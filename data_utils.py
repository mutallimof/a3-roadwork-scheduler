import pandas as pd
import numpy as np
import glob
import os
import re
from typing import List, Optional, Tuple
from pyproj import Transformer


def fix_utm(value: str) -> float:
    """Parses a BASt UTM32 coordinate string into a float of meters.

    UTM coordinates use thousands-grouping in 3-digit blocks, but the last
    block may be shorter (decimal meters). This pads each block correctly
    instead of just stripping separators, which would corrupt values whose
    final block is shorter than 3 digits (e.g. "557.22" is 557220, not
    55722) — see analysis.ipynb for the documented mistake this replaced.
    """
    parts = str(value).split('.')
    fixed = parts[0] + ''.join(p.ljust(3, '0') if i == len(parts)-1 else p.zfill(3)
                                 for i, p in enumerate(parts[1:], 1))
    return float(fixed)


def discover_year_folders(base_path: str = '.') -> List[Tuple[int, int]]:
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


def load_year(year: int) -> pd.DataFrame:
    """Loads and concatenates every CSV inside a single year folder."""
    # os.path.join keeps this portable — a literal backslash glob only
    # matches on Windows and silently returns nothing on Mac/Linux.
    files = glob.glob(os.path.join(str(year), '*.csv'))
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


def load_traffic_data(min_stations: int = 5) -> pd.DataFrame:
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


def load_coordinates() -> pd.DataFrame:
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


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in kilometers.

    Accepts scalars or numpy arrays for the second point, so it can be used
    to compute one station's distance to every other station in a single
    vectorized call.
    """
    r = 6371.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(np.subtract(lat2, lat1))
    dlambda = np.radians(np.subtract(lon2, lon1))
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def nearest_station(coords: pd.DataFrame, station_id, max_km: float = 40.0) -> Optional[pd.Series]:
    """Finds the A3 station geographically closest to `station_id` (excluding itself).

    Used to define the "segment" a roadwork schedule applies to — the stretch
    of highway between the selected station and its nearest neighbor. Returns
    None if no other station is within max_km, so a sparse dataset doesn't
    produce a nonsensical, wildly-long "segment".
    """
    target = coords[coords['DZ_Nr'] == station_id].iloc[0]
    others = coords[coords['DZ_Nr'] != station_id].dropna(subset=['lat', 'lon']).copy()
    if others.empty:
        return None
    others['dist_km'] = haversine_km(target['lat'], target['lon'], others['lat'].values, others['lon'].values)
    nearest = others.sort_values('dist_km').iloc[0]
    if nearest['dist_km'] > max_km:
        return None
    return nearest