"""
fetch_data.py

Builds the clean data layout the app reads, from BASt files in raw_data/:

    <project>/<year>/zst<station>_<year>.csv   (one file per A3 station and year)
    <project>/Jawe2022.csv or Jawe2023.csv      (station list with coordinates)

One command rebuilds everything:

    python scripts/fetch_data.py

What it accepts in raw_data/ (subfolders are searched too):
  - .zip files and .csv files with BASt hourly counts ("Stundenwerte").
    Per-station files (e.g. zst9033_2019.csv) and large files with many
    stations both work. Only A3 rows (Strklas = A, Strnum = 3) are kept.
  - Jawe<year>.csv (or a zip containing it), copied under its own name.

Rules:
  - Every year found in the files is written, unless --years is given. Which
    years the app then uses is set separately (A3_YEARS, see data_utils.py).
  - The same station-year found in two source files is a duplicate: the
    first one is kept, the second skipped (and reported if the content
    differs).
  - Files that already exist in the target folders are skipped, so the
    script can be run again safely. --force rewrites them.
  - At the end every output file is checked: it must open as Latin-1, ';'
    separated, with the same columns as the others.

BASt's download pages are browser pages, and this script does not guess
their file URLs. If you have direct links, pass them with --url and they are
downloaded into raw_data/ first.
"""

import argparse
import hashlib
import io
import os
import re
import shutil
import sys
import urllib.request
import zipfile

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SOURCE_DIR = os.path.join(PROJECT_DIR, 'raw_data')

# Columns the app needs from an hourly file (the rest are kept as they are)
REQUIRED_COLUMNS = {'Zst', 'Datum', 'Wotag', 'Stunde', 'KFZ_R1', 'KFZ_R2', 'Lkw_R1', 'Lkw_R2'}
JAWE_PATTERN = re.compile(r'^jawe\d{4}\.csv$', re.IGNORECASE)

MANUAL_STEPS = f"""
How to get the files (manual download):

  1. Hourly counts ("Stundenwerte") per year, from the BASt pages linked in
     the README:
       https://open.bydata.de/datasets?locale=de&query=Autobahn+Z%C3%A4hlstellen+A3
       https://www.bast.de/DE/Themen/Digitales/HF_1/Massnahmen/verkehrszaehlung/Stundenwerte.html
     Download the zip (or CSV) files for the A3 stations, or the full-year file.
  2. The station list "Jawe2022.csv" (or another year's Jawe file) from:
       https://www.bast.de/DE/Themen/Digitales/HF_1/Massnahmen/verkehrszaehlung/Daten/2022_1/Jawe2022.html?nn=414410
  3. Put all downloaded files, zipped or not, in subfolders or not, into:
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
    """Yields (label, opener) for every CSV under source_dir, including CSVs inside zips."""
    for root, dirs, files in os.walk(source_dir):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, source_dir)
            lower = name.lower()
            if lower.endswith('.csv'):
                yield rel, (lambda p=path: open(p, 'rb'))
            elif lower.endswith('.zip'):
                try:
                    zf = zipfile.ZipFile(path)
                except zipfile.BadZipFile:
                    log(f"  ERROR: {rel} is not a valid zip file (incomplete download?). Skipped.")
                    bad_files.append(rel)
                    continue
                for member in zf.namelist():
                    if member.lower().endswith('.csv') and not member.startswith('__MACOSX'):
                        yield f"{rel}/{member}", (lambda z=zf, m=member: io.BytesIO(z.read(m)))


def read_header(opener):
    with opener() as f:
        first = f.readline().decode('latin-1')
    return [c.strip() for c in first.strip().split(';')]


def handle_jawe(label, opener, force):
    name = os.path.basename(label)
    target = os.path.join(PROJECT_DIR, name[0].upper() + name[1:].lower())
    if os.path.exists(target) and not force:
        log(f"  skip {label}: {os.path.basename(target)} already present")
        return
    with opener() as src, open(target, 'wb') as dst:
        shutil.copyfileobj(src, dst)
    log(f"  wrote {os.path.basename(target)} (from {label})")


class HourlyWriter:
    """Splits hourly files into <year>/zst<station>_<year>.csv, skipping duplicates."""

    def __init__(self, years, force):
        self.years = years
        self.force = force
        self.existing_before = set()
        self.owner = {}        # target path -> source label that wrote it in this run
        self.digest = {}       # target path -> md5 of the rows written
        self.duplicates = []   # (label, target, same_content)

    def note_existing(self, year_dirs):
        for d in year_dirs:
            if os.path.isdir(d):
                self.existing_before |= {os.path.join(d, n) for n in os.listdir(d)}

    def handle(self, label, opener):
        header = read_header(opener)
        missing = REQUIRED_COLUMNS - set(header)
        if missing:
            log(f"  skip {label}: not a BASt hourly file (missing columns {sorted(missing)})")
            return
        has_road = {'Strklas', 'Strnum'} <= set(header)
        rows_written = 0
        skipped_existing = set()
        new_digests = {}
        with opener() as f:
            for chunk in pd.read_csv(f, sep=';', encoding='latin-1', dtype=str, chunksize=500_000):
                chunk.columns = [c.strip() for c in chunk.columns]
                if has_road:
                    chunk = chunk[(chunk['Strklas'].str.strip() == 'A') & (chunk['Strnum'].str.strip() == '3')]
                if chunk.empty:
                    continue
                # Datum is YYMMDD
                chunk_years = 2000 + chunk['Datum'].str.strip().str.zfill(6).str[:2].astype(int)
                for (year, zst), part in chunk.groupby([chunk_years, chunk['Zst'].str.strip()]):
                    if self.years and year not in self.years:
                        continue
                    target = os.path.join(PROJECT_DIR, str(year), f"zst{zst}_{year}.csv")
                    if target in self.existing_before and not self.force:
                        skipped_existing.add(os.path.relpath(target, PROJECT_DIR))
                        continue
                    owner = self.owner.get(target)
                    if owner is not None and owner != label:
                        # Same station-year already written from another source file
                        new_digests.setdefault(target, hashlib.md5())
                        new_digests[target].update(part.to_csv(index=False).encode())
                        continue
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    first_write = owner is None
                    part.to_csv(target, sep=';', index=False, encoding='latin-1',
                                mode='w' if first_write else 'a', header=first_write)
                    self.owner[target] = label
                    self.digest.setdefault(target, hashlib.md5()).update(part.to_csv(index=False).encode())
                    rows_written += len(part)
        for target, h in new_digests.items():
            same = h.hexdigest() == self.digest[target].hexdigest()
            self.duplicates.append((label, target, same))
            rel = os.path.relpath(target, PROJECT_DIR)
            if same:
                log(f"  {label}: duplicate of {rel} (identical content), skipped")
            else:
                log(f"  WARNING {label}: also contains {rel} with DIFFERENT content; "
                    f"kept the version from {self.owner[target]}")
        if rows_written:
            log(f"  {label}: {rows_written:,} rows written")
        if skipped_existing:
            log(f"  {label}: skipped, already present: {', '.join(sorted(skipped_existing))}")


def verify_layout(year_dirs):
    """Checks that every output file opens the same way and has the same columns."""
    reference_cols = None
    problems = []
    counts = {}
    for d in year_dirs:
        files = sorted(f for f in os.listdir(d) if f.endswith('.csv'))
        counts[os.path.basename(d)] = files
        for name in files:
            path = os.path.join(d, name)
            try:
                df = pd.read_csv(path, sep=';', encoding='latin-1', nrows=5)
            except Exception as e:
                problems.append(f"{path}: cannot be read ({type(e).__name__}: {e})")
                continue
            cols = [c.strip() for c in df.columns]
            if reference_cols is None:
                reference_cols = cols
            elif cols != reference_cols:
                problems.append(f"{os.path.relpath(path, PROJECT_DIR)}: columns differ from the other files")
            if not re.fullmatch(r'zst\d+_\d{4}\.csv', name):
                problems.append(f"{os.path.relpath(path, PROJECT_DIR)}: unexpected file name")
    return counts, reference_cols, problems


def main():
    parser = argparse.ArgumentParser(description="Build the clean data layout from files in raw_data/.")
    parser.add_argument('--source-dir', default=DEFAULT_SOURCE_DIR,
                        help=f"folder with downloaded zip/csv files (default: {DEFAULT_SOURCE_DIR})")
    parser.add_argument('--url', action='append', default=[],
                        help="direct download URL of a zip or csv file; can be given several times")
    parser.add_argument('--years', type=int, nargs='+',
                        help="only write these years (default: every year found)")
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

    writer = HourlyWriter(set(args.years) if args.years else None, args.force)
    writer.note_existing(os.path.join(PROJECT_DIR, n) for n in os.listdir(PROJECT_DIR)
                         if re.fullmatch(r'\d{4}', n))

    log(f"\nProcessing {len(sources)} CSV file(s):")
    errors = len(bad_files)
    for label, opener in sources:
        try:
            if JAWE_PATTERN.match(os.path.basename(label)):
                handle_jawe(label, opener, args.force)
            else:
                writer.handle(label, opener)
        except Exception as e:
            errors += 1
            log(f"  ERROR reading {label}: {type(e).__name__}: {e}")

    year_dirs = sorted(os.path.join(PROJECT_DIR, n) for n in os.listdir(PROJECT_DIR)
                       if re.fullmatch(r'\d{4}', n) and os.path.isdir(os.path.join(PROJECT_DIR, n)))
    counts, columns, problems = verify_layout(year_dirs)

    log("\nResult:")
    for year, files in counts.items():
        stations = [f[3:].split('_')[0] for f in files]
        log(f"  {year}/: {len(files)} station file(s): {', '.join(stations)}")
    if columns:
        log(f"  all files checked: Latin-1, ';' separated, {len(columns)} columns")
    jawe_files = sorted(f for f in os.listdir(PROJECT_DIR) if JAWE_PATTERN.match(f))
    log(f"  station list: {', '.join(jawe_files) if jawe_files else 'MISSING'}")
    n_dup = len(writer.duplicates)
    if n_dup:
        log(f"  duplicates skipped: {n_dup}")

    complete = True
    if not counts:
        complete = False
        log("  ERROR: no hourly data written.")
    if not jawe_files:
        complete = False
        log("  ERROR: no Jawe<year>.csv station list. Add it (or a zip containing it) to the source folder.")
    for p in problems:
        log(f"  ERROR: {p}")
    if not complete:
        log(MANUAL_STEPS)
        return 1
    if errors or problems or not download_ok:
        log("\nFinished with errors (see above). The data that was processed is in place.")
        return 1
    log("\nDone. Start the app with:  streamlit run app.py")
    return 0


if __name__ == '__main__':
    sys.exit(main())
