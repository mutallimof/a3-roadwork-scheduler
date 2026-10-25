import pandas as pd
import glob
import io
import os
import re
from pyproj import Transformer

# Data files are looked up next to this file, so the app works no matter
# which directory it is started from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Small extract of the real data, used when the full data is not present
SAMPLE_DIR = os.path.join(BASE_DIR, 'sample_data')

# Years the analysis uses (see analysis.ipynb): 2019 as the pre-COVID
# baseline and 2023. 2020-2022 were left out on purpose (COVID, and poor
# station coverage in 2022). Other year folders (e.g. 2018, 2022) may be
# present but are ignored unless configured, e.g. A3_YEARS=2018,2022,2023
# or A3_YEARS=all.
DEFAULT_YEARS = (2019, 2023)

# Station list files, in order of preference. Jawe2022.csv is what the
# original analysis used; Jawe2023.csv is the fallback.
STATION_FILES = ('Jawe2022.csv', 'Jawe2023.csv')

# Station number -> correct name, taken from Jawe2022.csv as printed in
# analysis.ipynb. Used to repair names that were damaged in a copy of
# Jawe2023.csv (umlauts replaced by U+FFFD).
STATION_NAMES_FILE = os.path.join(BASE_DIR, 'station_names.csv')

# Destination names used for the direction labels (from analysis.ipynb)
KNOWN_PLACE_NAMES = ('Würzburg', 'Nürnberg', 'Frankfurt a. Main', 'Passau', 'Linz (A)')

BAVARIA_LAND_NR = '9'
DAMAGED = '�'


def configured_years():
    """Returns the sorted list of years to use, or None for all years present."""
    value = os.environ.get('A3_YEARS', '').strip()
    if not value:
        return sorted(DEFAULT_YEARS)
    if value.lower() == 'all':
        return None
    return sorted(int(y) for y in re.split(r'[,\s]+', value) if y)


def fix_utm(value):
    # UTM coordinates use thousands-grouping in 3-digit blocks, but the last
    # block may be shorter (decimal meters). Pads each block correctly
    # instead of just stripping separators, which would corrupt some values.
    parts = str(value).split('.')
    fixed = parts[0] + ''.join(p.ljust(3, '0') if i == len(parts)-1 else p.zfill(3)
                                 for i, p in enumerate(parts[1:], 1))
    return float(fixed)


def discover_year_folders(base_path=BASE_DIR):
    """
    Scans base_path for folders named with exactly 4 digits (e.g. '2019',
    '2023', '2024') that contain at least one CSV file, and returns them
    as a sorted list of (year, file_count) tuples.
    """
    year_folders = []
    if not os.path.isdir(base_path):
        return year_folders
    for entry in os.listdir(base_path):
        full_path = os.path.join(base_path, entry)
        # Folder name must be exactly 4 digits to be treated as a year
        if os.path.isdir(full_path) and re.fullmatch(r'\d{4}', entry):
            csv_count = len(glob.glob(os.path.join(full_path, '*.csv')))
            if csv_count > 0:
                year_folders.append((int(entry), csv_count))
    return sorted(year_folders)


def find_station_file(base_path=BASE_DIR):
    for name in STATION_FILES:
        path = os.path.join(base_path, name)
        if os.path.exists(path):
            return path
    return None


def year_status(base_path=BASE_DIR, years=None):
    """
    Compares the configured years with the year folders present.
    Returns a dict with lists: configured (None = all), present, used,
    missing (configured but not present), ignored (present but not used).
    """
    if years is None:
        years = configured_years()
    present = [y for y, _ in discover_year_folders(base_path)]
    used = present if years is None else [y for y in years if y in present]
    return {
        'configured': years,
        'present': present,
        'used': used,
        'missing': [] if years is None else [y for y in years if y not in present],
        'ignored': [y for y in present if y not in used],
    }


def load_year(year, base_path=BASE_DIR):
    # Loads and concatenates every CSV inside a single year folder
    files = glob.glob(os.path.join(base_path, str(year), '*.csv'))
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


def resolve_data_dir(allow_sample=True):
    """
    Returns (data_dir, is_sample). The full data in the project folder is
    used if any of it is present (year folders or a Jawe station file), so
    a half-finished setup shows its real error instead of silently
    switching to the sample. Otherwise sample_data/ is used if it contains
    data.
    """
    full_present = bool(discover_year_folders(BASE_DIR)) or find_station_file(BASE_DIR) is not None
    if full_present or not allow_sample:
        return BASE_DIR, False
    if discover_year_folders(SAMPLE_DIR):
        return SAMPLE_DIR, True
    return BASE_DIR, False


def load_traffic_data(min_stations=5, base_path=BASE_DIR, years=None):
    """
    Loads the configured years (see configured_years) and combines them
    into one dataset. min_stations sets a threshold below which a year is
    flagged as a warning (likely incomplete data), without excluding it.
    Year folders that are present but not configured are ignored.
    """
    status = year_status(base_path, years)

    if not status['present']:
        raise FileNotFoundError("No year folders with CSV files found. Expected folders like '2019', '2023' etc.")
    if not status['used']:
        wanted = ', '.join(str(y) for y in status['configured'])
        found = ', '.join(str(y) for y in status['present'])
        raise FileNotFoundError(
            f"None of the configured years ({wanted}) is present. Year folders found: {found}. "
            f"Add the data for the configured years, or set A3_YEARS (e.g. A3_YEARS={found.replace(', ', ',')}).")
    for y in status['missing']:
        print(f"Warning: configured year {y} has no data folder; continuing without it.")
    for y in status['ignored']:
        print(f"Note: {y}/ is present but not configured; ignored.")

    all_dfs = []
    for year in status['used']:
        df_year = load_year(year, base_path)
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
    df['Datum'] = pd.to_datetime(df['Datum'].astype(str).str.strip().str.zfill(6), format='%y%m%d')

    # Combine both directions (KFZ already includes motorcycles)
    df['total_traffic'] = df['KFZ_R1'] + df['KFZ_R2']
    df['total_trucks'] = df['Lkw_R1'] + df['Lkw_R2']
    df['truck_ratio'] = df['total_trucks'] / df['total_traffic']

    # BASt quality flags for the vehicle counts, kept for the data checks
    for col in ('K_KFZ_R1', 'K_KFZ_R2'):
        df[col] = df[col].astype(str).str.strip() if col in df.columns else pd.NA

    # Direction columns kept separately too — used by the app for
    # direction-specific scoring (e.g. "only the Frankfurt-bound side")
    return df[['Datum', 'Wotag', 'Stunde', 'Zst', 'year',
                'total_traffic', 'total_trucks', 'truck_ratio',
                'KFZ_R1', 'KFZ_R2', 'Lkw_R1', 'Lkw_R2', 'K_KFZ_R1', 'K_KFZ_R2']]


def read_text_file(path):
    # BASt files are Latin-1. A copy of Jawe2023.csv is UTF-8 with damaged
    # umlauts (U+FFFD), so UTF-8 is tried first and Latin-1 is the fallback.
    with open(path, 'rb') as f:
        raw = f.read()
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('latin-1')


def load_reference_names(path=STATION_NAMES_FILE):
    if not os.path.exists(path):
        return {}
    ref = pd.read_csv(path, sep=';', encoding='utf-8', dtype=str)
    return dict(zip(ref['DZ_Nr'].astype(int), ref['DZ_Name']))


def _matches_damaged(damaged, candidate):
    # Same length; every intact character equal; every damaged character
    # stands for a non-ASCII character (umlauts, ß) in the candidate.
    return (len(damaged) == len(candidate)
            and all(d == c or (d == DAMAGED and ord(c) > 127) for d, c in zip(damaged, candidate)))


def repair_name(text, reference=None, known_words=()):
    """
    Repairs a name whose non-ASCII letters were replaced by U+FFFD.
    Returns (name, status) with status 'ok', 'repaired' or 'damaged'.
    A repair is only made when it can be checked: first against the
    reference name for the same station, then word by word against known
    words, where exactly one known word must fit. Nothing is guessed.
    """
    if not isinstance(text, str) or DAMAGED not in text:
        return text, 'ok'
    if reference and _matches_damaged(text, reference):
        return reference, 'repaired'
    words = text.split(' ')
    for i, word in enumerate(words):
        if DAMAGED in word:
            fits = {w for w in known_words if _matches_damaged(word, w)}
            if len(fits) == 1:
                words[i] = fits.pop()
    repaired = ' '.join(words)
    if DAMAGED in repaired:
        return repaired, 'damaged'
    return repaired, 'repaired'


def load_coordinates(base_path=BASE_DIR):
    """
    Loads station coordinates + metadata from the yearly-average file
    (Jawe2022.csv, or Jawe2023.csv as fallback), keeps the A3 in Bavaria,
    repairs damaged names where this can be checked, fixes the UTM
    formatting and converts to lat/lon.
    """
    path = find_station_file(base_path)
    if path is None:
        raise FileNotFoundError(f"No station file found in {base_path}: expected one of {', '.join(STATION_FILES)}")
    coords = pd.read_csv(io.StringIO(read_text_file(path)), sep=';', dtype=str)
    coords.columns = [c.strip() for c in coords.columns]
    coords = coords.apply(lambda s: s.str.strip())
    coords = coords[(coords['Str_Kl'] == 'A') & (coords['Str_Nr'] == '3')]
    # Jawe2023.csv covers the A3 in all of Germany; this app is for Bavaria
    if 'Land_Nr' in coords.columns:
        coords = coords[coords['Land_Nr'] == BAVARIA_LAND_NR]
    coords = coords[['DZ_Nr', 'DZ_Name', 'Koor_UTM32_E', 'Koor_UTM32_N',
                     'Fernziel_Ri1', 'Fernziel_Ri2']].copy()
    coords['DZ_Nr'] = coords['DZ_Nr'].astype(int)

    reference = load_reference_names()
    known_words = set(KNOWN_PLACE_NAMES)
    for name in reference.values():
        known_words.update(name.split(' '))
    names = [repair_name(n, reference.get(nr), known_words) for nr, n in zip(coords['DZ_Nr'], coords['DZ_Name'])]
    coords['DZ_Name'] = [n for n, _ in names]
    coords['name_status'] = [s for _, s in names]
    for col in ('Fernziel_Ri1', 'Fernziel_Ri2'):
        coords[col] = [repair_name(n, None, known_words)[0] if pd.notna(n) else n for n in coords[col]]
    # A name that could not be repaired is shown with '?' and its number, never guessed
    damaged = coords['name_status'] == 'damaged'
    coords.loc[damaged, 'DZ_Name'] = [f"{n.replace(DAMAGED, '?')} [{nr}, name damaged in source]"
                                      for n, nr in zip(coords.loc[damaged, 'DZ_Name'], coords.loc[damaged, 'DZ_Nr'])]
    for col in ('Fernziel_Ri1', 'Fernziel_Ri2'):
        coords[col] = coords[col].str.replace(DAMAGED, '?')

    coords['Koor_UTM32_E'] = coords['Koor_UTM32_E'].apply(fix_utm)
    coords['Koor_UTM32_N'] = coords['Koor_UTM32_N'].apply(fix_utm)

    transformer = Transformer.from_crs("EPSG:25832", "EPSG:4326")
    lat, lon = transformer.transform(coords['Koor_UTM32_E'].values, coords['Koor_UTM32_N'].values)
    coords['lat'] = lat
    coords['lon'] = lon
    coords.attrs['source_file'] = os.path.basename(path)

    return coords.reset_index(drop=True)


# Upper bound for a plausibility check: vehicles per hour in one direction.
# Three lanes carry roughly 6,000 vehicles/hour at most, so more than
# 10,000 in one hour and one direction is treated as impossible.
MAX_PLAUSIBLE_PER_DIRECTION = 10_000


def check_data(df):
    """
    Basic data checks, run when the app loads the data. Never raises.
    Returns (issues, per_station) where issues is a list of plain-text
    findings and per_station a DataFrame with one row per station-year.

    The quality-flag part follows the analysis in the aitraffic project
    (clean_data.py / data_report.md, github.com/DanieMyl/aitraffic):
    K_ columns mark hours BASt estimated ('s') or found implausible ('u').
    """
    issues = []
    rows = []
    for (zst, year), g in df.groupby(['Zst', 'year']):
        expected = 8784 if pd.Timestamp(year=int(year), month=12, day=31).dayofyear == 366 else 8760
        slots = g[['Datum', 'Stunde']].drop_duplicates()
        duplicates = len(g) - len(slots)
        missing_hours = max(expected - len(slots), 0)
        kfz = g[['KFZ_R1', 'KFZ_R2']]
        lkw = g[['Lkw_R1', 'Lkw_R2']]
        negative = int(((kfz < 0).any(axis=1) | (lkw < 0).any(axis=1)).sum())
        trucks_over_total = int(((g['Lkw_R1'] > g['KFZ_R1']) | (g['Lkw_R2'] > g['KFZ_R2'])).sum())
        too_high = int((kfz > MAX_PLAUSIBLE_PER_DIRECTION).any(axis=1).sum())
        empty = int(kfz.isna().any(axis=1).sum())
        flags = pd.concat([g['K_KFZ_R1'], g['K_KFZ_R2']]).dropna()
        flags = flags[flags.isin(['-', 's', 'u', 'z'])]
        estimated = float((flags == 's').mean()) if len(flags) else float('nan')
        implausible = int((flags == 'u').sum())
        rows.append(dict(station=int(zst), year=int(year), rows=len(g), missing_hours=missing_hours,
                         duplicate_rows=duplicates, empty_counts=empty, negative_values=negative,
                         trucks_above_total=trucks_over_total, above_max=too_high,
                         estimated_share=estimated, implausible_flags=implausible))
    per_station = pd.DataFrame(rows)
    if per_station.empty:
        return ["No traffic rows to check."], per_station

    def report(col, text):
        bad = per_station[per_station[col] > 0]
        if len(bad):
            where = ', '.join(f"{r.station}/{r.year}" for r in bad.itertuples())
            issues.append(f"{text}: {int(bad[col].sum()):,} in {len(bad)} station-year(s) ({where})")

    report('missing_hours', "Missing hours")
    report('duplicate_rows', "Duplicate hours")
    report('empty_counts', "Hours without a vehicle count")
    report('negative_values', "Hours with negative counts")
    report('trucks_above_total', "Hours with more trucks than vehicles")
    report('above_max', f"Hours above {MAX_PLAUSIBLE_PER_DIRECTION:,} vehicles in one direction")
    report('implausible_flags', "Counts flagged implausible by BASt ('u')")
    return issues, per_station
