"""
compare_with_aitraffic.py

Runs the same test cases through this app's recommendation logic and the
aitraffic project's recommend_windows.py (github.com/DanieMyl/aitraffic),
then checks both against the raw BASt counts.

Requirements:
  - the full data installed here (scripts/fetch_data.py);
  - a COPY of aitraffic in which clean_data.py and forecast_lgbm.py have
    been run (data_clean/ and models/ present), and a Python environment
    with aitraffic's requirements plus pyproj.

Usage:
    python scripts/compare_with_aitraffic.py --aitraffic-dir /path/to/aitraffic_copy
    python scripts/compare_with_aitraffic.py --aitraffic-dir ... --out docs/comparison_results.md

Test period: July to December 2023. aitraffic's model is trained on data
before 2023-07-01, so this period is held out for it and real counts exist
to check against. Its forecast is seeded with the measured week before the
horizon, as it would be in use.

Hour convention used for the check: BASt 'Stunde' n covers (n-1):00 to
n:00 local time (Stunde 1 = 00:00-01:00); see docs/comparison.md.
"""

import argparse
import contextlib
import datetime
import io
import logging
import os
import sys

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
import data_utils as du  # noqa: E402

DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

# Clock hours (start of hour) in which a window may lie, per shift
SHIFT_CLOCK_HOURS = {
    'any': set(range(24)),
    'day': set(range(6, 18)),              # 06:00-18:00
    'night': {22, 23, 0, 1, 2, 3, 4, 5},   # 22:00-06:00
}
# The matching option in this app
APP_WORK_HOURS = {'any': '24h (always)', 'day': 'Day (06-18)', 'night': 'Night only (22-06)'}

# station, side ('both', 'R1', 'R2'), shift, project length in hours, horizon start (7 days), note
CASES = [
    (9033, 'both', 'any', 1, '2023-09-04', 'Monday start'),
    (9033, 'both', 'any', 4, '2023-09-04', 'Monday start'),
    (9033, 'R1', 'day', 2, '2023-09-13', 'one side, day shift'),
    (9040, 'both', 'night', 4, '2023-10-16', 'night shift'),
    (9040, 'both', 'day', 4, '2023-11-05', 'Sunday start'),
    (9521, 'R2', 'any', 2, '2023-11-10', 'Friday start'),
    (9507, 'both', 'any', 4, '2023-10-02', 'holiday week (Tue 3 Oct)'),
    (9093, 'both', 'day', 4, '2023-10-30', 'holiday week (Wed 1 Nov)'),
    (9159, 'both', 'night', 2, '2023-12-18', 'Christmas week (25/26 Dec)'),
    (9050, 'both', 'any', 1, '2023-07-10', "station with 'u' flags"),
    (9085, 'R1', 'day', 1, '2023-08-10', 'holiday Tue 15 Aug, 41% estimated'),
    (9011, 'both', 'night', 4, '2023-09-22', 'Friday start, night shift'),
]


# ---------------------------------------------------------------------------
# This app, version 1: a frozen copy of the logic in app.py on branch
# feat/data-and-quality (commit 54fb800), kept so the comparison can be
# repeated after the app changes.
# ---------------------------------------------------------------------------
def ours_v1(df, station, side, work_hours, earliest):
    sd = df[df['Zst'] == station].copy()
    if side == 'R1':
        sd['eff'], sd['eff_trucks'] = sd['KFZ_R1'], sd['Lkw_R1']
    elif side == 'R2':
        sd['eff'], sd['eff_trucks'] = sd['KFZ_R2'], sd['Lkw_R2']
    else:
        sd['eff'], sd['eff_trucks'] = sd['total_traffic'], sd['total_trucks']
    sd['ratio'] = sd['eff_trucks'] / sd['eff']
    if work_hours == "Night only (22-06)":
        mask = (sd['Stunde'] >= 22) | (sd['Stunde'] <= 6)
    elif work_hours == "Day (06-18)":
        mask = (sd['Stunde'] >= 6) & (sd['Stunde'] <= 18)
    else:
        mask = pd.Series(True, index=sd.index)
    hs = sd[mask].groupby(['Wotag', 'Stunde']).agg(avg=('eff', 'mean'), tr=('ratio', 'mean')).reset_index()
    hs['score'] = (1 - hs['avg'] / hs['avg'].max()) * (1 - hs['tr'])
    hs = hs.dropna(subset=['score'])
    best = hs.sort_values('score', ascending=False).iloc[0]
    worst = hs.sort_values('score').iloc[0]
    target = int(best['Wotag']) - 1
    ahead = (target - earliest.weekday()) % 7 or 7
    start_date = earliest + datetime.timedelta(days=ahead)
    stunde = int(best['Stunde'])
    return {
        'date': start_date, 'stunde': stunde,
        # what the app displays: the Stunde value as a clock time
        'label': f"{DAYS[target]} {start_date:%d %b} {stunde:02d}:00",
        # the data rows it is based on, in clock time
        'clock_start': pd.Timestamp(start_date) + pd.Timedelta(hours=stunde - 1),
        'expected': float(best['avg']),
        'reduction': 1 - best['avg'] / worst['avg'],
    }


# ---------------------------------------------------------------------------
# aitraffic
# ---------------------------------------------------------------------------
class Aitraffic:
    def __init__(self, path):
        self.path = path
        sys.path.insert(0, path)
        self._cwd = os.getcwd()
        os.chdir(path)          # aitraffic uses relative paths (data_clean/, models/)
        logging.disable(logging.INFO)
        with contextlib.redirect_stdout(io.StringIO()):
            import recommend_windows as rw
        self.rw = rw
        self.model, self.meta, self.hist = rw.load_assets()

    def recommend(self, station, side, shift, hours, start):
        rw = self.rw
        stations = [(station, 'R1'), (station, 'R2')] if side == 'both' else [(station, side)]
        end = (pd.Timestamp(start) + pd.Timedelta(days=7)).strftime('%Y-%m-%d')
        with contextlib.redirect_stdout(io.StringIO()):
            recs = rw.get_recommendations(
                stations=stations, duration=rw.ContinuousDuration(hours=hours),
                horizon_start=start, horizon_end=end, top_n=10_000, min_sep_hours=1,
                model=self.model, meta=self.meta, df_history=self.hist)
        recs['start'] = pd.to_datetime(recs['start_date'])
        allowed = SHIFT_CLOCK_HOURS[shift]
        inside = recs['start'].apply(lambda t: all((t + pd.Timedelta(hours=k)).hour in allowed
                                                   for k in range(hours)))
        recs = recs[inside]
        best = recs.sort_values('composite_score').iloc[0]
        worst_volume = recs['total_kfz'].max()
        return {
            'clock_start': best['start'],
            'label': f"{DAYS[best['start'].dayofweek]} {best['start']:%d %b %H:%M}",
            'expected': float(best['mean_kfz_per_hour']),
            'reduction': 1 - best['total_kfz'] / worst_volume,
        }


# ---------------------------------------------------------------------------
# Check against the raw counts
# ---------------------------------------------------------------------------
def hourly_series(raw, station, side):
    s = raw[raw['Zst'] == station]
    ts = s['Datum'] + pd.to_timedelta(s['Stunde'] - 1, unit='h')
    col = {'both': 'total_traffic', 'R1': 'KFZ_R1', 'R2': 'KFZ_R2'}[side]
    return pd.Series(s[col].values, index=ts).sort_index()


def actual(series, start, hours):
    idx = pd.date_range(start, periods=hours, freq='h')
    return float(series.reindex(idx).mean())


def truth(series, shift, hours, horizon_start):
    """All windows of `hours` consecutive hours inside the shift in the 7-day horizon, with measured traffic."""
    allowed = SHIFT_CLOCK_HOURS[shift]
    starts = pd.date_range(horizon_start, periods=7 * 24, freq='h')
    rows = []
    for t in starts:
        if all((t + pd.Timedelta(hours=k)).hour in allowed for k in range(hours)):
            rows.append((t, actual(series, t, hours)))
    return pd.DataFrame(rows, columns=['start', 'traffic']).dropna()


def main():
    parser = argparse.ArgumentParser(description="Compare this app with aitraffic on the same cases.")
    parser.add_argument('--aitraffic-dir', required=True)
    parser.add_argument('--out', help="write the markdown table to this file")
    parser.add_argument('--version', choices=['v1', 'v2', 'both'], default='both')
    args = parser.parse_args()
    if args.out:
        args.out = os.path.abspath(args.out)     # the aitraffic code needs a chdir below

    with contextlib.redirect_stdout(io.StringIO()):
        raw = du.load_traffic_data(years=[2023])
    ait = Aitraffic(os.path.abspath(args.aitraffic_dir))

    ours_versions = []
    if args.version in ('v1', 'both'):
        ours_versions.append(('ours v1', lambda df, st, side, shift, h, start: ours_v1(
            df, st, side, APP_WORK_HOURS[shift], start)))
    if args.version in ('v2', 'both'):
        try:
            import scheduler
            ours_versions.append(('ours v2', lambda df, st, side, shift, h, start: scheduler.compare_adapter(
                df, st, side, shift, h, start)))
        except ImportError:
            pass

    rows = []
    for i, (station, side, shift, hours, start, note) in enumerate(CASES, 1):
        start_date = datetime.date.fromisoformat(start)
        series = hourly_series(raw, station, side)
        tr = truth(series, shift, hours, start)
        best_t, worst_t = tr.loc[tr['traffic'].idxmin()], tr['traffic'].max()
        results = {}
        a = ait.recommend(station, side, shift, hours, start)
        results['aitraffic'] = a
        before = raw[raw['Datum'] < pd.Timestamp(start)]
        for name, fn in ours_versions:
            results[name] = fn(raw, station, side, shift, hours, start_date)
            results[name + ' (data before start only)'] = fn(before, station, side, shift, hours, start_date)
        for name, r in results.items():
            act = actual(series, r['clock_start'], hours)
            in_horizon = pd.Timestamp(start) <= r['clock_start'] < pd.Timestamp(start) + pd.Timedelta(days=7)
            in_shift = all((r['clock_start'] + pd.Timedelta(hours=k)).hour in SHIFT_CLOCK_HOURS[shift]
                           for k in range(hours))
            rank = int((tr['traffic'] < act).sum()) + 1 if in_horizon and in_shift else None
            rows.append(dict(case=i, station=station, side=side, shift=shift, hours=hours, start=start, note=note,
                             tool=name, shown=r['label'],
                             data_slot=f"{r['clock_start']:%a %d %b %H:%M}",
                             expected=round(r['expected']), reduction=f"{r['reduction']:.0%}",
                             measured=round(act), measured_reduction=f"{1 - act / worst_t:.0%}",
                             in_horizon='yes' if in_horizon else 'no', in_shift='yes' if in_shift else 'no',
                             rank=f"{rank}/{len(tr)}" if rank else '-',
                             best_possible=f"{best_t['start']:%a %d %b %H:%M} ({round(best_t['traffic'])})"))
    res = pd.DataFrame(rows)

    cols = ['case', 'tool', 'shown', 'data_slot', 'expected', 'reduction', 'measured', 'measured_reduction',
            'in_horizon', 'in_shift', 'rank']
    lines = ["| Case | Setup | Best possible (measured) |", "|---|---|---|"]
    for (i,), g in res.groupby(['case']):
        r = g.iloc[0]
        lines.append(f"| {i} | {r['station']} {r['side']}, {r['shift']}, {r['hours']} h, from {r['start']} ({r['note']}) | {r['best_possible']} |")
    lines += ["", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in res.itertuples():
        lines.append("| " + " | ".join(str(getattr(r, c)) for c in cols) + " |")
    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text)
    os.chdir(ait._cwd)
    return 0


if __name__ == '__main__':
    sys.exit(main())
