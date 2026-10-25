# A3 Roadwork Scheduler

A Streamlit app that suggests when to schedule roadworks at a traffic
counting station on the A3 motorway in Bavaria, Germany. It uses historical
hourly traffic counts from BASt (Bundesanstalt für Straßenwesen, Germany's
federal road research institute) and, for long projects, precomputed
seasonal values from a Prophet model.

Built during the ConStructAI Hackathon at THWS (June 2026) for the challenge
"Data-Based Forecasting for Road Renovation Scheduling", and cleaned up
afterwards.

---

## What the app shows

You choose a counting station, the affected side of the road, the earliest
start date, the project duration in weeks and the daily working hours. The
app then shows:

- **The recommended time**: a weekday, a time window and a calendar date
  range, with a short note on how it was chosen.
- **Key numbers**: average traffic in the recommended hour, how much lower
  that is than the worst slot inside your working hours, and a rough CO2
  estimate.
- **Seasonal alternative** (projects longer than 6 weeks): the month with the
  lowest value in the precomputed seasonal data, an alternative date range in
  that month, and a bar chart of all 12 monthly values.
- **Weekly traffic pattern**: a heatmap of measured average vehicles per hour
  for each weekday and hour at the selected station, with the recommended
  slot marked.
- **Top 5 time slots** and an explanation of the score.
- **A3 network map**: all counting stations coloured by average traffic.
- **Weather** (projects of 1-2 weeks starting within about 15 days): a
  short-term forecast from Open-Meteo. It is shown for information only and
  does not change the recommendation.

> **Screenshot placeholder 1: input panel.** Capture the top of the page
> before clicking "Find best schedule" (title, data summary line, "Where" and
> "When" panel). Save as `screenshots/ss_main.png`.

> **Screenshot placeholder 2: recommendation.** Pick a station with data,
> set the duration to 10 weeks, click "Find best schedule". Capture the
> "Recommended time for the roadworks" box and the three numbers below it.
> Save as `screenshots/ss_results.png`.

> **Screenshot placeholder 3: charts.** Same run as above. Capture the
> "Seasonal alternative" bar chart and the "Weekly traffic pattern" heatmap.
> Save as `screenshots/ss_heatmap.png`.

> **Screenshot placeholder 4: map.** Same run, scroll to "A3 network
> overview" and capture the map (needs internet). Save as
> `screenshots/ss_map.png`.

The images currently in `screenshots/` show the older version of the
interface.

---

## Stack

- Python (tested with 3.13)
- Streamlit (web interface)
- pandas (data loading and aggregation)
- matplotlib (heatmap and monthly bar chart)
- folium + streamlit-folium (network map)
- pyproj (converts station coordinates from UTM32 to latitude/longitude)
- requests (Open-Meteo weather lookup)
- Prophet (only for `refresh_forecasts.py`, which precomputes the seasonal
  values; the app itself does not run Prophet)

---

## Running it

### 1. Install

```
git clone https://github.com/mutallimof/a3-roadwork-scheduler.git
cd a3-roadwork-scheduler
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Choose the data

#### Quick demo (no downloads)

The repository includes `sample_data/`: a small extract of the real BASt
data (stations 9033 AD Seligenstadt, 9040 AK Nürnberg and 9093 AK
Deggendorf, March to June 2023, 0.33 MB). If the full data is not
installed, the app uses it automatically and shows a "Demo sample" notice
at the top. Results from the sample are for demonstration only: it covers
four months of one year, and only these three stations can be selected.

Nothing to do: go to step 3.

#### Full data (run scripts/fetch_data.py)

1. Get the BASt files (see "Where the data comes from" below):
   - hourly counts ("Stundenwerte") per station and year, as zips or CSVs,
     or the large full-year file;
   - the station list `Jawe2022.csv` (or `Jawe2023.csv`).
2. Put them into `raw_data/` in the project folder. Zipped or not, in
   subfolders or not, does not matter.
3. Run:
   ```
   python scripts/fetch_data.py
   ```

This builds the clean layout in one command:

- unzips everything and searches subfolders;
- keeps only A3 rows and writes one file per station and year,
  `<year>/zst<station>_<year>.csv`, for every year found;
- copies the station list under its own name (`Jawe2022.csv` or
  `Jawe2023.csv`);
- skips a station-year that appears twice and says whether the two
  copies were identical;
- skips files that already exist (use `--force` to rewrite them);
- checks every output file (Latin-1, `;` separated, same columns) and
  prints the number of stations per year.

Other options: `--source-dir <folder>` to read from another folder (e.g.
Downloads), `--url <link>` to download a file from a direct link first,
`--years 2019 2023` to write only some years.

As soon as any full data is present (a year folder or a `Jawe` station
list), the app uses it instead of the sample. If the setup is incomplete,
it shows an error rather than switching back to the sample.

To rebuild the sample from the full data: `python scripts/make_sample.py`.
To write a report of the installed data (coverage, checks, quality flags):
`python scripts/data_report.py` (writes `data_report.md`).

### 3. Start

```
streamlit run app.py
```

Streamlit prints a local URL (usually http://localhost:8501). Open it in a
browser.

The map and the weather outlook need an internet connection (map tiles and
the map library are loaded from the internet). Everything else works offline.

**How this was checked:** Linux, Python 3.13, streamlit 1.66, pandas 3.0,
with the real BASt files for 2018, 2022 and 2023 and `Jawe2023.csv` (from
the aitraffic project, see Credits). `fetch_data.py` rebuilt all 63
station-year files; the app ran for every station with no errors, both with
the full data and with only the demo sample. The map could not be checked
(no internet access in the test environment), and the Windows commands were
not tested.

### Which years the app uses

The analysis uses **2019 and 2023** (2019 as the pre-COVID baseline;
2020–2022 were left out on purpose because of COVID, and 2022 also had poor
station coverage). The app loads only these years by default, even if other
year folders such as `2018/` or `2022/` are present, and says so at the top
of the page.

To use other years, set the environment variable `A3_YEARS` before
starting the app:

```
A3_YEARS=2018,2022,2023 streamlit run app.py      # Linux/macOS
set A3_YEARS=2018,2022,2023 && streamlit run app.py   (Windows cmd)
$env:A3_YEARS="all"; streamlit run app.py            (Windows PowerShell)
```

`all` uses every year folder present.

**If 2019 is missing** (as in the data currently available, see
Limitations), the app shows a notice, continues with 2023 only, and marks
every station without 2023 counts as "(no traffic data)" in the station
list and grey on the map. With the current files that is 19 stations with
data and 27 without, out of 46 A3 stations in Bavaria.

### Data checks

When the app loads the data it checks, per station and year: the number
of hours (8,760, or 8,784 in a leap year), duplicate and missing hours,
empty and negative counts, more than 10,000 vehicles per hour in one
direction, more trucks than vehicles, and the BASt quality flags
(`K_KFZ_R1`/`K_KFZ_R2`: `s` = estimated, `u` = implausible). Findings are
shown as a warning with details; the app keeps working. With the current
2023 data the only finding is station 9050 (AK Fürth/Erlangen (O)), with
1,486 counts flagged implausible.

### Where the data comes from

All traffic and station data comes from the **Bundesanstalt für
Straßenwesen (BASt)**:

- **Hourly traffic counts** (`zst*.csv`, one per station per year):
  [BASt — Stundenwerte](https://open.bydata.de/datasets?locale=de&query=Autobahn+Z%C3%A4hlstellen+A3&page=1&limit=10)
- **Station coordinates and metadata** (`Jawe2022.csv`):
  [BASt — Jahresdaten](https://www.bast.de/DE/Themen/Digitales/HF_1/Massnahmen/verkehrszaehlung/Daten/2022_1/Jawe2022.html?nn=414410)

Both are free to download, no account needed. The licence terms for
redistributing the files have not been confirmed. The full data is
therefore not in this repository (`.gitignore` excludes the year folders,
`raw_data/`, the `Jawe` files and zips); only the small `sample_data/`
extract is included.

### Data layout

```
a3-roadwork-scheduler/
├── app.py
├── data_utils.py
├── station_names.csv       (station number -> name, for repairing names)
├── prophet_results.json    (precomputed seasonal values)
├── sample_data/            (demo extract, included)
│   ├── Jawe2023.csv
│   └── 2023/zst9033_2023.csv, zst9040_2023.csv, zst9093_2023.csv
├── raw_data/               (your downloads; not in git)
├── Jawe2023.csv            (station list; not in git)
├── 2018/  2022/            (present but not used by default; not in git)
└── 2023/                   (not in git)
    ├── zst9010_2023.csv
    └── ...                 (one file per station)
```

Paths are relative to the project folder, so the app can be started from
any directory.

---

## Adding new yearly data

### 1. Historical data

Put the new files into `raw_data/` and run `python scripts/fetch_data.py`.
The app only uses the years in `A3_YEARS` (default 2019 and 2023), so add
the new year there, or change `DEFAULT_YEARS` in `data_utils.py`.

### 2. Seasonal values — manual refresh

Fitting Prophet for every station takes several minutes, so it is a separate
step:

```
pip install prophet
python refresh_forecasts.py
```

This rewrites `prophet_results.json` from the configured years that are
present (with the current data: 2023 only). Restart the app afterwards.

The script includes German national public holidays for 2019–2026. For
later years, extend the `GERMAN_HOLIDAYS` list at the top of
`refresh_forecasts.py`.

---

## Method

### Data

Each row of a BASt hourly file has vehicle counts per direction
(`KFZ_R1`/`KFZ_R2`), truck counts (`Lkw_R1`/`Lkw_R2`), the date, the weekday
and the hour (`Stunde`, values 1–24). Station coordinates and direction
names (`Fernziel_Ri1`/`Fernziel_Ri2`) come from `Jawe2022.csv`, or
`Jawe2023.csv` when that is the only station list available. The data
cleaning steps, including a corrected mistake in parsing the coordinates,
are in `analysis.ipynb`.

### Choosing the time slot

For the selected station and side of the road, the app averages the
historical counts for every (weekday, hour) combination inside the chosen
working hours, and scores each one:

```
traffic_score = 1 - (avg_traffic / highest avg_traffic among those slots)
truck_score   = 1 - avg_truck_share
score         = traffic_score * truck_score
```

The slot with the highest score is recommended. The start date is the first
matching weekday after the earliest start date, and the work repeats weekly
for the chosen number of weeks.

### CO2 estimate

Assumes every vehicle passing during the work is forced into a 2 km detour
at 120 g CO2/km, i.e. 0.24 kg CO2 per vehicle. The app compares the best
slot with the worst slot inside the working hours. This is a rough
illustration, not a measured value.

### Seasonal values (Prophet)

For projects longer than 6 weeks the app also suggests a start month. The
monthly values come from `prophet_results.json`, which `refresh_forecasts.py`
produces by fitting Prophet per station on the hourly series (yearly and
weekly seasonality, German public holidays) and averaging the predictions
per calendar month. Stations without an entry use a fixed network-wide set
of monthly values written into `app.py`.

---

## Limitations

- **No 2019 data.** The 2019 hourly files are not available in this
  setup, so the app currently runs on 2023 only (19 stations). The 13
  stations that only had 2019 data in the original analysis (9027, 9038,
  9041, 9046, 9251, 9252, 9511, 9512, 9515, 9516, 9517, 9518, 9727) have no
  traffic data now. Adding the 2019 files to `raw_data/` and rerunning
  `fetch_data.py` restores the intended setup.
- **No Jawe2022.csv.** The station list used is `Jawe2023.csv`. For the 45
  stations listed in both, the coordinates are the same (checked against
  the Jawe2022 output in `analysis.ipynb`); 9509 Weibersbrunn is new in 2023.
- **Station names were damaged in the available Jawe2023.csv.** Every
  umlaut had been replaced by an unknown-character mark, and this cannot be
  undone by re-decoding. 16 of the 46 Bavarian station names were repaired
  from `station_names.csv` (the Jawe2022 names printed in
  `analysis.ipynb`), and only where the station number matches and every
  other letter is identical. The destination names (Nürnberg, Würzburg)
  were repaired the same way. A name that cannot be checked like this is
  shown with `?` and its station number, never guessed; with the current
  files there are none.
- **Quality flags.** For several 2023 stations a large share of hourly
  counts is marked as estimated by BASt (up to 41% for 9085). The app
  reports this but still uses all counts. The meaning of the flags (`s`
  estimated, `u` implausible) is taken from the aitraffic project's data
  report and has not been checked against the BASt documentation.
- **The seasonal values in the committed `prophet_results.json` mix fitted
  and forecast values.** Up to this branch, `refresh_forecasts.py` called
  `make_future_dataframe(periods=8760, freq='h')`, which by default also
  includes all training timestamps. The monthly averages were therefore
  about two thirds Prophet's fitted values for 2019 and 2023 and one third
  the forecast for the following year. They are model output in both cases,
  not measured counts. The script is fixed on this branch
  (`include_history=False`), but `prophet_results.json` has not been
  regenerated because the data is not in the repository. It is not known
  how much this changes the recommended month. In the committed file,
  January is the lowest month for 24 of the 32 stations, November for 5
  and December for 3. In the notebook's single-station test, which averaged
  only the forecast year, November and December were lowest. Re-running
  `refresh_forecasts.py` with the data would show whether the month changes.
- **The app only uses the lowest month.** The seasonal suggestion picks the
  month with the lowest value. It does not check whether the difference to
  other months is meaningful.
- **No accuracy has been measured.** Neither the time-slot recommendation
  nor the Prophet values have been tested against held-out data. As a
  plausibility check only: with the 2023 data the network-wide quietest
  slot is Sunday hour 4–5 (about 500 vehicles/hour, both directions) and
  the busiest Friday hour 15 (about 5,870), close to the notebook's
  figures for 2019 + 2023 (550 and 5,660).
- **Two years of data with a gap.** The analysis uses 2019 and 2023
  (2020–2022 were left out because of COVID). Prophet fits one trend across
  the four-year gap. Each public holiday appears only twice in the training
  data, so the holiday effect is a rough signal.
- **Station coverage.** 32 stations have a station-specific seasonal entry.
  The others use the fixed fallback values in `app.py`; where those values
  came from is not documented in the code. Not every station has traffic
  files for every year.
- **Hour labels.** BASt's `Stunde` column runs from 1 to 24. The app shows
  the value as a clock time (e.g. 5 → 05:00). If `Stunde` = 1 means
  00:00–01:00 (which the 1–24 range suggests), the times shown are one hour
  later than the hour that was counted. The aitraffic project's data report
  also reads `Stunde` 1 as 00:00–01:00, but neither source has been checked
  against the BASt documentation.
- **Time window vs. score.** The score is computed for single hours. The
  app then shows a 4-hour window starting at the best hour, which can extend
  beyond the chosen working hours. The CO2 estimate assumes 8 working hours
  per day for both "Day" and "Night" options, although the day option
  covers 06–18.
- **Short projects assume a repeating weekly pattern.** The app repeats the
  best weekly slot and does not check whether traffic stays low across the
  whole project period.
- **Map.** The line on the map connects stations ordered west to east and
  only roughly follows the road. The map needs an internet connection.
- **Weather** is shown only for short projects starting within about 15
  days and is not used in the scoring.

---

## Project structure

| File | Purpose |
|---|---|
| `app.py` | The Streamlit application |
| `data_utils.py` | Loads and cleans traffic and coordinate data, finds year folders |
| `refresh_forecasts.py` | Standalone script that regenerates `prophet_results.json` |
| `analysis.ipynb` | Exploratory analysis with the reasoning behind data decisions |
| `prophet_results.json` | Precomputed monthly seasonal values per station |
| `requirements.txt` | Python packages needed to run the app |
| `scripts/fetch_data.py` | Unzips downloaded BASt files and puts A3 data into the folders the app expects |
| `scripts/make_sample.py` | Builds `sample_data/` from the full data |
| `scripts/data_report.py` | Writes `data_report.md` (coverage, checks, quality flags) |
| `data_report.md` | Report of the data used for testing (aggregate figures only) |
| `station_names.csv` | Station number -> correct name, used to repair damaged names |
| `sample_data/` | Small extract of the real data for a quick demo |
| `tests/` | Unit tests (`python -m unittest discover -s tests -v`) |
| `Jawe*.csv`, `2018/`, `2019/`, `2022/`, `2023/`, `raw_data/` | BASt data, not in git, see "Full data" |

---

## Tests

```
python -m unittest discover -s tests -v
```

18 tests for the data loader, year selection, name repair, data checks and
`scripts/fetch_data.py`. They use small generated files in a temporary
folder, not real data, and need no extra packages.

---

## Credits

- **Data:** Bundesanstalt für Straßenwesen (BASt), automatic traffic
  counts on federal motorways (hourly values) and yearly evaluation files
  (Jawe). `sample_data/` is an unchanged extract of these files.
- **aitraffic** ([github.com/DanieMyl/aitraffic](https://github.com/DanieMyl/aitraffic)),
  a joint project, provided:
  - the 2018, 2022 and 2023 hourly files and `Jawe2023.csv` used to test
    this version;
  - the idea of using the BASt quality flags and of checking for missing
    hours, negative counts and more trucks than vehicles
    (`clean_data.py`, `data_report.md`), adapted in `check_data()` in
    `data_utils.py`;
  - the idea of a written data report (`data_report.md`), adapted in
    `scripts/data_report.py`;
  - the month × weekday heatmap (`plot_month_dow()` in `heatmap.py`),
    adapted in the app as "Measured traffic by month and weekday".

  No code was copied unchanged; each part was rewritten for this app.
