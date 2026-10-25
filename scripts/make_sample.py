"""
make_sample.py

Builds sample_data/ from the full BASt data in the project folder, so the
app can run without any downloads (it switches to sample_data/ when the
full data is missing).

The sample is an unmodified subset of the real files:
  - a few A3 stations (default: 9033 AD Seligenstadt, 9040 AK Nürnberg and
    9093 AK Deggendorf, i.e. the west, middle and east of the Bavarian A3)
  - a few months of hourly rows (default: March to June)
  - only the columns the app uses, plus the BASt quality flags
  - the station list (Jawe2022.csv or Jawe2023.csv) reduced to the A3 in
    Bavaria and the columns the app uses; station and destination names
    are the repaired ones from data_utils.load_coordinates()

Usage:
    python scripts/make_sample.py
    python scripts/make_sample.py --year 2023 --months 3 4 5 6 --stations 9033 9040 9093
"""

import argparse
import os
import shutil
import sys

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
import io  # noqa: E402

from data_utils import (BASE_DIR, SAMPLE_DIR, BAVARIA_LAND_NR, find_station_file,  # noqa: E402
                        load_coordinates, load_year, read_text_file)

HOURLY_COLUMNS = ['Zst', 'Datum', 'Wotag', 'Stunde', 'KFZ_R1', 'K_KFZ_R1', 'KFZ_R2', 'K_KFZ_R2',
                  'Lkw_R1', 'Lkw_R2']
JAWE_COLUMNS = ['DZ_Nr', 'DZ_Name', 'Land_Nr', 'Str_Kl', 'Str_Nr', 'Koor_UTM32_E', 'Koor_UTM32_N',
                'Fernziel_Ri1', 'Fernziel_Ri2']
DEFAULT_STATIONS = [9033, 9040, 9093]


def main():
    parser = argparse.ArgumentParser(description="Build sample_data/ from the full data.")
    parser.add_argument('--year', type=int, default=2023)
    parser.add_argument('--months', type=int, nargs='+', default=[3, 4, 5, 6])
    parser.add_argument('--stations', type=int, nargs='+',
                        help=f"station numbers (default: {' '.join(map(str, DEFAULT_STATIONS))})")
    args = parser.parse_args()

    jawe_path = find_station_file(BASE_DIR)
    if jawe_path is None:
        print("ERROR: no Jawe station list in the project folder. Run scripts/fetch_data.py first.")
        return 1

    df = load_year(args.year)
    if df.empty:
        print(f"ERROR: no data in {args.year}/. Run scripts/fetch_data.py first.")
        return 1

    stations = args.stations or DEFAULT_STATIONS
    df.columns = [c.strip() for c in df.columns]
    month = (df['Datum'].astype(str).str.strip().str.zfill(6).str[2:4]).astype(int)
    sample = df[df['Zst'].isin(stations) & month.isin(args.months)][HOURLY_COLUMNS].copy()
    for col in ('K_KFZ_R1', 'K_KFZ_R2'):
        sample[col] = sample[col].astype(str).str.strip()
    if sample.empty:
        print(f"ERROR: no rows for stations {stations} in months {args.months} of {args.year}.")
        return 1

    if os.path.isdir(SAMPLE_DIR):
        shutil.rmtree(SAMPLE_DIR)
    year_dir = os.path.join(SAMPLE_DIR, str(args.year))
    os.makedirs(year_dir)
    for zst, part in sample.groupby('Zst'):
        part.to_csv(os.path.join(year_dir, f"zst{zst}_{args.year}.csv"), sep=';', index=False, encoding='latin-1')

    jawe = pd.read_csv(io.StringIO(read_text_file(jawe_path)), sep=';', dtype=str)
    jawe.columns = [c.strip() for c in jawe.columns]
    jawe = jawe.apply(lambda s: s.str.strip())
    jawe = jawe[(jawe['Str_Kl'] == 'A') & (jawe['Str_Nr'] == '3')]
    if 'Land_Nr' in jawe.columns:
        jawe = jawe[jawe['Land_Nr'] == BAVARIA_LAND_NR]
    else:
        jawe['Land_Nr'] = BAVARIA_LAND_NR
    jawe = jawe[JAWE_COLUMNS].copy()
    # Write the repaired names, so the sample does not carry damaged umlauts
    names = load_coordinates(BASE_DIR).set_index('DZ_Nr')
    nr = jawe['DZ_Nr'].astype(int)
    for col in ('DZ_Name', 'Fernziel_Ri1', 'Fernziel_Ri2'):
        jawe[col] = nr.map(names[col]).fillna(jawe[col])
    jawe_name = os.path.basename(jawe_path)
    jawe.to_csv(os.path.join(SAMPLE_DIR, jawe_name), sep=';', index=False, encoding='latin-1', errors='replace')

    size = sum(os.path.getsize(os.path.join(root, f)) for root, _, files in os.walk(SAMPLE_DIR) for f in files)
    print(f"Wrote {SAMPLE_DIR}")
    print(f"  stations: {sorted(int(s) for s in sample['Zst'].unique())}")
    print(f"  months: {sorted(args.months)} of {args.year}, {len(sample):,} hourly rows")
    print(f"  {jawe_name}: {len(jawe)} A3 stations in Bavaria")
    print(f"  total size: {size / 1e6:.2f} MB")
    return 0


if __name__ == '__main__':
    sys.exit(main())
