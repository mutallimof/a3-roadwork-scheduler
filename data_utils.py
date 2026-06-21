import pandas as pd
import glob
import os
import re
from pyproj import Transformer


def fix_utm(value):
    # UTM coordinates use thousands-grouping in 3-digit blocks, but the last
    # block may be shorter (decimal meters). Pads each block correctly
    # instead of just stripping separators, which would corrupt some values.
    parts = str(value).split('.')
    fixed = parts[0] + ''.join(p.ljust(3, '0') if i == len(parts)-1 else p.zfill(3)
                                 for i, p in enumerate(parts[1:], 1))
    return float(fixed)


def discover_year_folders(base_path='.'):
    """
    Scans base_path for folders named with exactly 4 digits (e.g. '2019',
    '2023', '2024') that contain at least one CSV file, and returns them
    as a sorted list of (year, file_count) tuples.
    """
    year_folders = []
    for entry in os.listdir(base_path):
        full_path = os.path.join(base_path, entry)
        # Folder name must be exactly 4 digits to be treated as a year
        if os.path.isdir(full_path) and re.fullmatch(r'\d{4}', entry):
            csv_count = len(glob.glob(os.path.join(full_path, '*.csv')))
            if csv_count > 0:
                year_folders.append((int(entry), csv_count))
    return sorted(year_folders)


def load_year(year):
    # Loads and concatenates every CSV inside a single year folder
    files = glob.glob(f'{year}\\*.csv')
    dfs = []
    for f in files:
        try:
            d = pd.read_csv(f, sep=';', encoding='latin-1')
            d['year'] = year
            dfs.append(d)
        except Exception as e:
            print(f"Skipped {f}: {e}")
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


def load_traffic_data(min_stations=5):
    """
    Loads every year folder currently present and combines them into one
    dataset. min_stations sets a threshold below which a year is flagged
    as a warning (likely incomplete data), without excluding it — that
    decision is left to whoever manages the data folders.
    """
    available_years = discover_year_folders()

    if not available_years:
        raise FileNotFoundError("No year folders with CSV files found. Expected folders like '2019', '2023' etc.")

    all_dfs = []
    for year, file_count in available_years:
        df_year = load_year(year)
        if df_year.empty:
            print(f"Warning: {year} folder found but no usable CSVs loaded.")
            continue

        n_stations = df_year['Zst'].nunique()
        if n_stations < min_stations:
            print(f"Warning: {year} has only {n_stations} stations — data may be incomplete.")

        print(f"Loaded {year}: {len(df_year)} rows, {n_stations} stations")
        all_dfs.append(df_year)

    if not all_dfs:
        raise ValueError("No usable data loaded. Check your year folders.")

    df = pd.concat(all_dfs, ignore_index=True)

    # Parse date (format is YYMMDD)
    df['Datum'] = pd.to_datetime(df['Datum'], format='%y%m%d')

    # Combine both directions (KFZ already includes motorcycles)
    df['total_traffic'] = df['KFZ_R1'] + df['KFZ_R2']
    df['total_trucks'] = df['Lkw_R1'] + df['Lkw_R2']
    df['truck_ratio'] = df['total_trucks'] / df['total_traffic']

    # Direction columns kept separately too — used by the app for
    # direction-specific scoring (e.g. "only the Frankfurt-bound side")
    return df[['Datum', 'Wotag', 'Stunde', 'Zst', 'year',
                'total_traffic', 'total_trucks', 'truck_ratio',
                'KFZ_R1', 'KFZ_R2', 'Lkw_R1', 'Lkw_R2']]


def load_coordinates():
    # Loads station coordinates + metadata from the yearly-average file,
    # filters to A3 only, fixes the UTM formatting, converts to lat/lon
    coords = pd.read_csv('Jawe2022.csv', sep=';', encoding='latin-1')
    coords = coords[['DZ_Nr', 'DZ_Name', 'Str_Kl', 'Str_Nr',
                      'Koor_UTM32_E', 'Koor_UTM32_N',
                      'Fernziel_Ri1', 'Fernziel_Ri2']]
    coords = coords[(coords['Str_Kl'] == 'A') & (coords['Str_Nr'] == 3)]

    coords['Koor_UTM32_E'] = coords['Koor_UTM32_E'].astype(str).apply(fix_utm)
    coords['Koor_UTM32_N'] = coords['Koor_UTM32_N'].astype(str).apply(fix_utm)

    transformer = Transformer.from_crs("EPSG:25832", "EPSG:4326")
    lat, lon = transformer.transform(coords['Koor_UTM32_E'].values, coords['Koor_UTM32_N'].values)
    coords['lat'] = lat
    coords['lon'] = lon

    return coords