"""
scheduler.py — the recommendation logic of the app, without the interface.

How a recommendation is made
----------------------------
1. For the chosen station and side of the road, average the measured
   hourly counts for every weekday and clock hour (168 slots per week).
   Public holidays in Bavaria and hours BASt flagged as implausible ('u')
   are left out of the averages.
2. Every block of `hours` consecutive slots that lies completely inside
   the chosen shift is a candidate window (a block may cross midnight,
   e.g. Sunday 22:00 to Monday 02:00).
3. Each window gets the app's score, computed on the window's averages:
       traffic_score = 1 - avg_traffic / highest avg_traffic among the windows
       truck_score   = 1 - avg_truck_share
       score         = traffic_score * truck_score
   The highest score wins.
4. The project starts on the first matching weekday on or after the
   earliest start date and repeats weekly.

Hour convention: BASt 'Stunde' n covers (n-1):00 to n:00 local time
(Stunde 1 = 00:00-01:00). This follows the BASt data-set description and
is visible in the data: on the spring daylight-saving day, Stunde 3
(02:00-03:00, the hour that does not exist) is 0 at every station.

Several parts follow the aitraffic project (github.com/DanieMyl/aitraffic):
the hour convention (clean_data.parse_timestamp), scoring whole windows
instead of single hours (recommend_windows._find_continuous_windows),
shifts that cross midnight (recommend_windows.ShiftDuration), leaving out
'u'-flagged hours (forecast_lgbm.load_data) and Bavarian public holidays
(its is_holiday feature). The code here is written for this app.
"""

import datetime

import pandas as pd

DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

# Clock hours (start of each hour) that belong to a shift; end hour excluded
SHIFTS = {
    'day': ('Day (06-18)', set(range(6, 18))),
    'night': ('Night only (22-06)', {22, 23, 0, 1, 2, 3, 4, 5}),
    'any': ('24h (always)', set(range(24))),
}
SHIFT_BY_LABEL = {label: key for key, (label, _) in SHIFTS.items()}


def clock_hour(stunde):
    """BASt Stunde (1-24) -> clock hour at the start of the counted hour (0-23)."""
    return stunde - 1


def _easter(year):
    # Anonymous Gregorian algorithm (Meeus/Jones/Butcher)
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return datetime.date(year, month, day)


def bavarian_holidays(year):
    """
    Public holidays valid in all of Bavaria, as {date: name}. Matches the
    `holidays` package's Germany(state='BY') list used by aitraffic. Not
    included: 15 August (only in communities with a Catholic majority) and
    8 August (Augsburg only).
    """
    e = _easter(year)
    d = datetime.date
    days = {
        d(year, 1, 1): 'Neujahr', d(year, 1, 6): 'Heilige Drei Könige',
        e - datetime.timedelta(days=2): 'Karfreitag', e + datetime.timedelta(days=1): 'Ostermontag',
        d(year, 5, 1): 'Erster Mai', e + datetime.timedelta(days=39): 'Christi Himmelfahrt',
        e + datetime.timedelta(days=50): 'Pfingstmontag', e + datetime.timedelta(days=60): 'Fronleichnam',
        d(year, 10, 3): 'Tag der Deutschen Einheit', d(year, 11, 1): 'Allerheiligen',
        d(year, 12, 25): 'Erster Weihnachtstag', d(year, 12, 26): 'Zweiter Weihnachtstag',
    }
    return dict(sorted(days.items()))


def holidays_between(start, end):
    """Bavarian public holidays in [start, end), as a list of (date, name)."""
    out = []
    for year in range(start.year, end.year + 1):
        out += [(day, name) for day, name in bavarian_holidays(year).items() if start <= day < end]
    return out


def prepare(station_data, side):
    """
    Adds clock time and the traffic of the chosen side to a station's rows.
    side: 'both', 'R1' or 'R2'. Drops hours flagged implausible ('u') on
    that side and Bavarian public holidays. Returns (rows, excluded) where
    excluded counts the dropped hours by reason.
    """
    d = station_data.copy()
    d['clock'] = clock_hour(d['Stunde'])
    d['dow'] = d['Wotag'] - 1
    if side == 'R1':
        d['traffic'], d['trucks'], flags = d['KFZ_R1'], d['Lkw_R1'], [d['K_KFZ_R1']]
    elif side == 'R2':
        d['traffic'], d['trucks'], flags = d['KFZ_R2'], d['Lkw_R2'], [d['K_KFZ_R2']]
    else:
        d['traffic'], d['trucks'] = d['total_traffic'], d['total_trucks']
        flags = [d['K_KFZ_R1'], d['K_KFZ_R2']]
    implausible = pd.Series(False, index=d.index)
    for f in flags:
        implausible |= f.astype(str).str.strip().eq('u')
    years = sorted(d['Datum'].dt.year.unique()) if len(d) else []
    holiday_dates = {day for y in years for day in bavarian_holidays(int(y))}
    holiday = d['Datum'].dt.date.isin(holiday_dates)
    excluded = {'implausible': int(implausible.sum()), 'holiday': int((holiday & ~implausible).sum())}
    d = d[~implausible & ~holiday]
    d = d.assign(truck_ratio=d['trucks'] / d['traffic'])
    return d, excluded


def weekly_profile(rows):
    """Average traffic and truck share for each of the 168 weekday-hour slots (index = dow*24 + clock)."""
    p = rows.groupby(['dow', 'clock']).agg(avg_traffic=('traffic', 'mean'),
                                           avg_truck_ratio=('truck_ratio', 'mean'),
                                           hours=('traffic', 'size'))
    p.index = [dow * 24 + c for dow, c in p.index]
    return p.reindex(range(168))


def score_windows(profile, shift, hours):
    """
    All windows of `hours` consecutive slots inside the shift, scored.
    Returns a DataFrame sorted best first: start_slot, dow, clock,
    avg_traffic, avg_truck_ratio, traffic_score, score.
    """
    allowed = SHIFTS[shift][1]
    rows = []
    for start in range(168):
        slots = [(start + k) % 168 for k in range(hours)]
        if not all(s % 24 in allowed for s in slots):
            continue
        block = profile.loc[slots]
        if block['avg_traffic'].isna().any():
            continue
        rows.append(dict(start_slot=start, dow=start // 24, clock=start % 24,
                         avg_traffic=block['avg_traffic'].mean(),
                         avg_truck_ratio=block['avg_truck_ratio'].mean()))
    w = pd.DataFrame(rows)
    if w.empty:
        return w
    w['traffic_score'] = 1 - w['avg_traffic'] / w['avg_traffic'].max()
    w['score'] = w['traffic_score'] * (1 - w['avg_truck_ratio'])
    return w.sort_values(['score', 'start_slot'], ascending=[False, True]).reset_index(drop=True)


def window_label(dow, clock, hours):
    end = (clock + hours) % 24
    return f"{DAY_NAMES[dow]}s, {clock:02d}:00–{end:02d}:00"


def recommend(station_data, side, shift, hours, earliest_start, weeks):
    """
    Recommendation for one station. Returns None if there is no usable
    data for the shift. Otherwise a dict with the best and worst window,
    the reduction, the project dates and the holidays inside them.
    """
    rows, excluded = prepare(station_data, side)
    if rows.empty:
        return None
    profile = weekly_profile(rows)
    windows = score_windows(profile, shift, hours)
    if windows.empty:
        return None
    best = windows.iloc[0]
    worst = windows.sort_values('score').iloc[0]
    days_ahead = (int(best['dow']) - earliest_start.weekday()) % 7
    start_date = earliest_start + datetime.timedelta(days=days_ahead)
    end_date = start_date + datetime.timedelta(weeks=weeks)
    project_holidays = holidays_between(start_date, end_date)
    on_work_days = [(d, n) for d, n in project_holidays if d.weekday() == int(best['dow'])]
    return {
        'best': best, 'worst': worst, 'windows': windows, 'profile': profile,
        'reduction': 1 - best['avg_traffic'] / worst['avg_traffic'],
        'start_date': start_date, 'end_date': end_date,
        'first_window_start': datetime.datetime.combine(start_date, datetime.time(int(best['clock']))),
        'label': window_label(int(best['dow']), int(best['clock']), hours),
        'holidays': project_holidays, 'holidays_on_work_days': on_work_days,
        'excluded': excluded, 'rows_used': len(rows),
    }


def compare_adapter(df, station, side, shift, hours, earliest_start):
    """Output in the shape scripts/compare_with_aitraffic.py expects."""
    r = recommend(df[df['Zst'] == station], side, shift, hours, earliest_start, weeks=1)
    t = pd.Timestamp(r['first_window_start'])
    return {'clock_start': t, 'label': f"{t:%a %d %b %H:%M}", 'expected': float(r['best']['avg_traffic']),
            'reduction': float(r['reduction'])}
