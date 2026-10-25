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

If the full data is not installed, the app automatically uses the small
extract in `sample_data/` (a few A3 stations, a few months of 2023) and
shows a "Demo sample" notice at the top. Results from the sample are for
demonstration only: it covers part of one year, and only the stations in
the sample can be selected.

> **Not in the repository yet.** `sample_data/` has to be created from the
> full data with `python scripts/make_sample.py` (see below), and the BASt
> licence terms have to be checked before it is committed.

#### Full data (run scripts/fetch_data.py)

1. Download the BASt files manually (the BASt pages are browser pages, and
   the script does not guess file URLs):
   - Hourly counts ("Stundenwerte") for **2019** and **2023**: per-station
     zip/CSV files for the A3 stations, or the full-year file. Links are in
     "Where the data comes from" below.
   - `Jawe2022.csv` (station coordinates and direction names).
2. Put the downloaded files, zipped or not, into a folder called `raw_data/`
   in the project folder.
3. Run:
   ```
   python scripts/fetch_data.py
   ```
   It unzips the files, keeps only A3 stations, and writes
   `2019/zst<station>_2019.csv`, `2023/zst<station>_2023.csv` and
   `Jawe2022.csv` into the project folder. Files that already exist are
   skipped, so it can be run again after adding more downloads. It prints
   an error for files it cannot read and lists anything still missing.
   Options: `--source-dir <folder>` to read from another folder (e.g. your
   Downloads folder), `--url <link>` to download a file from a direct link
   first, `--force` to rewrite existing files.

As soon as any full data is present (a year folder or `Jawe2022.csv`), the
app uses it instead of the sample. If the setup is incomplete, it shows an
error rather than switching back to the sample.

To rebuild the sample from the full data:
```
python scripts/make_sample.py
```
Defaults: the 3 stations with the most 2023 rows, March to June, only the
columns the app uses. See `--help` for options.

### 3. Start

```
streamlit run app.py
```

Streamlit prints a local URL (usually http://localhost:8501). Open it in a
browser.

The map and the weather outlook need an internet connection (map tiles and
the map library are loaded from the internet). Everything else works offline.

**How these steps were checked:** a fresh clone, Linux, Python 3.13,
streamlit 1.66, pandas 3.0. The real BASt files were not available in the
test environment, so the app and the two scripts were run against generated
files in the same format as the BASt files (same columns, separators and
encoding). This tested that the code runs; it did not test any results. The
Windows commands were not tested.

### Where the data comes from

All traffic and station data comes from BASt:

- **Hourly traffic counts** (the `zst*.csv` files, one per station per
  year): [BASt — Stundenwerte](https://open.bydata.de/datasets?locale=de&query=Autobahn+Z%C3%A4hlstellen+A3&page=1&limit=10)
- **Station coordinates and metadata** (`Jawe2022.csv`): [BASt — Jahresdaten](https://www.bast.de/DE/Themen/Digitales/HF_1/Massnahmen/verkehrszaehlung/Daten/2022_1/Jawe2022.html?nn=414410)

Both are free to download, no account needed. The licence terms for
redistributing the files have not been confirmed yet; check the BASt pages
before publishing copies of the data.

The steps below are the manual alternative to `scripts/fetch_data.py`:

1. Download the hourly data for a year (e.g. 2019) from the Stundenwerte
   page. It comes as a `.zip` file.
2. Unzip it. Inside is one CSV per station, named like `zst9010_2019.csv`.
3. In the project folder, create a folder named exactly after the year,
   e.g. `2019`.
4. Move all CSVs for that year into that folder.
5. Repeat for other years (the original analysis uses 2019 and 2023).
6. Download `Jawe2022.csv` and put it directly in the project folder (not
   inside a year folder).

The folder should then look like:

```
a3-roadwork-scheduler/
├── app.py
├── data_utils.py
├── refresh_forecasts.py
├── requirements.txt
├── scripts/
├── sample_data/            (small demo extract, used if the rest is missing)
├── Jawe2022.csv            (station coordinates + metadata)
├── prophet_results.json    (precomputed seasonal values, included)
├── 2019/
│   ├── zst9010_2019.csv
│   └── ...
└── 2023/
    ├── zst9010_2023.csv
    └── ...
```

`data_utils.py` loads every folder in the project folder whose name is
exactly 4 digits and contains CSV files. Paths are relative to the project
folder, so the app can be started from any directory.

---

## Adding new yearly data

### 1. Historical data — automatic

Add the new year folder as described above. It is picked up the next time
the app starts. To exclude a year, remove its folder.

### 2. Seasonal values — manual refresh

Fitting Prophet for every station takes several minutes, so it is a separate
step:

```
pip install prophet
python refresh_forecasts.py
```

This rewrites `prophet_results.json` from the year folders currently
present. Restart the app afterwards.

The script includes German national public holidays for 2019–2026. For
later years, extend the `GERMAN_HOLIDAYS` list at the top of
`refresh_forecasts.py`.

---

## Method

### Data

Each row of a BASt hourly file has vehicle counts per direction
(`KFZ_R1`/`KFZ_R2`), truck counts (`Lkw_R1`/`Lkw_R2`), the date, the weekday
and the hour (`Stunde`, values 1–24). Station coordinates and direction
names (`Fernziel_Ri1`/`Fernziel_Ri2`) come from `Jawe2022.csv`. The data
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
  nor the Prophet values have been tested against held-out data.
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
  later than the hour that was counted. This has not been checked against
  the BASt documentation.
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
| `sample_data/` | Small extract of the real data for a quick demo (not committed yet) |
| `Jawe2022.csv`, `2019/`, `2023/` | BASt data, not included, see "Full data" |
