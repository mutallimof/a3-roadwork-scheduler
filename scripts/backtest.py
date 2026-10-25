"""
backtest.py — accuracy of the app's recommendations on held-out weeks.

For each test week, only data from before the week is used. The script
measures:
  1. Expected traffic: how far the weekly profile (the app's averages)
     is from the measured hourly counts of that week (MAE, MAPE; hours
     with fewer than 10 vehicles are skipped).
  2. Choice quality: the app's recommended window for that week, ranked
     by measured traffic among all possible windows of the same length
     in the same shift (rank 1 = it really was the quietest), and how
     much more traffic it had than the quietest window.

The idea of testing on held-out data follows the aitraffic project
(forecast_lgbm.time_split/evaluate, github.com/DanieMyl/aitraffic). Unlike
its validation, no measured values from inside the test week are used.

Usage (needs the full data, see scripts/fetch_data.py):
    python scripts/backtest.py
    python scripts/backtest.py --years 2023 --out docs/backtest_results.md
"""

import argparse
import contextlib
import datetime
import io
import os
import sys

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
import data_utils as du  # noqa: E402
import scheduler  # noqa: E402
sys.path.insert(0, os.path.join(PROJECT_DIR, 'scripts'))
from compare_with_aitraffic import APP_WORK_HOURS, ours_v1  # noqa: E402

# Mondays in the second half of 2023, including weeks with public holidays
TEST_WEEKS = ['2023-07-10', '2023-08-07', '2023-09-04', '2023-10-02', '2023-10-30', '2023-11-27', '2023-12-18']
CASES = [('both', 'any', 1), ('both', 'any', 4), ('both', 'day', 4), ('both', 'night', 4), ('R1', 'day', 2)]


def measured_series(rows):
    ts = rows['Datum'] + pd.to_timedelta(rows['clock'], unit='h')
    return pd.Series(rows['traffic'].values, index=ts).sort_index()


def choose(version, sd_before, side, shift, hours, start):
    """Clock start of the first recommended window, for this app (v2) or the frozen v1 logic."""
    if version == 'v1':
        r = ours_v1(sd_before, int(sd_before['Zst'].iloc[0]), side, APP_WORK_HOURS[shift], start.date())
        return r['clock_start']
    r = scheduler.recommend(sd_before, side, shift, hours, start.date(), weeks=1)
    return None if r is None else pd.Timestamp(r['first_window_start'])


def run(df, version='v2'):
    prof_rows, choice_rows = [], []
    for week in TEST_WEEKS:
        start = pd.Timestamp(week)
        idx = pd.date_range(start, periods=168, freq='h')
        before = df[df['Datum'] < start]
        for station, sd_all in df.groupby('Zst'):
            sd_before = before[before['Zst'] == station]
            if sd_before.empty:
                continue
            for side in ('R1', 'R2'):
                rows, _ = scheduler.prepare(sd_before, side)
                prof = scheduler.weekly_profile(rows)
                actual_rows, _ = scheduler.prepare(sd_all[(sd_all['Datum'] >= start) & (sd_all['Datum'] < start + pd.Timedelta(days=7))], side)
                act = measured_series(actual_rows).reindex(idx)
                pred = prof['avg_traffic'].to_numpy()[[(t.dayofweek * 24 + t.hour) for t in idx]]
                m = act.notna().to_numpy() & ~np.isnan(pred) & (act.to_numpy() >= 10)
                a = act.to_numpy()[m]
                prof_rows.append(dict(n=int(m.sum()), ae=float(np.abs(a - pred[m]).sum()),
                                      ape=float((np.abs(a - pred[m]) / a).sum())))
            for side, shift, hours in CASES:
                chosen_t = choose(version, sd_before, side, shift, hours, start)
                if chosen_t is None:
                    continue
                week_rows, _ = scheduler.prepare(sd_all[(sd_all['Datum'] >= start) & (sd_all['Datum'] < start + pd.Timedelta(days=8))], side)
                series = measured_series(week_rows)
                allowed = scheduler.SHIFTS[shift][1]
                cands = []
                for t in idx:
                    if all((t + pd.Timedelta(hours=k)).hour in allowed for k in range(hours)):
                        v = series.reindex(pd.date_range(t, periods=hours, freq='h'))
                        if v.notna().all():
                            cands.append((t, v.mean()))
                if not cands:
                    continue
                c = pd.DataFrame(cands, columns=['t', 'traffic'])
                in_shift = all((chosen_t + pd.Timedelta(hours=k)).hour in allowed for k in range(hours))
                in_week = start <= chosen_t < start + pd.Timedelta(days=7)
                if not (in_shift and in_week):
                    choice_rows.append(dict(case=f"{side}, {shift}, {hours} h", rank=np.nan, n=len(c),
                                            excess=np.nan, outside=1))
                    continue
                chosen = series.reindex(pd.date_range(chosen_t, periods=hours, freq='h'))
                if chosen.isna().any():
                    continue          # chosen window falls on an excluded hour (holiday/implausible)
                v = chosen.mean()
                choice_rows.append(dict(case=f"{side}, {shift}, {hours} h", rank=int((c['traffic'] < v).sum()) + 1,
                                        n=len(c), excess=v / c['traffic'].min() - 1, outside=0))
    p = pd.DataFrame(prof_rows)
    accuracy = {'hours': int(p['n'].sum()), 'MAE': p['ae'].sum() / p['n'].sum(), 'MAPE': 100 * p['ape'].sum() / p['n'].sum()}
    ch = pd.DataFrame(choice_rows)
    choice = ch.groupby('case').agg(tests=('rank', 'size'), outside=('outside', 'mean'),
                                    median_rank=('rank', 'median'),
                                    top3=('rank', lambda s: (s <= 3).sum() / len(s)),
                                    mean_excess=('excess', 'mean'), windows=('n', 'median'))
    return accuracy, choice


def main():
    parser = argparse.ArgumentParser(description="Accuracy of the recommendations on held-out weeks.")
    parser.add_argument('--years', type=int, nargs='+', help="years to load (default: A3_YEARS / 2019 2023)")
    parser.add_argument('--out', help="also write the result as markdown to this file")
    parser.add_argument('--version', choices=['v1', 'v2'], default='v2',
                        help="v2 = this app; v1 = the logic before the comparison (frozen copy)")
    args = parser.parse_args()
    with contextlib.redirect_stdout(io.StringIO()):
        df = du.load_traffic_data(years=args.years)
    years = sorted(int(y) for y in df['year'].unique())
    accuracy, choice = run(df, args.version)
    lines = [f"Backtest ({args.version}) on held-out weeks ({', '.join(TEST_WEEKS)}), data years {years}, "
             f"run {datetime.date.today():%Y-%m-%d}. Real BASt data.", "",
             f"Expected traffic vs measured, per direction: {accuracy['hours']:,} hours, "
             f"MAE {accuracy['MAE']:.0f} vehicles/hour, MAPE {accuracy['MAPE']:.1f}%", "",
             "| Case | Tests | Outside shift or week | Median rank of chosen window | Chosen window in top 3 | "
             "Traffic above the quietest window | Windows per week |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for case, r in choice.iterrows():
        rank = '-' if pd.isna(r['median_rank']) else f"{r['median_rank']:.0f}"
        excess = '-' if pd.isna(r['mean_excess']) else f"{r['mean_excess']:.0%}"
        lines.append(f"| {case} | {int(r['tests'])} | {r['outside']:.0%} | {rank} | {r['top3']:.0%} | {excess} | {r['windows']:.0f} |")
    lines += ["", "Rank: position of the chosen window among all windows of that length in the shift and week, "
              "ordered by measured traffic (1 = quietest). Windows outside the shift or the week count as not in the top 3."]
    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
