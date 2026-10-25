"""
Tests for the data loader, the data checks, the name repair and
scripts/fetch_data.py.

All test files are small GENERATED files in the BASt layout, written to a
temporary folder. They are not real traffic data.

Run:  python -m unittest discover -s tests -v
"""

import contextlib
import io
import os
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, 'scripts'))

import data_utils as du  # noqa: E402
import fetch_data  # noqa: E402

D = du.DAMAGED


def hourly_frame(zst, year, days=2, road=('A', '3')):
    """Generated hourly rows for one station: `days` full days from 1 January."""
    rows = []
    for d in pd.date_range(f'{year}-01-01', periods=days, freq='D'):
        for h in range(1, 25):
            rows.append(dict(Zst=zst, Strklas=road[0], Strnum=road[1], Datum=d.strftime('%y%m%d'),
                             Wotag=d.weekday() + 1, Stunde=h, KFZ_R1=100 + h, K_KFZ_R1='-',
                             KFZ_R2=110 + h, K_KFZ_R2='-', Lkw_R1=10, Lkw_R2=12))
    return pd.DataFrame(rows)


def write_hourly(base, zst, year, df=None, **kw):
    os.makedirs(os.path.join(base, str(year)), exist_ok=True)
    df = hourly_frame(zst, year, **kw) if df is None else df
    df.to_csv(os.path.join(base, str(year), f'zst{zst}_{year}.csv'), sep=';', index=False, encoding='latin-1')
    return df


JAWE_HEADER = 'DZ_Nr;DZ_Name;Land_Nr;Str_Kl;Str_Nr;Koor_UTM32_E;Koor_UTM32_N;Fernziel_Ri1;Fernziel_Ri2\n'


def write_jawe(base, name, rows, encoding):
    with open(os.path.join(base, name), 'w', encoding=encoding) as f:
        f.write(JAWE_HEADER + ''.join(';'.join(r) + '\n' for r in rows))


class ConfiguredYearsTest(unittest.TestCase):
    def test_default_is_2019_and_2023(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(du.configured_years(), [2019, 2023])

    def test_env_list_and_all(self):
        with mock.patch.dict(os.environ, {'A3_YEARS': '2023, 2018'}):
            self.assertEqual(du.configured_years(), [2018, 2023])
        with mock.patch.dict(os.environ, {'A3_YEARS': 'all'}):
            self.assertIsNone(du.configured_years())


class LoaderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()

    def tearDown(self):
        self.quiet.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_year_status_missing_and_ignored(self):
        write_hourly(self.base, 9033, 2018)
        write_hourly(self.base, 9033, 2023)
        s = du.year_status(self.base, [2019, 2023])
        self.assertEqual(s['used'], [2023])
        self.assertEqual(s['missing'], [2019])
        self.assertEqual(s['ignored'], [2018])

    def test_loads_only_configured_years(self):
        write_hourly(self.base, 9033, 2018)
        write_hourly(self.base, 9033, 2022)
        write_hourly(self.base, 9033, 2023)
        df = du.load_traffic_data(base_path=self.base, years=[2019, 2023])
        self.assertEqual(sorted(df['year'].unique()), [2023])
        self.assertEqual(len(df), 48)
        self.assertEqual(df['Datum'].min(), pd.Timestamp('2023-01-01'))
        self.assertTrue((df['total_traffic'] == df['KFZ_R1'] + df['KFZ_R2']).all())

    def test_no_configured_year_present_raises_clear_error(self):
        write_hourly(self.base, 9033, 2018)
        with self.assertRaises(FileNotFoundError) as ctx:
            du.load_traffic_data(base_path=self.base, years=[2019, 2023])
        self.assertIn('A3_YEARS', str(ctx.exception))

    def test_files_without_quality_flags_still_load(self):
        df = hourly_frame(9033, 2023).drop(columns=['K_KFZ_R1', 'K_KFZ_R2'])
        write_hourly(self.base, 9033, 2023, df=df)
        out = du.load_traffic_data(base_path=self.base, years=[2023])
        self.assertIn('K_KFZ_R1', out.columns)


class NameRepairTest(unittest.TestCase):
    def test_repair_from_reference(self):
        self.assertEqual(du.repair_name(f'AK N{D}rnberg (O)', 'AK Nürnberg (O)'), ('AK Nürnberg (O)', 'repaired'))

    def test_reference_that_does_not_fit_is_not_used(self):
        name, status = du.repair_name(f'AK N{D}rnberg (O)', 'AK Fürth (O)')
        self.assertEqual(status, 'damaged')
        self.assertIn(D, name)

    def test_word_repair_needs_exactly_one_fit(self):
        self.assertEqual(du.repair_name(f'W{D}rzburg', None, {'Würzburg', 'Nürnberg'}), ('Würzburg', 'repaired'))
        self.assertEqual(du.repair_name(f'M{D}hle', None, {'Mühle', 'Möhle'})[1], 'damaged')

    def test_compound_words_are_matched_by_part(self):
        known = du.known_words_from({9521: 'AS Nürnberg/Behringersd.'})
        self.assertEqual(du.repair_name(f'AS N{D}rnberg/Behringersdorf (B14)', None, known),
                         ('AS Nürnberg/Behringersdorf (B14)', 'repaired'))
        self.assertEqual(du.repair_name(f'AS N{D}rnberg-M{D}geldorf', None, known)[1], 'damaged')

    def test_intact_name_is_unchanged(self):
        self.assertEqual(du.repair_name('AD Seligenstadt (O)', 'other'), ('AD Seligenstadt (O)', 'ok'))


class CoordinatesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_jawe2023_utf8_damaged_bavaria_only(self):
        write_jawe(self.base, 'Jawe2023.csv', [
            ['9040', f'AK N{D}rnberg (O)', '9', 'A', '3', '649.440', '5.488.130', f'N{D}rnberg', 'Passau'],
            ['9999', f'Unbekannt {D}rt', '9', 'A', '3', '600.100', '5.500.000', 'Passau', f'W{D}rzburg'],
            ['5672', 'AD Heumar (N)', '5', 'A', '3', '362.914', '5.644.366', 'Oberhausen', 'Köln'],
            ['7001', 'A7 Station', '9', 'A', '7', '560.100', '5.500.000', 'a', 'b'],
        ], 'utf-8')
        c = du.load_coordinates(self.base).set_index('DZ_Nr')
        self.assertEqual(sorted(c.index), [9040, 9999])          # Bavaria and A3 only
        self.assertEqual(c.at[9040, 'DZ_Name'], 'AK Nürnberg (O)')
        self.assertEqual(c.at[9040, 'name_status'], 'repaired')
        self.assertEqual(c.at[9040, 'Fernziel_Ri1'], 'Nürnberg')
        self.assertEqual(c.at[9999, 'name_status'], 'damaged')  # no reference, not guessed
        self.assertIn('9999', c.at[9999, 'DZ_Name'])
        self.assertNotIn(D, c.at[9999, 'DZ_Name'])
        self.assertEqual(c.at[9999, 'Fernziel_Ri2'], 'Würzburg')
        self.assertTrue(48 < c.at[9040, 'lat'] < 51 and 9 < c.at[9040, 'lon'] < 14)

    def test_jawe2022_latin1_is_preferred(self):
        write_jawe(self.base, 'Jawe2022.csv', [
            ['9033', 'AD Seligenstadt (O)', '9', 'A', '3', '502.145', '5.537.327', 'Frankfurt a. Main', 'Würzburg']],
            'latin-1')
        write_jawe(self.base, 'Jawe2023.csv', [
            ['9040', 'AK Nürnberg (O)', '9', 'A', '3', '649.440', '5.488.130', 'Nürnberg', 'Passau']], 'utf-8')
        c = du.load_coordinates(self.base)
        self.assertEqual(c.attrs['source_file'], 'Jawe2022.csv')
        self.assertEqual(c['DZ_Name'].tolist(), ['AD Seligenstadt (O)'])
        self.assertEqual(c['Fernziel_Ri2'].tolist(), ['Würzburg'])


class CheckDataTest(unittest.TestCase):
    def frame(self, raw):
        raw = raw.copy()
        raw['year'] = 2023
        raw['Datum'] = pd.to_datetime(raw['Datum'], format='%y%m%d')
        return raw

    def test_clean_partial_data_has_no_findings_when_not_full_year(self):
        issues, per = du.check_data(self.frame(hourly_frame(9033, 2023, days=3)), full_year=False)
        self.assertEqual(issues, [])
        self.assertEqual(per.loc[0, 'missing_hours'], 0)

    def test_full_year_expected(self):
        issues, per = du.check_data(self.frame(hourly_frame(9033, 2023, days=3)))
        self.assertEqual(per.loc[0, 'missing_hours'], 8760 - 72)
        self.assertTrue(any(i.startswith('Missing hours') for i in issues))

    def test_detects_problems(self):
        raw = hourly_frame(9033, 2023, days=3)
        raw = raw.drop(index=5)                                   # one missing hour
        raw = pd.concat([raw, raw.iloc[[0]]])                     # one duplicate hour
        raw.iloc[1, raw.columns.get_loc('KFZ_R1')] = -1           # negative
        raw.iloc[2, raw.columns.get_loc('Lkw_R2')] = 1000         # trucks above total
        raw.iloc[3, raw.columns.get_loc('KFZ_R2')] = 20_000       # impossible
        raw.iloc[4, raw.columns.get_loc('K_KFZ_R1')] = 'u'        # flagged implausible
        raw.iloc[6, raw.columns.get_loc('K_KFZ_R2')] = 's'        # estimated
        issues, per = du.check_data(self.frame(raw), full_year=False)
        row = per.iloc[0]
        self.assertEqual(row['missing_hours'], 1)
        self.assertEqual(row['duplicate_rows'], 1)
        self.assertEqual(row['negative_values'], 1)
        self.assertEqual(row['trucks_above_total'], 2)            # the negative KFZ row counts too
        self.assertEqual(row['above_max'], 1)
        self.assertEqual(row['implausible_flags'], 1)
        self.assertGreater(row['estimated_share'], 0)
        self.assertEqual(len(issues), 6)

    def test_never_raises_on_empty(self):
        issues, per = du.check_data(self.frame(hourly_frame(9033, 2023, days=1)).iloc[0:0])
        self.assertTrue(per.empty)
        self.assertEqual(len(issues), 1)


class FetchDataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = os.path.join(self.tmp.name, 'project')
        self.raw = os.path.join(self.project, 'raw_data')
        os.makedirs(self.raw)

    def tearDown(self):
        self.tmp.cleanup()

    def run_fetch(self, *extra):
        out = io.StringIO()
        with mock.patch.object(fetch_data, 'PROJECT_DIR', self.project), \
             mock.patch.object(sys, 'argv', ['fetch_data.py', '--source-dir', self.raw, *extra]), \
             contextlib.redirect_stdout(out):
            code = fetch_data.main()
        return code, out.getvalue()

    def zip_csv(self, path, member, df):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr(member, df.to_csv(sep=';', index=False).encode('latin-1'))

    def test_builds_layout_from_zips_subfolders_and_skips_duplicates(self):
        a = hourly_frame(9033, 2018)
        self.zip_csv(os.path.join(self.raw, '2018', 'zst9033.zip'), 'zst9033_2018.csv', a)
        os.makedirs(os.path.join(self.raw, '2023', 'zst9040'))
        hourly_frame(9040, 2023).to_csv(os.path.join(self.raw, '2023', 'zst9040', 'zst9040_2023.csv'),
                                        sep=';', index=False, encoding='latin-1')
        a.to_csv(os.path.join(self.raw, 'copy_zst9033_2018.csv'), sep=';', index=False, encoding='latin-1')
        changed = a.copy()
        changed['KFZ_R1'] += 1
        self.zip_csv(os.path.join(self.raw, 'other.zip'), 'zst9033_2018_v2.csv', changed)
        # Bulk file with another road: must be filtered out
        hourly_frame(7001, 2023, road=('A', '7')).to_csv(os.path.join(self.raw, 'bulk.csv'), sep=';',
                                                          index=False, encoding='latin-1')
        with open(os.path.join(self.raw, 'Jawe2023.csv'), 'w', encoding='utf-8') as f:
            f.write(JAWE_HEADER)

        code, out = self.run_fetch()
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(os.listdir(os.path.join(self.project, '2018'))), ['zst9033_2018.csv'])
        self.assertEqual(sorted(os.listdir(os.path.join(self.project, '2023'))), ['zst9040_2023.csv'])
        self.assertTrue(os.path.exists(os.path.join(self.project, 'Jawe2023.csv')))
        self.assertFalse(os.path.exists(os.path.join(self.project, 'Jawe2022.csv')))
        self.assertIn('identical content', out)
        self.assertIn('DIFFERENT content', out)
        written = pd.read_csv(os.path.join(self.project, '2018', 'zst9033_2018.csv'), sep=';', encoding='latin-1')
        self.assertEqual(len(written), len(a))                    # duplicates not appended
        self.assertEqual(written['KFZ_R1'].tolist(), a['KFZ_R1'].tolist())

        code, out = self.run_fetch()                             # second run: nothing rewritten
        self.assertEqual(code, 0, out)
        self.assertIn('already present', out)

    def test_station_list_is_reduced_to_bavarian_a3_and_repaired(self):
        rows = [['9040', f'AK N{D}rnberg (O)', '9', 'A', '3', '649.440', '5.488.130', f'N{D}rnberg', 'Passau'],
                ['5672', 'AD Heumar (N)', '5', 'A', '3', '362.914', '5.644.366', 'Oberhausen', 'Köln'],
                ['7001', 'A7 Station', '9', 'A', '7', '560.100', '5.500.000', 'a', 'b']]
        with open(os.path.join(self.raw, 'Jawe2023.csv'), 'w', encoding='utf-8') as f:
            f.write(JAWE_HEADER + ''.join(';'.join(r) + '\n' for r in rows))
        hourly_frame(9040, 2023).to_csv(os.path.join(self.raw, 'zst9040_2023.csv'), sep=';', index=False,
                                        encoding='latin-1')
        code, out = self.run_fetch()
        self.assertEqual(code, 0, out)
        written = pd.read_csv(os.path.join(self.project, 'Jawe2023.csv'), sep=';', encoding='latin-1', dtype=str)
        self.assertEqual(written['DZ_Nr'].tolist(), ['9040'])
        self.assertEqual(written['DZ_Name'].tolist(), ['AK Nürnberg (O)'])
        self.assertEqual(written['Fernziel_Ri1'].tolist(), ['Nürnberg'])
        self.assertIn('1 of 3 rows', out)

    def test_empty_source_folder_fails_with_instructions(self):
        code, out = self.run_fetch()
        self.assertEqual(code, 1)
        self.assertIn('How to get the files', out)


if __name__ == '__main__':
    unittest.main()
