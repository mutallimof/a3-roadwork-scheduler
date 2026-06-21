"""
refresh_forecasts.py

Regenerates prophet_results.json from whatever traffic data is currently
present (see data_utils.py — it auto-detects any year folders in the
project directory).

Includes German national public holidays as a Prophet regressor, so the
model can learn a separate effect for holiday traffic instead of folding
it into the regular weekly/yearly pattern.

Run this manually whenever new yearly data has been added and you want
the seasonal forecasts to reflect it. This is NOT run automatically by
the app, since fitting Prophet across all stations takes several minutes.

Before first use:
    python -m pip install prophet

Usage:
    python refresh_forecasts.py
"""

import json
import pandas as pd
from prophet import Prophet
from data_utils import load_traffic_data


# German national public holidays (fixed + Easter-based, 2019-2026).
# Extend this list when adding years beyond 2026.
GERMAN_HOLIDAYS = pd.DataFrame({
    'holiday': 'public_holiday',
    'ds': pd.to_datetime([
        # 2019
        '2019-01-01', '2019-04-19', '2019-04-22', '2019-05-01', '2019-05-30',
        '2019-06-10', '2019-10-03', '2019-12-25', '2019-12-26',
        # 2023
        '2023-01-01', '2023-04-07', '2023-04-10', '2023-05-01', '2023-05-18',
        '2023-05-29', '2023-10-03', '2023-12-25', '2023-12-26',
        # 2024
        '2024-01-01', '2024-03-29', '2024-04-01', '2024-05-01', '2024-05-09',
        '2024-05-20', '2024-10-03', '2024-12-25', '2024-12-26',
        # 2025
        '2025-01-01', '2025-04-18', '2025-04-21', '2025-05-01', '2025-05-29',
        '2025-06-09', '2025-10-03', '2025-12-25', '2025-12-26',
        # 2026
        '2026-01-01', '2026-04-03', '2026-04-06', '2026-05-01', '2026-05-14',
        '2026-05-25', '2026-10-03', '2026-12-25', '2026-12-26',
    ]),
    'lower_window': 0,
    'upper_window': 0,
})


def prepare_station_series(df, station_id):
    station_df = df[df['Zst'] == station_id].copy()
    station_df['ds'] = station_df['Datum'] + pd.to_timedelta(station_df['Stunde'], unit='h')
    station_df = station_df[['ds', 'total_traffic']].rename(columns={'total_traffic': 'y'})
    station_df = station_df.sort_values('ds').reset_index(drop=True)
    return station_df


def main():
    print("Loading traffic data...")
    df = load_traffic_data()

    station_ids = df['Zst'].unique()
    print(f"Found {len(station_ids)} stations. Fitting Prophet for each (this takes a while)...\n")

    results = {}
    for sid in station_ids:
        try:
            series = prepare_station_series(df, sid)
            if len(series) < 100:
                print(f"Skipped {sid}: not enough data points ({len(series)})")
                continue

            m = Prophet(
                yearly_seasonality=True,
                weekly_seasonality=True,
                daily_seasonality=False,
                holidays=GERMAN_HOLIDAYS
            )
            m.fit(series)

            future = m.make_future_dataframe(periods=8760, freq='h')
            forecast = m.predict(future)
            forecast['yhat'] = forecast['yhat'].clip(lower=0)
            forecast['month'] = forecast['ds'].dt.month

            monthly_avg = forecast.groupby('month')['yhat'].mean().to_dict()
            results[int(sid)] = {int(k): float(v) for k, v in monthly_avg.items()}

            print(f"Done: {sid} ({len(results)}/{len(station_ids)})")
        except Exception as e:
            print(f"Failed {sid}: {e}")

    with open('prophet_results.json', 'w') as f:
        json.dump(results, f)

    print(f"\nSaved {len(results)} stations to prophet_results.json")


if __name__ == '__main__':
    main()
