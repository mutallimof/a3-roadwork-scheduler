"""
fetch_data.py

Puts the BASt data into the folders the app expects:

    <project>/2019/zst<station>_2019.csv   (one file per A3 station and year)
    <project>/2023/zst<station>_2023.csv
    <project>/Jawe2022.csv

BASt's download pages are browser pages, and this script does not guess
their file URLs. Instead it processes files you have downloaded into a
local folder (default: raw_data/ in the project folder):

  - .zip files and .csv files with BASt hourly counts. Both per-station
    files (e.g. zst9033_2019.csv) and large files with many stations work;
    only A3 stations are kept when the file has road columns
    (Strklas/Strnum).
  - Jawe2022.csv (or a zip containing it) with station coordinates.

If you have direct download URLs, pass them with --url and they are
downloaded into the same folder first.

Files that already exist in the target folders are skipped, so the script
can be run again safely. Use --force to rewrite them.

Usage:
    python scripts/fetch_data.py
    python scripts/fetch_data.py --source-dir C:\\Users\\me\\Downloads\\bast
    python scripts/fetch_data.py --url https://.../file.zip --url https://.../Jawe2022.csv
"""

import argparse
import io
import os
import shutil
import sys
import urllib.request
import zipfile

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SOURCE_DIR = os.path.join(PROJECT_DIR, 'raw_data')
DEFAULT_YEARS = [2019, 2023]

# Columns the app needs from an hourly file (the rest are kept as they are)
REQUIRED_COLUMNS = {'Zst', 'Datum', 'Wotag', 'Stunde', 'KFZ_R1', 'KFZ_R2', 'Lkw_R1', 'Lkw_R2'}

MANUAL_STEPS = f"""
How to get the files (manual download):

  1. Hourly counts ("Stundenwerte") for 2019 and 2023, from the BASt pages
     linked in the README:
       https://open.bydata.de/datasets?locale=de&query=Autobahn+Z%C3%A4hlstellen+A3
       https://www.bast.de/DE/Themen/Digitales/HF_1/Massnahmen/verkehrszaehlung/Stundenwerte.html
     Download the zip (or CSV) files for the A3 stations, or the full-year
     file, for each year.
  2. Station data "Jawe2022.csv" from:
       https://www.bast.de/DE/Themen/Digitales/HF_1/Massnahmen/verkehrszaehlung/Daten/2022_1/Jawe2022.html?nn=414410
  3. Put all downloaded files, still zipped is fine, into one folder,
     by default:
       {DEFAULT_SOURCE_DIR}
  4. Run this script again.
"""


def log(msg):
    print(msg, flush=True)


def download(urls, source_dir):
    ok = True
    for url in urls:
        name = os.path.basename(url.split('?')[0]) or 'download'
        target = os.path.join(source_dir, name)
        if os.path.exists(target):
            log(f"  skip download, already present: {name}")
            continue
        log(f"  downloading {url}")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'a3-roadwork-scheduler/fetch_data'})
            with urllib.request.urlopen(req, timeout=120) as r, open(target + '.part', 'wb') as f:
                shutil.copyfileobj(r, f)
            os.replace(target + '.part', target)
        except Exception as e:
            ok = False
            if os.path.exists(target + '.part'):
                os.remove(target + '.part')
            log(f"  ERROR: could not download {url}: {e}")
            log(f"         If the site needs a browser, download it manually into {source_dir}.")
    return ok


def iter_csv_sources(source_dir, bad_files):
    """Yields (label, opener) for every CSV in source_dir, including CSVs inside zips."""
    for name in sorted(os.listdir(source_dir)):
        path = os.path.join(source_dir, name)
        lower = name.lower()
        if lower.endswith('.csv'):
            yield name, (lambda p=path: open(p, 'rb'))
        elif lower.endswith('.zip'):
            try:
                zf = zipfile.ZipFile(path)
            except zipfile.BadZipFile:
                log(f"  ERROR: {name} is not a valid zip file (incomplete download?). Skipped.")
                bad_files.append(name)
                continue
            for member in zf.namelist():
                if member.lower().endswith('.csv') and not member.startswith('__MACOSX'):
                    yield f"{name}/{member}", (lambda z=zf, m=member: io.BytesIO(z.read(m)))


def read_header(opener):
    with opener() as f:
        first = f.readline().decode('latin-1')
    return [c.strip() for c in first.strip().split(';')]


def handle_jawe(label, opener, force):
    target = os.path.join(PROJECT_DIR, 'Jawe2022.csv')
    if os.path.exists(target) and not force:
        log(f"  skip {label}: Jawe2022.csv already present")
        return True
    with opener() as src, open(target, 'wb') as dst:
        shutil.copyfileobj(src, dst)
    log(f"  wrote Jawe2022.csv (from {label})")
    return True


def handle_hourly(label, opener, years, force, existing_before, written):
    """Splits an hourly file into <year>/zst<station>_<year>.csv for A3 stations."""
    header = read_header(opener)
    missing = REQUIRED_COLUMNS - set(header)
    if missing:
        log(f"  skip {label}: not a BASt hourly file (missing columns {sorted(missing)})")
        return
    has_road = {'Strklas', 'Strnum'} <= set(header)
    rows_kept = 0
    rows_matching = 0
    skipped_files = set()
    with opener() as f:
        for chunk in pd.read_csv(f, sep=';', encoding='latin-1', dtype=str, chunksize=500_000):
            chunk.columns = [c.strip() for c in chunk.columns]
            if has_road:
                chunk = chunk[(chunk['Strklas'].str.strip() == 'A') & (chunk['Strnum'].str.strip() == '3')]
            if chunk.empty:
                continue
            # Datum is YYMMDD
            chunk_years = 2000 + chunk['Datum'].str.strip().str[:2].astype(int)
            for (year, zst), part in chunk.groupby([chunk_years, chunk['Zst'].str.strip()]):
                if year not in years:
                    continue
                rows_matching += len(part)
                target = os.path.join(PROJECT_DIR, str(year), f"zst{zst}_{year}.csv")
                if target in existing_before and not force:
                    skipped_files.add(os.path.relpath(target, PROJECT_DIR))
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                first_write = target not in written
                part.to_csv(target, sep=';', index=False, encoding='latin-1',
                            mode='w' if first_write else 'a', header=first_write)
                written.add(target)
                rows_kept += len(part)
    if rows_kept:
        log(f"  {label}: {rows_kept:,} rows written")
    if skipped_files:
        log(f"  {label}: skipped, already present: {', '.join(sorted(skipped_files))}")
    if rows_matching == 0:
        what = "A3 rows" if has_road else "rows"
        log(f"  {label}: no {what} for years {sorted(years)}")


def main():
    parser = argparse.ArgumentParser(description="Put BASt traffic data into the folders the app expects.")
    parser.add_argument('--source-dir', default=DEFAULT_SOURCE_DIR,
                        help=f"folder with downloaded zip/csv files (default: {DEFAULT_SOURCE_DIR})")
    parser.add_argument('--url', action='append', default=[],
                        help="direct download URL of a zip or csv file; can be given several times")
    parser.add_argument('--years', type=int, nargs='+', default=DEFAULT_YEARS,
                        help="years to keep (default: 2019 2023)")
    parser.add_argument('--force', action='store_true', help="rewrite files that already exist")
    args = parser.parse_args()

    os.makedirs(args.source_dir, exist_ok=True)
    log(f"Source folder: {args.source_dir}")
    log(f"Target folder: {PROJECT_DIR}")

    download_ok = download(args.url, args.source_dir) if args.url else True

    bad_files = []
    sources = list(iter_csv_sources(args.source_dir, bad_files))
    if not sources:
        log("\nERROR: no .zip or .csv files found in the source folder.")
        log(MANUAL_STEPS)
        return 1

    existing_before = set()
    for year in args.years:
        year_dir = os.path.join(PROJECT_DIR, str(year))
        if os.path.isdir(year_dir):
            existing_before |= {os.path.join(year_dir, n) for n in os.listdir(year_dir)}
    written = set()

    log(f"\nProcessing {len(sources)} CSV file(s):")
    errors = len(bad_files)
    for label, opener in sources:
        try:
            if os.path.basename(label).lower().startswith('jawe'):
                handle_jawe(label, opener, args.force)
            else:
                handle_hourly(label, opener, set(args.years), args.force, existing_before, written)
        except Exception as e:
            errors += 1
            log(f"  ERROR reading {label}: {type(e).__name__}: {e}")

    # Summary
    log("\nResult:")
    complete = True
    for year in args.years:
        year_dir = os.path.join(PROJECT_DIR, str(year))
        n = len([f for f in os.listdir(year_dir) if f.endswith('.csv')]) if os.path.isdir(year_dir) else 0
        log(f"  {year}/: {n} station file(s)")
        if n == 0:
            complete = False
            log(f"    ERROR: no hourly data for {year}. Add the {year} Stundenwerte files to the source folder.")
    if os.path.exists(os.path.join(PROJECT_DIR, 'Jawe2022.csv')):
        log("  Jawe2022.csv: present")
    else:
        complete = False
        log("  ERROR: Jawe2022.csv missing. Add it (or a zip containing it) to the source folder.")

    if not complete:
        log(MANUAL_STEPS)
        return 1
    if errors or not download_ok:
        log("\nFinished with errors (see above). The data that was processed is in place.")
        return 1
    log("\nDone. Start the app with:  streamlit run app.py")
    return 0


if __name__ == '__main__':
    sys.exit(main())
