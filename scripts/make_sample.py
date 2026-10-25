"""
make_sample.py

Builds sample_data/ from the full BASt data in the project folder, so the
app can run without any downloads (it switches to sample_data/ when the
full data is missing).

The sample is an unmodified subset of the real files:
  - a few A3 stations (default: the 3 with the most rows in the chosen year)
  - a few months of hourly rows (default: March to June)
  - only the columns the app uses
  - Jawe2022.csv reduced to the A3 rows and the columns the app uses

Usage:
    python scripts/make_sample.py
    python scripts/make_sample.py --year 2023 --months 3 4 5 6 --stations 9033 9040 9081
"""

import argparse
import os
import shutil
import sys

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
from data_utils import BASE_DIR, SAMPLE_DIR, load_year  # noqa: E402

HOURLY_COLUMNS = ['Zst', 'Datum', 'Wotag', 'Stunde', 'KFZ_R1', 'KFZ_R2', 'Lkw_R1', 'Lkw_R2']
JAWE_COLUMNS = ['DZ_Nr', 'DZ_Name', 'Str_Kl', 'Str_Nr', 'Koor_UTM32_E', 'Koor_UTM32_N',
                'Fernziel_Ri1', 'Fernziel_Ri2']


def main():
    parser = argparse.ArgumentParser(description="Build sample_data/ from the full data.")
    parser.add_argument('--year', type=int, default=2023)
    parser.add_argument('--months', type=int, nargs='+', default=[3, 4, 5, 6])
    parser.add_argument('--stations', type=int, nargs='+',
                        help="station numbers (default: the 3 with the most rows in --year)")
    args = parser.parse_args()

    jawe_path = os.path.join(BASE_DIR, 'Jawe2022.csv')
    if not os.path.exists(jawe_path):
        print("ERROR: Jawe2022.csv not found in the project folder. Run scripts/fetch_data.py first.")
        return 1

    df = load_year(args.year)
    if df.empty:
        print(f"ERROR: no data in {args.year}/. Run scripts/fetch_data.py first.")
        return 1

    stations = args.stations or df['Zst'].value_counts().head(3).index.tolist()
    month = (df['Datum'].astype(str).str.strip().str[2:4]).astype(int)
    sample = df[df['Zst'].isin(stations) & month.isin(args.months)][HOURLY_COLUMNS]
    if sample.empty:
        print(f"ERROR: no rows for stations {stations} in months {args.months} of {args.year}.")
        return 1

    if os.path.isdir(SAMPLE_DIR):
        shutil.rmtree(SAMPLE_DIR)
    year_dir = os.path.join(SAMPLE_DIR, str(args.year))
    os.makedirs(year_dir)
    for zst, part in sample.groupby('Zst'):
        part.to_csv(os.path.join(year_dir, f"zst{zst}_{args.year}.csv"), sep=';', index=False, encoding='latin-1')

    jawe = pd.read_csv(jawe_path, sep=';', encoding='latin-1', dtype=str)
    jawe = jawe[(jawe['Str_Kl'].str.strip() == 'A') & (jawe['Str_Nr'].str.strip() == '3')][JAWE_COLUMNS]
    jawe.to_csv(os.path.join(SAMPLE_DIR, 'Jawe2022.csv'), sep=';', index=False, encoding='latin-1')

    size = sum(os.path.getsize(os.path.join(root, f)) for root, _, files in os.walk(SAMPLE_DIR) for f in files)
    print(f"Wrote {SAMPLE_DIR}")
    print(f"  stations: {sorted(int(s) for s in sample['Zst'].unique())}")
    print(f"  months: {sorted(args.months)} of {args.year}, {len(sample):,} hourly rows")
    print(f"  Jawe2022.csv: {len(jawe)} A3 stations")
    print(f"  total size: {size / 1e6:.2f} MB")
    return 0


if __name__ == '__main__':
    sys.exit(main())
