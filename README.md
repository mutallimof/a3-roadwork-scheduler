# A3 Roadwork Scheduler

A tool that recommends the best time to schedule highway construction on the
A3 (Germany), based on real historical traffic data and seasonal forecasting.
Built during the ConStructAI Hackathon @ THWS (June 2026).

Pick a location, a direction, a construction duration, and your daily working
hours — the tool returns a specific recommended date range, backed by real
traffic numbers, an estimated CO2 impact, and (for longer projects) a
seasonal alternative based on a Prophet forecast.

---

## What it does

- Loads real hourly traffic counts from BASt (Bundesanstalt für
  Straßenwesen — Germany's federal road authority) across all available
  years and stations on the A3
- Scores every (weekday, hour) combination by traffic volume and truck
  ratio, in priority order
- Lets you pick which direction of traffic is affected (using the road's
  real destination labels, e.g. "→ Frankfurt am Main")
- Returns a specific recommended calendar date range, not just an abstract
  "Sunday morning"
- For projects longer than 6 weeks, also suggests a seasonal alternative
  start month, using a Prophet forecast per station
- Shows a short-term weather outlook (next 15 days) for short-duration
  projects
- Visualizes the full weekly traffic pattern as a heatmap, and the whole
  A3 network as a colored map

---

## Background

This project was built for the "Data-Based Forecasting for Road Renovation
Scheduling" challenge at the ConStructAI Hackathon (THWS, June 2026): given
real traffic data, recommend the optimal timing for A3 highway roadworks to
minimize disruption. It was cleaned up and extended afterward into the
version in this repository.

### Where the data comes from

All traffic and station data comes from BASt (Bundesanstalt für
Straßenwesen), Germany's federal road authority:

- **Hourly traffic counts** (the `zst*.csv` files, one per station per
  year): [BASt — Stundenwerte](https://www.bast.de/DE/Verkehrstechnik/Fachthemen/v2-verkehrszaehlung/Stundenwerte.html)
- **Station coordinates and metadata** (`Jawe2022.csv`): [BASt — Jahresdaten](https://www.bast.de/DE/Verkehrstechnik/Fachthemen/v2-verkehrszaehlung/Jahresdaten.html)

Both are free to download, no account needed. The sections below walk
through exactly how to turn what you download into the folder structure
this tool expects.

---

## Running it

### Requirements

```
pip install streamlit pandas matplotlib pyproj folium streamlit-folium requests
```

Prophet is needed separately, only for regenerating forecasts (see below):

```
pip install prophet
```

### Setting up your data folders

BASt's download gives you a set of zipped CSVs, one per station, for a
chosen year. Here's how to turn that into what `data_utils.py` expects:

1. Go to the BASt Stundenwerte page linked above and download the hourly
   data for a year (e.g. 2019). It comes as a `.zip` file.
2. **Unzip it.** Inside, you'll find one CSV per station, named something
   like `zst9010_2019.csv`.
3. In your project folder, **create a new folder named exactly after the
   year**, e.g. `2019`.
4. **Move all the unzipped CSVs for that year into that folder.**
5. Repeat for any other year you want to include (e.g. download 2023,
   unzip, create a `2023` folder, move its CSVs in).
6. Download `Jawe2022.csv` from the Jahresdaten page and place it directly
   in the project's root folder (not inside a year folder) — it's used
   once for station coordinates and direction labels, not per-year.

Once this is done, your folder should look like:

```
your-project-folder/
├── app.py
├── data_utils.py
├── refresh_forecasts.py
├── Jawe2022.csv            (station coordinates + metadata)
├── prophet_results.json    (precomputed seasonal forecasts)
├── 2019/                   (one folder per year of traffic data)
│   ├── zst9010_2019.csv
│   ├── zst9011_2019.csv
│   └── ...
└── 2023/
    ├── zst9010_2023.csv
    └── ...
```

`data_utils.py` automatically scans for any folder named with exactly 4
digits and loads whatever CSVs are inside — you don't need to tell it
which years exist anywhere in the code.

### Start the app

```
streamlit run app.py
```

---

## Adding new yearly data

The historical scoring layer updates automatically, but the seasonal
(Prophet) forecast needs a manual refresh. These two layers are separate
on purpose — fitting Prophet across every station takes several minutes,
so it's a deliberate step rather than something the app does silently
every time it starts.

### 1. Historical scoring — automatic

Follow the same "Setting up your data folders" steps above for the new
year: download from BASt, unzip, create a folder named after the year,
move the CSVs in. `data_utils.py` automatically detects any folder with a
4-digit name containing CSVs and includes it — no code changes needed.

To exclude a year (for example, an anomalous year you don't want included),
simply don't keep that folder in the project directory. This is a deliberate
choice left to whoever manages the data, rather than something hardcoded.

### 2. Seasonal forecast — manual refresh

> **Before running for the first time:** `refresh_forecasts.py` needs the
> `prophet` package, which isn't part of the core requirements above (it's
> heavier and only needed for this one step). If you see
> `ModuleNotFoundError: No module named 'prophet'`, install it once with:
> ```
> python -m pip install prophet
> ```

1. Add your new year folder (e.g. `2024/`) alongside the existing ones
2. Run:
   ```
   python refresh_forecasts.py
   ```
3. This regenerates `prophet_results.json`, automatically including
   whatever years are currently present
4. Restart the Streamlit app

The script includes German national public holidays (2019–2026) as a
factor Prophet can learn from separately. If you add data for years beyond
2026, extend the `GERMAN_HOLIDAYS` list at the top of `refresh_forecasts.py`.

---

## Methodology

### Data source

BASt publishes hourly traffic counts per station, per year. Each row
includes vehicle counts in both directions (`KFZ_R1`/`KFZ_R2`), truck
counts (`Lkw_R1`/`Lkw_R2`), the weekday, and the hour. Station coordinates
and direction labels come from a separate yearly file (`Jawe2022.csv`).

The full data-cleaning process — including a documented mistake-then-fix
on parsing the coordinate format — is in `analysis.ipynb`.

### Scoring formula

Every (weekday, hour) combination is scored on two factors, combined in
priority order:

```
congestion_score = 1 - (avg_traffic / max_traffic)
freight_score     = 1 - avg_truck_ratio
final_score        = congestion_score * freight_score
```

The two factors are multiplied, not averaged — a time slot only scores
well if both are favorable. A low-traffic hour that happens to be
truck-heavy gets pulled down, not just slightly discounted.

### CO2 estimate

Scheduling roadworks during a high-traffic window is assumed to force
affected vehicles into a ~2km detour. At ~120g CO2/km for an average car,
that's **0.24 kg CO2 per affected vehicle** — a simplification, but
directionally meaningful for comparing best vs. worst scheduling choices.

### Seasonal forecasting (Prophet)

For projects longer than 6 weeks, the historical weekly pattern alone
isn't enough — seasonal effects matter more. Prophet is fit per station on
the full hourly time series (yearly + weekly seasonality, plus German
public holidays as a separate learned effect), forecasting a full year
ahead. The resulting monthly averages are precomputed and saved to
`prophet_results.json`, rather than run live in the app.

---

## Limitations

- **Prophet coverage:** 32 of 45 A3 stations have enough historical data
  points for Prophet to fit reliably. The remaining 13 fall back to a
  network-wide generic seasonal estimate instead of a station-specific one.
- **Holiday effect is a rough signal:** with only two years of training
  data (2019, 2023), each public holiday has just two historical examples
  for Prophet to learn from. It picks up large, obvious effects (e.g.
  Christmas being much quieter) but isn't a precise estimate — this will
  improve as more years of data are added.
- **Short-project recommendations assume a recurring weekly pattern:**
  for projects of a few weeks, the tool finds the single best weekly
  slot and repeats it. It doesn't yet check whether traffic stays
  consistently low across the entire project duration, just that the
  underlying weekly pattern is historically reliable.
- **Weather is informational, not predictive:** the short-term weather
  outlook (Open-Meteo) only displays for projects starting within ~15
  days, since forecasts beyond that aren't reliable. It does not feed
  into the scoring or seasonal forecast.
- **Data coverage gaps:** not every station has usable files for every
  year, due to broken or missing download links on BASt's portal. Years
  with very few stations are flagged with a warning when loaded, but
  still included — exclusion is a manual choice (see "Adding new yearly
  data" above).

---

## Project structure

| File | Purpose |
|---|---|
| `app.py` | The Streamlit application |
| `data_utils.py` | Loads and cleans traffic + coordinate data, auto-detects year folders |
| `refresh_forecasts.py` | Standalone script to regenerate `prophet_results.json` |
| `analysis.ipynb` | Full exploratory analysis, with documented reasoning for every data decision |
| `prophet_results.json` | Precomputed per-station seasonal forecasts |
| `Jawe2022.csv` | Station coordinates and metadata (not included in this repo — sourced from BASt) |
