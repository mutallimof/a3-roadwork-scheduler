"""
evaluate_models.py

Backtests three forecasting approaches per A3 station on real, held-out
traffic data:

  1. seasonal-naive — the historical (weekday, hour) average from the
     training window. This is roughly what app.py's own scoring uses, so
     it's the right baseline to beat.
  2. prophet        — the same model refresh_forecasts.py fits, evaluated
     out-of-sample instead of just forecasting forward.
  3. lightgbm       — gradient-boosted trees on calendar features (hour,
     weekday, month, holiday flag) plus lag features (traffic 1h, 24h and
     168h/1-week before each timestamp).

For each station, the last `--holdout-months` months of its history are
held out as a test set never seen during training; everything before that
is the training set. MAE and MAPE are reported per station and pooled into
an overall summary, printed to the console and written to
`evaluation_results.json`.

IMPORTANT — lag-feature caveat: LightGBM's lag features are computed from
the *actual* historical traffic at each lag point, including inside the
test window. That's a fair way to compare "given recent real traffic, how
good is each model's short-range/pattern fit", but it is NOT the same
setup as the multi-month-ahead forecast the app actually needs (where
those recent lags wouldn't be available). Prophet and the seasonal-naive
baseline don't use lags at all, so this evaluation is slightly generous to
LightGBM for a long-horizon comparison — read its numbers as "best case"
rather than "what you'd get scheduling roadwork 6 months out."

MAPE is undefined at zero traffic and unstable near it; hours with fewer
than `MAPE_MIN_TRAFFIC` vehicles are excluded from the MAPE calculation
(but still count towards MAE).

Usage (run this locally once you have real traffic data — see README):

    python -m pip install prophet lightgbm
    python evaluate_models.py
    python evaluate_models.py --holdout-months 6 --stations 9155,9156
"""

import argparse
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from data_utils import load_traffic_data
from refresh_forecasts import GERMAN_HOLIDAYS, prepare_station_series

MIN_TRAIN_ROWS = 24 * 60  # ~60 days of hourly data before a station is worth backtesting at all
MAPE_MIN_TRAFFIC = 20.0   # veh/hr threshold below which percentage error is too noisy to trust


def mean_absolute_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(y_true) - np.asarray(y_pred))))


def mean_absolute_percentage_error(y_true: np.ndarray, y_pred: np.ndarray) -> Optional[float]:
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    mask = y_true >= MAPE_MIN_TRAFFIC
    if not mask.any():
        return None
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['hour'] = df['ds'].dt.hour
    df['weekday'] = df['ds'].dt.weekday  # 0 = Monday
    df['month'] = df['ds'].dt.month
    holiday_dates = set(GERMAN_HOLIDAYS['ds'].dt.date)
    df['is_holiday'] = df['ds'].dt.date.isin(holiday_dates).astype(int)
    return df


def add_lag_features(df: pd.DataFrame, full_lookup: pd.Series) -> pd.DataFrame:
    df = df.copy()
    for lag_hours, name in [(1, 'lag_1h'), (24, 'lag_24h'), (168, 'lag_168h')]:
        df[name] = (df['ds'] - pd.Timedelta(hours=lag_hours)).map(full_lookup)
    return df


def seasonal_naive_forecast(train_cal: pd.DataFrame, test_cal: pd.DataFrame) -> np.ndarray:
    """Predicts each test hour using the (weekday, hour) mean observed in training."""
    lookup = train_cal.groupby(['weekday', 'hour'])['y'].mean()
    global_mean = train_cal['y'].mean()
    preds = [lookup.get((row.weekday, row.hour), global_mean) for row in test_cal.itertuples()]
    return np.array(preds)


def prophet_forecast(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    from prophet import Prophet

    m = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        holidays=GERMAN_HOLIDAYS,
    )
    m.fit(train[['ds', 'y']])
    forecast = m.predict(test[['ds']])
    return forecast['yhat'].clip(lower=0).values


def lightgbm_forecast(train: pd.DataFrame, test: pd.DataFrame, full_series: pd.DataFrame) -> np.ndarray:
    import lightgbm as lgb

    full_lookup = full_series.set_index('ds')['y']
    feature_cols = ['hour', 'weekday', 'month', 'is_holiday', 'lag_1h', 'lag_24h', 'lag_168h']

    train_feat = add_lag_features(add_calendar_features(train), full_lookup)
    test_feat = add_lag_features(add_calendar_features(test), full_lookup)

    fill_value = train_feat['y'].mean()
    train_feat[feature_cols] = train_feat[feature_cols].fillna(fill_value)
    test_feat[feature_cols] = test_feat[feature_cols].fillna(fill_value)

    model = lgb.LGBMRegressor(
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=31,
        random_state=42,
        verbosity=-1,
    )
    model.fit(train_feat[feature_cols], train_feat['y'])
    preds = model.predict(test_feat[feature_cols])
    return np.clip(preds, 0, None)


def evaluate_station(df: pd.DataFrame, station_id, holdout_months: int) -> Optional[Dict]:
    series = prepare_station_series(df, station_id)
    if len(series) < MIN_TRAIN_ROWS:
        return None

    cutoff = series['ds'].max() - pd.DateOffset(months=holdout_months)
    train = series[series['ds'] <= cutoff].reset_index(drop=True)
    test = series[series['ds'] > cutoff].reset_index(drop=True)
    if len(train) < MIN_TRAIN_ROWS or test.empty:
        return None

    train_cal = add_calendar_features(train)
    test_cal = add_calendar_features(test)
    y_test = test['y'].values

    result: Dict[str, Optional[Dict[str, float]]] = {'n_train': len(train), 'n_test': len(test)}

    naive_preds = seasonal_naive_forecast(train_cal, test_cal)
    result['seasonal_naive'] = {
        'mae': mean_absolute_error(y_test, naive_preds),
        'mape': mean_absolute_percentage_error(y_test, naive_preds),
    }

    try:
        prophet_preds = prophet_forecast(train, test)
        result['prophet'] = {
            'mae': mean_absolute_error(y_test, prophet_preds),
            'mape': mean_absolute_percentage_error(y_test, prophet_preds),
        }
    except ImportError:
        result['prophet'] = None
        print("  [prophet] not installed — `pip install prophet` to include it")
    except Exception as e:
        result['prophet'] = None
        print(f"  [prophet] failed for station {station_id}: {e}")

    try:
        lgb_preds = lightgbm_forecast(train, test, series)
        result['lightgbm'] = {
            'mae': mean_absolute_error(y_test, lgb_preds),
            'mape': mean_absolute_percentage_error(y_test, lgb_preds),
        }
    except ImportError:
        result['lightgbm'] = None
        print("  [lightgbm] not installed — `pip install lightgbm` to include it")
    except Exception as e:
        result['lightgbm'] = None
        print(f"  [lightgbm] failed for station {station_id}: {e}")

    return result


def summarize(per_station: Dict[int, Dict], model_names: List[str]) -> Dict[str, Dict[str, float]]:
    overall = {}
    for model in model_names:
        maes = [r[model]['mae'] for r in per_station.values() if r.get(model)]
        mapes = [r[model]['mape'] for r in per_station.values() if r.get(model) and r[model]['mape'] is not None]
        if not maes:
            overall[model] = None
            continue
        overall[model] = {
            'stations_evaluated': len(maes),
            'mae_mean': float(np.mean(maes)),
            'mae_median': float(np.median(maes)),
            'mape_mean': float(np.mean(mapes)) if mapes else None,
            'mape_median': float(np.median(mapes)) if mapes else None,
        }
    return overall


def print_summary(overall: Dict[str, Optional[Dict[str, float]]]) -> None:
    print("\n" + "=" * 72)
    print("OVERALL SUMMARY (across all backtested stations)")
    print("=" * 72)
    header = f"{'Model':<18}{'Stations':>10}{'MAE mean':>12}{'MAE median':>13}{'MAPE mean':>12}"
    print(header)
    print("-" * len(header))
    for model, stats in overall.items():
        if stats is None:
            print(f"{model:<18}{'—':>10}{'—':>12}{'—':>13}{'—':>12}")
            continue
        mape_str = f"{stats['mape_mean']:.1f}%" if stats['mape_mean'] is not None else "n/a"
        print(f"{model:<18}{stats['stations_evaluated']:>10}{stats['mae_mean']:>12.1f}"
              f"{stats['mae_median']:>13.1f}{mape_str:>12}")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest seasonal-naive vs Prophet vs LightGBM on A3 traffic data.")
    parser.add_argument('--holdout-months', type=int, default=3,
                         help="Number of trailing months per station held out as the test set (default: 3).")
    parser.add_argument('--stations', type=str, default=None,
                         help="Comma-separated station IDs to evaluate (default: all stations with enough history).")
    parser.add_argument('--output', type=str, default='evaluation_results.json',
                         help="Path to write the JSON results (default: evaluation_results.json).")
    args = parser.parse_args()

    print("Loading traffic data...")
    df = load_traffic_data()

    station_ids = sorted(df['Zst'].unique())
    if args.stations:
        wanted = {int(s.strip()) for s in args.stations.split(',')}
        station_ids = [s for s in station_ids if s in wanted]

    print(f"Backtesting {len(station_ids)} station(s) with a {args.holdout_months}-month hold-out...\n")

    per_station = {}
    model_names = ['seasonal_naive', 'prophet', 'lightgbm']
    for sid in station_ids:
        print(f"Station {sid}...")
        result = evaluate_station(df, sid, args.holdout_months)
        if result is None:
            print(f"  Skipped (not enough history for a {args.holdout_months}-month hold-out)")
            continue
        per_station[int(sid)] = result
        for model in model_names:
            m = result.get(model)
            if m:
                mape_str = f"{m['mape']:.1f}%" if m['mape'] is not None else "n/a"
                print(f"  {model:<16} MAE={m['mae']:.1f}  MAPE={mape_str}")

    if not per_station:
        print("\nNo station had enough history for the requested hold-out. "
              "Try a smaller --holdout-months, or add more yearly data.")
        return

    overall = summarize(per_station, model_names)
    print_summary(overall)

    output = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'holdout_months': args.holdout_months,
        'mape_min_traffic': MAPE_MIN_TRAFFIC,
        'stations': per_station,
        'overall': overall,
    }
    with open(args.output, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved detailed results to {args.output}")


if __name__ == '__main__':
    main()
