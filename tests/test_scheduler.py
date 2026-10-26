"""
Tests for scheduler.py (the recommendation logic).

All inputs are small GENERATED frames in the layout data_utils produces.
They are not real traffic data.

Run:  python -m unittest discover -s tests -v
"""

import datetime
import os
import sys
import unittest

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, 'scripts'))

import scheduler  # noqa: E402
from compare_with_aitraffic import ours_v1  # noqa: E402


def frame(start, days, traffic, station=9033):
    """Generated rows: traffic(timestamp at the start of the counted hour) -> vehicles per direction."""
    rows = []
    for day in pd.date_range(start, periods=days, freq='D'):
        for stunde in range(1, 25):
            t = day + pd.Timedelta(hours=stunde - 1)
            v = traffic(t)
            rows.append(dict(Zst=station, Datum=day, Wotag=day.dayofweek + 1, Stunde=stunde, year=day.year,
                             KFZ_R1=v, KFZ_R2=v, Lkw_R1=v // 10, Lkw_R2=v // 10, K_KFZ_R1='-', K_KFZ_R2='-'))
    df = pd.DataFrame(rows)
    df['total_traffic'] = df['KFZ_R1'] + df['KFZ_R2']
    df['total_trucks'] = df['Lkw_R1'] + df['Lkw_R2']
    df['truck_ratio'] = df['total_trucks'] / df['total_traffic']
    return df


def busy_except(quiet):
    """1000 vehicles per hour, except the (dayofweek, hour) slots in `quiet` (vehicles given)."""
    return lambda t: quiet.get((t.dayofweek, t.hour), 1000)


class ConventionAndHolidaysTest(unittest.TestCase):
    def test_stunde_1_is_midnight(self):
        self.assertEqual(scheduler.clock_hour(1), 0)
        self.assertEqual(scheduler.clock_hour(24), 23)

    def test_bavarian_holidays_known_dates(self):
        h23 = scheduler.bavarian_holidays(2023)
        self.assertEqual(len(h23), 12)
        for d in ('2023-04-07', '2023-04-10', '2023-05-18', '2023-05-29', '2023-06-08', '2023-11-01'):
            self.assertIn(datetime.date.fromisoformat(d), h23)
        self.assertNotIn(datetime.date(2023, 8, 15), h23)    # only in Catholic-majority communities
        self.assertIn(datetime.date(2026, 6, 4), scheduler.bavarian_holidays(2026))   # Fronleichnam

    def test_holidays_between(self):
        got = scheduler.holidays_between(datetime.date(2026, 12, 20), datetime.date(2027, 1, 7))
        self.assertEqual([d.isoformat() for d, _ in got], ['2026-12-25', '2026-12-26', '2027-01-01', '2027-01-06'])


class PrepareTest(unittest.TestCase):
    def test_drops_implausible_on_the_chosen_side_and_holidays(self):
        df = frame('2023-10-02', 7, lambda t: 500)            # Tue 3 Oct is a holiday
        df.loc[0, 'K_KFZ_R2'] = 'u'
        rows, excluded = scheduler.prepare(df, 'R1')
        self.assertEqual(excluded, {'implausible': 0, 'holiday': 24})
        rows, excluded = scheduler.prepare(df, 'both')
        self.assertEqual(excluded, {'implausible': 1, 'holiday': 24})
        self.assertEqual(len(rows), 7 * 24 - 25)
        self.assertEqual(rows['clock'].min(), 0)


class WindowTest(unittest.TestCase):
    def test_night_window_crosses_midnight_and_week_end(self):
        # Quiet from Sunday 22:00 to Monday 02:00
        quiet = {(6, 22): 50, (6, 23): 50, (0, 0): 50, (0, 1): 50}
        df = frame('2023-09-04', 14, busy_except(quiet))
        r = scheduler.recommend(df, 'both', 'night', 4, datetime.date(2023, 9, 4), weeks=2)
        self.assertEqual((int(r['best']['dow']), int(r['best']['clock'])), (6, 22))
        self.assertEqual(r['label'], 'Sundays, 22:00–02:00')
        # the night shift never yields a window touching 06:00-22:00
        for w in r['windows'].itertuples():
            hours = {(w.clock + k) % 24 for k in range(4)}
            self.assertTrue(hours <= scheduler.SHIFTS['night'][1])

    def test_day_shift_is_06_to_18(self):
        # 05:00 is the quietest hour of the week but outside the day shift
        df = frame('2023-09-04', 7, busy_except({(6, 5): 10, (6, 6): 300}))
        r = scheduler.recommend(df, 'both', 'day', 1, datetime.date(2023, 9, 4), weeks=1)
        self.assertEqual((int(r['best']['dow']), int(r['best']['clock'])), (6, 6))
        self.assertEqual(sorted(set(r['windows']['clock'])), list(range(6, 18)))

    def test_block_is_scored_as_a_whole(self):
        # Single quietest hour Wed 03:00 between busy hours; a uniformly quiet block on Sunday
        quiet = {(2, 3): 10, (6, 2): 200, (6, 3): 200, (6, 4): 200, (6, 5): 200}
        df = frame('2023-09-04', 7, busy_except(quiet))
        r1 = scheduler.recommend(df, 'both', 'any', 1, datetime.date(2023, 9, 4), weeks=1)
        r4 = scheduler.recommend(df, 'both', 'any', 4, datetime.date(2023, 9, 4), weeks=1)
        self.assertEqual((int(r1['best']['dow']), int(r1['best']['clock'])), (2, 3))
        self.assertEqual((int(r4['best']['dow']), int(r4['best']['clock'])), (6, 2))

    def test_start_date_may_be_the_earliest_day_itself(self):
        df = frame('2023-09-04', 7, busy_except({(6, 3): 10}))
        r = scheduler.recommend(df, 'both', 'any', 1, datetime.date(2023, 9, 10), weeks=2)   # a Sunday
        self.assertEqual(r['start_date'], datetime.date(2023, 9, 10))
        self.assertEqual(r['end_date'], datetime.date(2023, 9, 24))
        self.assertEqual(r['first_window_start'], datetime.datetime(2023, 9, 10, 3))

    def test_holidays_in_project_period_are_listed(self):
        df = frame('2023-09-04', 7, busy_except({(1, 3): 10}))        # best: Tuesdays 03:00
        r = scheduler.recommend(df, 'both', 'any', 1, datetime.date(2023, 9, 25), weeks=3)
        self.assertEqual([d.isoformat() for d, _ in r['holidays']], ['2023-10-03'])
        self.assertEqual([d.isoformat() for d, _ in r['holidays_on_work_days']], ['2023-10-03'])

    def test_one_hour_any_shift_matches_v1_slot(self):
        # Without holidays or flags, v2 with 1-hour windows picks the same data slot as v1
        df = frame('2023-09-04', 14, lambda t: 300 + 100 * ((t.hour * 7 + t.dayofweek * 3) % 11))
        v1 = ours_v1(df, 9033, 'both', '24h (always)', datetime.date(2023, 9, 4))
        r = scheduler.recommend(df, 'both', 'any', 1, datetime.date(2023, 9, 4), weeks=1)
        self.assertEqual(pd.Timestamp(r['first_window_start']).dayofweek, v1['clock_start'].dayofweek)
        self.assertEqual(pd.Timestamp(r['first_window_start']).hour, v1['clock_start'].hour)
        self.assertAlmostEqual(float(r['best']['avg_traffic']), v1['expected'])

    def test_project_and_season_months(self):
        self.assertEqual(scheduler.project_months(datetime.date(2026, 12, 20), 3), {12, 1})
        self.assertEqual(scheduler.season_months({12}, 'season'), {11, 12, 1})
        self.assertEqual(scheduler.season_months({3}, 'month'), {3})

    def test_seasonal_profile_falls_back_when_data_is_thin(self):
        # January busy (2000), March quiet (500); only 1 week of data in March
        df = pd.concat([frame('2023-01-02', 28, lambda t: 2000), frame('2023-03-06', 7, lambda t: 500)])
        rows, _ = scheduler.prepare(df, 'R1')
        seasonal = scheduler.build_profile(rows, {3}, 'month', min_hours=1)
        self.assertTrue((seasonal['avg_traffic'] == 500).all())
        self.assertTrue((seasonal['source'] == 'season').all())
        thin = scheduler.build_profile(rows, {3}, 'month', min_hours=2)      # 1 hour per slot is too few
        self.assertTrue((thin['source'] == 'all').all())
        self.assertAlmostEqual(float(thin['avg_traffic'].iloc[0]), (4 * 2000 + 500) / 5)

    def test_expected_traffic_comes_from_the_estimate_profile(self):
        # Same weekly shape all year, but August twice as busy as the rest
        df = frame('2023-05-01', 140, lambda t: (2 if t.month == 8 else 1) * busy_except({(6, 3): 100})(t))
        aug = scheduler.recommend(df, 'R1', 'any', 1, datetime.date(2023, 8, 7), weeks=2)
        nov = scheduler.recommend(df, 'R1', 'any', 1, datetime.date(2023, 11, 6), weeks=2)
        self.assertEqual((int(aug['best']['dow']), int(aug['best']['clock'])), (6, 3))
        self.assertEqual((int(nov['best']['dow']), int(nov['best']['clock'])), (6, 3))
        self.assertGreater(aug['expected'], nov['expected'])
        self.assertAlmostEqual(aug['reduction'], 1 - aug['expected'] / float(aug['busiest']['avg_traffic']))
        weekly = scheduler.recommend(df, 'R1', 'any', 1, datetime.date(2023, 8, 7), weeks=2,
                                     estimate_profile='weekly')
        self.assertAlmostEqual(weekly['expected'], float(weekly['best']['avg_traffic']))

    def test_expected_range(self):
        self.assertEqual(scheduler.expected_range(100, {'window_ratio_p10': 0.5, 'window_ratio_p90': 1.5}), (50, 150))
        self.assertIsNone(scheduler.expected_range(100, None))

    def test_no_data_returns_none(self):
        df = frame('2023-09-04', 1, lambda t: 100).iloc[0:0]
        self.assertIsNone(scheduler.recommend(df, 'both', 'any', 1, datetime.date(2023, 9, 4), weeks=1))


if __name__ == '__main__':
    unittest.main()
