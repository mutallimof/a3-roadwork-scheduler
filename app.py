import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from data_utils import (load_traffic_data, load_coordinates, resolve_data_dir, year_status,
                        check_data, BASE_DIR)
import scheduler
import datetime
import json
import os
import requests

st.set_page_config(layout="wide", page_title="A3 Roadwork Scheduler")

st.title("A3 Roadwork Scheduler")
st.write("Suggests when to schedule roadworks at a counting station on the A3 motorway (Bavaria), "
         "based on historical hourly traffic counts from BASt.")

SETUP_HINT = ("See the README section \"Full data\": run `python scripts/fetch_data.py` to put the "
              "year folders (for example `2019/`, `2023/`) and the station list (`Jawe2022.csv` or "
              f"`Jawe2023.csv`) in the project folder (`{BASE_DIR}`).")

data_dir, is_sample = resolve_data_dir()

@st.cache_data
def load_data(data_dir):
    df = load_traffic_data(base_path=data_dir)
    coords = load_coordinates(base_path=data_dir)
    return df, coords

@st.cache_data
def run_data_check(df, full_year):
    # The check must never stop the app; a failure is reported as a finding
    try:
        return check_data(df, full_year=full_year)
    except Exception as e:
        return [f"The data check itself failed ({type(e).__name__}: {e})."], pd.DataFrame()

@st.cache_data
def load_prophet_results():
    # Missing or unreadable forecast file is not fatal: the app falls back
    # to a network-wide seasonal estimate.
    try:
        with open(os.path.join(BASE_DIR, 'prophet_results.json')) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def get_weather_outlook(lat, lon, target_date):
    """Open-Meteo forecast — only reliable within ~15 days, returns None outside that range."""
    days_ahead = (target_date - datetime.date.today()).days
    if days_ahead < 0 or days_ahead > 15:
        return None
    try:
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
               f"&daily=precipitation_sum,temperature_2m_max&timezone=Europe%2FBerlin"
               f"&start_date={target_date}&end_date={target_date}")
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        rain = data['daily']['precipitation_sum'][0]
        temp = data['daily']['temperature_2m_max'][0]
        return rain, temp
    except Exception:
        return None

prophet_results = load_prophet_results()
try:
    df, coords = load_data(data_dir)
except FileNotFoundError as e:
    st.error(f"Traffic data not found. {SETUP_HINT}")
    with st.expander("Technical details"):
        st.code(str(e))
    st.stop()
except Exception as e:
    st.error(f"The traffic data could not be loaded. {SETUP_HINT}")
    with st.expander("Technical details"):
        st.code(f"{type(e).__name__}: {e}")
    st.stop()

if coords.empty:
    st.error(f"The station list `{coords.attrs.get('source_file', 'Jawe')}` was loaded but contains no "
             f"A3 stations in Bavaria. {SETUP_HINT}")
    st.stop()

years_info = year_status(data_dir)
check_issues, check_table = run_data_check(df, full_year=not is_sample)

month_names = {1:'January',2:'February',3:'March',4:'April',5:'May',6:'June',
               7:'July',8:'August',9:'September',10:'October',11:'November',12:'December'}

years_loaded = sorted(df['year'].unique())
stations_with_data = set(df['Zst'].unique())
data_period = f"{df['Datum'].min():%d %b %Y} to {df['Datum'].max():%d %b %Y}"
if is_sample:
    st.warning(f"**Demo sample.** The full traffic data is not installed, so the app is using the small "
               f"extract in `sample_data/`: {len(stations_with_data)} stations, {data_period}. "
               f"The numbers are real BASt counts but cover only part of the year, so results are "
               f"for demonstration only. Run `python scripts/fetch_data.py` for the full data.")
stations_without_data = coords[~coords['DZ_Nr'].isin(stations_with_data)]
if years_info['missing'] and not is_sample:
    st.info(f"Configured years: {', '.join(str(y) for y in years_info['configured'])}. "
            f"No data folder for {', '.join(str(y) for y in years_info['missing'])}, so the app uses "
            f"{', '.join(str(y) for y in years_info['used'])} only. {len(stations_without_data)} of "
            f"{len(coords)} stations have no traffic data for the years in use; they are marked "
            f"\"no traffic data\" in the station list and grey on the map.")
ignored_note = (f" Also present but not used: {', '.join(str(y) for y in years_info['ignored'])} "
                f"(set A3_YEARS to include them)." if years_info['ignored'] and not is_sample else "")
st.caption(f"Data loaded: {len(df):,} hourly records from {len(stations_with_data)} stations, "
           f"years {', '.join(str(y) for y in years_loaded)}. "
           f"{len(prophet_results)} stations have a precomputed seasonal forecast.{ignored_note}")
if check_issues:
    st.warning(f"Data check: {len(check_issues)} finding(s). The app still works; results for the "
               f"affected stations may be less reliable.")
    with st.expander("Data check details"):
        for issue in check_issues:
            st.markdown(f"- {issue}")
        st.caption("Checked on load: hours per station and year, duplicate and missing hours, empty, negative "
                   "and impossible counts (over 10,000 vehicles per hour in one direction), more trucks than "
                   "vehicles, and BASt quality flags ('s' = estimated, 'u' = implausible).")

# --- Inputs -----------------------------------------------------------------
with st.container(border=True):
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Where**")
        station_choices = coords
        if is_sample:
            # The sample only has counts for a few stations; list just those
            station_choices = coords[coords['DZ_Nr'].isin(stations_with_data)]
        # Stations with data first, then the rest, each sorted by name
        station_choices = station_choices.assign(has_data=station_choices['DZ_Nr'].isin(stations_with_data))
        station_choices = station_choices.sort_values(['has_data', 'DZ_Name'], ascending=[False, True])
        station_labels = {row.DZ_Nr: row.DZ_Name if row.has_data else f"{row.DZ_Name} (no traffic data)"
                          for row in station_choices.itertuples()}
        station_id = st.selectbox("Counting station", list(station_labels), format_func=station_labels.get)
        station_row = coords[coords['DZ_Nr'] == station_id].iloc[0]
        station_name = station_row['DZ_Name']
        dir1_label = f"→ {station_row['Fernziel_Ri1']}" if pd.notna(station_row['Fernziel_Ri1']) else "Direction 1"
        dir2_label = f"→ {station_row['Fernziel_Ri2']}" if pd.notna(station_row['Fernziel_Ri2']) else "Direction 2"
        direction_choice = st.radio(
            "Affected side of the road",
            ["Both directions (full closure)", dir1_label, dir2_label],
        )
        if station_id not in stations_with_data:
            st.warning("No traffic counts are loaded for this station for the years in use, so no schedule "
                       "can be computed. Stations with data are at the top of the list.")
    with right:
        st.markdown("**When**")
        earliest_start = st.date_input("Earliest possible start date", value=datetime.date.today())
        duration_weeks = st.slider("Construction duration (weeks)", 1, 26, 4)
        work_hours = st.select_slider("Daily working hours",
                                        options=["Night only (22-06)", "Day (06-18)", "24h (always)"],
                                        value="Day (06-18)")
        shift_length = len(scheduler.SHIFTS[scheduler.SHIFT_BY_LABEL[work_hours]][1])
        window_hours = st.slider("Hours per work session", 1, min(12, shift_length), min(4, shift_length),
                                 help="Length of one uninterrupted work session. The app looks for the quietest "
                                      "block of this many consecutive hours inside the working hours.")

    current_inputs = (station_id, duration_weeks, work_hours, window_hours, direction_choice, earliest_start)
    find_clicked = st.button("Find best schedule", type="primary")

if "show_results" not in st.session_state:
    st.session_state.show_results = False

if find_clicked:
    st.session_state.show_results = True
    st.session_state.station_id = station_id
    st.session_state.station_name = station_name
    st.session_state.station_lat = station_row['lat']
    st.session_state.station_lon = station_row['lon']
    st.session_state.duration_weeks = duration_weeks
    st.session_state.work_hours = work_hours
    st.session_state.window_hours = window_hours
    st.session_state.direction_choice = direction_choice
    st.session_state.dir1_label = dir1_label
    st.session_state.dir2_label = dir2_label
    st.session_state.earliest_start = earliest_start
    st.session_state.inputs = current_inputs


def show_results():
    station_id = st.session_state.station_id
    station_name = st.session_state.station_name
    duration_weeks = st.session_state.duration_weeks
    work_hours = st.session_state.work_hours
    window_hours = st.session_state.window_hours
    direction_choice = st.session_state.direction_choice
    dir1_label = st.session_state.dir1_label
    dir2_label = st.session_state.dir2_label
    earliest_start = st.session_state.earliest_start

    station_data = df[df['Zst'] == station_id].copy()

    if station_data.empty:
        st.error(f"No traffic data is loaded for {station_name}, so no schedule can be computed. "
                 "Pick a different station.")
        return

    side = 'R1' if direction_choice == dir1_label else 'R2' if direction_choice == dir2_label else 'both'
    shift = scheduler.SHIFT_BY_LABEL[work_hours]
    rec = scheduler.recommend(station_data, side, shift, window_hours, earliest_start, duration_weeks)
    if rec is None:
        st.error("There is not enough usable traffic data for this station and these working hours "
                 "to compute a schedule.")
        return

    best, worst, windows = rec['best'], rec['worst'], rec['windows']
    reduction = rec['reduction'] * 100
    start_date, end_date = rec['start_date'], rec['end_date']
    best_dow = int(best['dow'])
    best_day_full = scheduler.DAY_NAMES[best_dow]
    window_text = rec['label'].split(', ', 1)[1]

    # One work session per week, as the headline says
    total_hours = duration_weeks * window_hours
    co2_best = best['avg_traffic'] * 0.24 * total_hours
    co2_worst = worst['avg_traffic'] * 0.24 * total_hours

    # --- Headline -------------------------------------------------------
    with st.container(border=True):
        st.markdown("#### Recommended time for the roadworks")
        st.markdown(f"## {rec['label']}, from {start_date.strftime('%d %B %Y')} "
                    f"to {end_date.strftime('%d %B %Y')}")
        st.write(f"Station: **{station_name}**. Affected side: **{direction_choice}**. "
                 f"Working hours: **{work_hours}**, sessions of **{window_hours} h**. "
                 f"The work session repeats every week until the project ends.")
        st.caption(
            f"How this was chosen: every block of {window_hours} consecutive hours inside your working hours "
            f"was scored using the historical counts for this station ({data_period}"
            f"{', demo sample only' if is_sample else ''}). Blocks with less traffic on the affected side and "
            f"a lower share of trucks score higher; {best_day_full} {window_text} scored highest. The project "
            f"starts on the first {best_day_full} on or after your earliest start date. Times are local clock "
            f"times (BASt hour 1 = 00:00–01:00). Public holidays and hours BASt marked implausible are left "
            f"out of the averages ({rec['excluded']['holiday']:,} and {rec['excluded']['implausible']:,} hours)."
        )

    c1, c2, c3 = st.columns(3)
    c1.metric("Average traffic in the recommended window", f"{best['avg_traffic']:.0f} vehicles/hour")
    c2.metric("Less traffic than the worst window", f"{reduction:.0f}%",
              help=f"Compared with the lowest-scoring {window_hours}-hour window inside your working hours "
                   f"({scheduler.window_label(int(worst['dow']), int(worst['clock']), window_hours)}, "
                   f"{worst['avg_traffic']:.0f} vehicles/hour).")
    c3.metric("Estimated CO2 avoided over the project", f"{(co2_worst-co2_best)/1000:.1f} t",
              help=f"Rough estimate for {total_hours} work hours ({duration_weeks} weekly sessions of "
                   f"{window_hours} h): assumes each affected vehicle drives a 2 km detour at 120 g CO2/km "
                   "(0.24 kg per vehicle), compared with working in the worst window.")

    if rec['holidays']:
        on_days = rec['holidays_on_work_days']
        listed = ', '.join(f"{d:%d %b %Y} ({n})" for d, n in rec['holidays'])
        st.info(f"Public holidays in Bavaria during the project: {listed}. "
                + (f"{len(on_days)} of them fall on a work day ({best_day_full}). " if on_days else "")
                + "Traffic on public holidays is usually lower than on normal weekdays; they are not part of "
                  "the averages above.")

    if duration_weeks <= 2:
        weather = get_weather_outlook(st.session_state.station_lat, st.session_state.station_lon, start_date)
        if weather:
            rain, temp = weather
            st.write(f"Weather forecast for {start_date.strftime('%d %B')} (Open-Meteo): "
                     f"up to **{temp:.0f} °C**, **{rain:.1f} mm** precipitation. "
                     "Shown only for short projects starting within about 15 days; it does not affect the recommendation.")

    # --- Seasonal alternative (long projects only) ------------------------
    best_month = None
    if duration_weeks > 6:
        station_prophet = prophet_results.get(str(int(station_id)))

        if station_prophet:
            month_traffic = {int(k): v for k, v in station_prophet.items()}
            forecast_source = "this station's precomputed Prophet forecast"
        else:
            month_traffic = {1: 2751, 2: 2924, 3: 3043, 4: 3064, 5: 2945, 6: 2899,
                              7: 3209, 8: 3011, 9: 2837, 10: 2636, 11: 2210, 12: 2065}
            forecast_source = ("a fixed network-wide estimate, because no station-specific forecast "
                               "exists for this station")
        best_month = min(month_traffic, key=month_traffic.get)

        year = earliest_start.year
        if best_month < earliest_start.month:
            year += 1
        candidate = datetime.date(year, best_month, 1)
        if candidate < earliest_start:
            candidate = datetime.date(year + 1, best_month, 1)

        days_ahead_seasonal = (best_dow - candidate.weekday()) % 7
        seasonal_start = candidate + datetime.timedelta(days=days_ahead_seasonal)
        seasonal_end = seasonal_start + datetime.timedelta(weeks=duration_weeks)

        st.subheader("Seasonal alternative")
        st.info(f"Because this project runs {duration_weeks} weeks, the time of year matters too. "
                f"**{month_names[best_month]}** has the lowest average traffic in {forecast_source}. "
                f"Alternative start in that month: **{seasonal_start.strftime('%d %B %Y')} → "
                f"{seasonal_end.strftime('%d %B %Y')}**, still on {best_day_full}s.")

        months = list(range(1, 13))
        values = [month_traffic.get(m, float('nan')) for m in months]
        fig, ax = plt.subplots(figsize=(10, 3))
        colors = ['#2a6fdb' if m == best_month else '#b8c4d6' for m in months]
        ax.bar([month_names[m][:3] for m in months], values, color=colors, width=0.7)
        ax.annotate(f"{month_traffic[best_month]:.0f}", (best_month - 1, month_traffic[best_month]),
                    xytext=(0, 3), textcoords="offset points", ha='center', fontsize=9)
        ax.set_xlabel("Month")
        ax.set_ylabel("Vehicles per hour")
        ax.set_title("Average traffic per month, both directions (dark bar = lowest month)", fontsize=10)
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(axis='y', alpha=0.3)
        ax.set_axisbelow(True)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)
        st.caption("What this chart shows: the average number of vehicles per hour (both directions added "
                   "together) for each calendar month, taken from the precomputed seasonal values. "
                   "Only the lowest month is used by the app. These are model estimates, not measured counts; "
                   "see the README section \"Limitations\" for how they were produced.")

    # --- Weekly pattern -------------------------------------------------
    st.subheader("Weekly traffic pattern at this station")
    profile = rec['profile']['avg_traffic'].to_numpy().reshape(7, 24)
    fig, ax = plt.subplots(figsize=(12, 4))
    im = ax.imshow(profile, aspect='auto', cmap='Blues')
    ax.set_yticks(range(7))
    ax.set_yticklabels([d[:3] for d in scheduler.DAY_NAMES])
    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=8)
    ax.set_xlabel("Hour of day (start of the hour, local time)")
    ax.set_ylabel("Day of week")
    ax.set_title(f"{station_name} — {direction_choice}", fontsize=10)
    for k in range(window_hours):
        slot = (int(best['start_slot']) + k) % 168
        ax.add_patch(Rectangle((slot % 24 - 0.5, slot // 24 - 0.5), 1, 1, fill=False,
                               edgecolor='#e8590c', linewidth=2.5))
    plt.colorbar(im, label='Average vehicles per hour')
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)
    st.caption("What this chart shows: measured historical traffic, not a forecast. Each cell is the average "
               "number of vehicles per hour on the selected side of the road for that weekday and hour, "
               "over all loaded data except public holidays. Darker means more traffic. The orange boxes mark "
               "the recommended window. The chart covers all 24 hours; the recommendation only considers your "
               "working hours.")

    # Month x weekday view of the measured counts. Idea adapted from
    # plot_month_dow() in heatmap.py of the aitraffic project
    # (github.com/DanieMyl/aitraffic).
    with st.expander("Measured traffic by month and weekday"):
        rows, _ = scheduler.prepare(station_data, side)
        in_shift = rows[rows['clock'].isin(scheduler.SHIFTS[shift][1])]
        month_pivot = (in_shift.assign(month=in_shift['Datum'].dt.month)
                       .groupby(['dow', 'month'])['traffic'].mean().unstack())
        fig, ax = plt.subplots(figsize=(12, 3.5))
        im = ax.imshow(month_pivot.values, aspect='auto', cmap='Blues')
        ax.set_yticks(range(len(month_pivot.index)))
        ax.set_yticklabels([scheduler.DAY_NAMES[d][:3] for d in month_pivot.index])
        ax.set_xticks(range(len(month_pivot.columns)))
        ax.set_xticklabels([month_names[m][:3] for m in month_pivot.columns])
        ax.set_xlabel("Month")
        ax.set_ylabel("Day of week")
        ax.set_title(f"{station_name} — {direction_choice}, {work_hours}", fontsize=10)
        plt.colorbar(im, label='Average vehicles per hour')
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)
        st.caption("What this chart shows: measured historical traffic within your working hours, averaged "
                   f"per month and weekday ({data_period}). Unlike the seasonal chart above, these are counts, "
                   "not model values. Months without data are left blank.")

    st.subheader("Top 5 windows")
    top5 = windows.head(5).assign(
        Window=[scheduler.window_label(int(r.dow), int(r.clock), window_hours) for r in windows.head(5).itertuples()])
    st.dataframe(
        top5[['Window', 'avg_traffic', 'avg_truck_ratio', 'score']]
        .rename(columns={'avg_traffic': 'Avg vehicles/hour', 'avg_truck_ratio': 'Truck share', 'score': 'Score (0–1)'})
        .style.format({'Avg vehicles/hour': '{:.0f}', 'Truck share': '{:.1%}', 'Score (0–1)': '{:.2f}'})
        .background_gradient(subset=['Score (0–1)'], cmap='Greens'),
        width='stretch',
        hide_index=True,
    )

    with st.expander("How the score is calculated"):
        st.write(f"Each {window_hours}-hour window gets two sub-scores, computed on the window's averages, "
                 "which are multiplied:")
        st.markdown(
            "- **Traffic score** = 1 − (average traffic in this window ÷ highest average traffic among the "
            "windows inside your working hours)\n"
            "- **Truck score** = 1 − average share of trucks in this window\n"
            "- **Score** = traffic score × truck score. A window only scores well if both are good."
        )
        pc1, pc2, pc3 = st.columns(3)
        pc1.metric("Traffic score (recommended window)", f"{best['traffic_score']:.2f}")
        pc2.metric("Truck score (recommended window)", f"{1-best['avg_truck_ratio']:.2f}")
        pc3.metric("Score (recommended window)", f"{best['score']:.2f}")

    # --- Network map ----------------------------------------------------
    st.subheader("A3 network overview")

    if duration_weeks > 6 and best_month is not None:
        month_mask = df['Datum'].dt.month == best_month
        station_avg_traffic = df[month_mask].groupby('Zst')['total_traffic'].mean().reset_index()
        map_period_label = f"average for {month_names[best_month]}, the month of the seasonal alternative"
    else:
        station_avg_traffic = df.groupby('Zst')['total_traffic'].mean().reset_index()
        map_period_label = "average over all loaded data"
    station_avg_traffic.columns = ['DZ_Nr', 'avg_traffic']

    st.caption(f"Each dot is a counting station. Colour shows its average traffic, both directions "
               f"({map_period_label}), relative to the busiest station: green = under 40% of the busiest, "
               f"orange = 40–70%, red = over 70%, grey = no data. Your selection ({station_name}) has a blue ring. "
               f"The dashed line connects stations from west to east and only roughly follows the road. "
               f"Map tiles need an internet connection.")

    map_data = coords.merge(station_avg_traffic, on='DZ_Nr', how='left')
    map_data['map_score'] = 1 - (map_data['avg_traffic'] / map_data['avg_traffic'].max())
    map_data = map_data.dropna(subset=['lat', 'lon'])

    m = folium.Map(location=[49.6, 10.5], zoom_start=8)

    legend_html = '''
    <div style="position: fixed; bottom: 50px; left: 50px; z-index:9999; background: white; padding: 10px; border-radius: 5px; font-size: 14px;">
    <b>Traffic level</b><br>
    <span style="color:green;">●</span> Low (good for roadworks)<br>
    <span style="color:orange;">●</span> Medium<br>
    <span style="color:red;">●</span> High (avoid)<br>
    <span style="color:gray;">●</span> No data<br>
    <span style="color:blue;">○</span> Selected station
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))

    route_coords = map_data.sort_values('lon')[['lat','lon']].values.tolist()
    folium.PolyLine(route_coords, color='#1f77b4', weight=5, opacity=0.85, dash_array='10').add_to(m)

    for i, row in map_data.iterrows():
        if pd.isna(row['map_score']):
            color = 'gray'
        elif row['map_score'] > 0.6:
            color = 'green'
        elif row['map_score'] > 0.3:
            color = 'orange'
        else:
            color = 'red'

        is_selected = row['DZ_Nr'] == station_id
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=12 if is_selected else 7,
            color='blue' if is_selected else color,
            fill=True,
            fill_color=color,
            fill_opacity=0.8,
            popup=f"{row['DZ_Name']}<br>{row['avg_traffic']:.0f} vehicles/hour" if not pd.isna(row['avg_traffic']) else f"{row['DZ_Name']}<br>no data"
        ).add_to(m)

    st_folium(m, height=500, use_container_width=True, key="a3_map", returned_objects=[])


if st.session_state.show_results:
    if st.session_state.get("inputs") != current_inputs:
        st.info("The inputs above have changed. The results below are still for the previous inputs; "
                "click \"Find best schedule\" to update them.")
    try:
        show_results()
    except Exception as e:
        st.error("Something went wrong while computing the schedule for these inputs. "
                 "Try a different station or setting.")
        with st.expander("Technical details"):
            st.code(f"{type(e).__name__}: {e}")

with st.expander("About the data"):
    coverage = coords[['DZ_Nr', 'DZ_Name', 'name_status']].copy()
    coverage['Traffic data loaded'] = coverage['DZ_Nr'].isin(stations_with_data).map({True: 'yes', False: 'no'})
    coverage['Station forecast'] = coverage['DZ_Nr'].astype(int).astype(str).isin(prophet_results.keys()).map({True: 'yes', False: 'no (fallback)'})
    if not check_table.empty:
        quality = (check_table.groupby('station')
                   .agg(estimated=('estimated_share', 'mean'), implausible=('implausible_flags', 'sum'))
                   .reset_index())
        coverage = coverage.merge(quality, left_on='DZ_Nr', right_on='station', how='left').drop(columns='station')
        coverage['estimated'] = coverage['estimated'].map(lambda v: '' if pd.isna(v) else f"{v:.0%}")
        coverage['implausible'] = coverage['implausible'].map(lambda v: '' if pd.isna(v) else f"{int(v):,}")
    coverage['name_status'] = coverage['name_status'].map(
        {'ok': '', 'repaired': 'repaired', 'damaged': 'damaged in source'})
    st.write(f"Hourly traffic counts: BASt (Bundesanstalt für Straßenwesen), years "
             f"{', '.join(str(y) for y in years_loaded)}. Station locations and direction names: BASt "
             f"`{coords.attrs.get('source_file', 'Jawe')}`, A3 in Bavaria only. "
             f"{len(stations_with_data & set(coords['DZ_Nr']))} of {len(coords)} stations have traffic data loaded.")
    st.caption("\"estimated\": share of hourly counts BASt marked as estimated ('s'). \"implausible\": counts "
               "marked implausible ('u'). \"Name\": 'repaired' means umlauts lost in the source file were "
               "restored from the Jawe2022 names in analysis.ipynb (checked letter by letter).")
    st.dataframe(coverage.rename(columns={'DZ_Nr': 'Station ID', 'DZ_Name': 'Station', 'name_status': 'Name',
                                          'estimated': 'Estimated', 'implausible': 'Implausible'}),
                 width='stretch', hide_index=True)
