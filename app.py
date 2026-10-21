import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from data_utils import load_traffic_data, load_coordinates, BASE_DIR
import datetime
import json
import os
import requests

st.set_page_config(layout="wide", page_title="A3 Roadwork Scheduler")

st.title("A3 Roadwork Scheduler")
st.write("Suggests when to schedule roadworks at a counting station on the A3 motorway (Bavaria), "
         "based on historical hourly traffic counts from BASt.")

SETUP_HINT = ("See the README section \"Setting up your data folders\": the app needs year folders "
              "(for example `2019/`, `2023/`) with BASt hourly CSV files, and `Jawe2022.csv`, "
              f"in the project folder (`{BASE_DIR}`).")

@st.cache_data
def load_data():
    df = load_traffic_data()
    coords = load_coordinates()
    return df, coords

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
    df, coords = load_data()
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
    st.error(f"`Jawe2022.csv` was loaded but contains no A3 stations. {SETUP_HINT}")
    st.stop()

days_map = {1:'Mon', 2:'Tue', 3:'Wed', 4:'Thu', 5:'Fri', 6:'Sat', 7:'Sun'}
day_names_full = {'Mon':'Monday', 'Tue':'Tuesday', 'Wed':'Wednesday', 'Thu':'Thursday',
                  'Fri':'Friday', 'Sat':'Saturday', 'Sun':'Sunday'}
month_names = {1:'January',2:'February',3:'March',4:'April',5:'May',6:'June',
               7:'July',8:'August',9:'September',10:'October',11:'November',12:'December'}

years_loaded = sorted(df['year'].unique())
stations_with_data = set(df['Zst'].unique())
st.caption(f"Data loaded: {len(df):,} hourly records from {len(stations_with_data)} stations, "
           f"years {', '.join(str(y) for y in years_loaded)}. "
           f"{len(prophet_results)} stations have a precomputed seasonal forecast.")

# --- Inputs -----------------------------------------------------------------
with st.container(border=True):
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Where**")
        station_name = st.selectbox("Counting station", sorted(coords['DZ_Name'].dropna().unique()))
        station_row = coords[coords['DZ_Name']==station_name].iloc[0]
        station_id = station_row['DZ_Nr']
        dir1_label = f"→ {station_row['Fernziel_Ri1']}" if pd.notna(station_row['Fernziel_Ri1']) else "Direction 1"
        dir2_label = f"→ {station_row['Fernziel_Ri2']}" if pd.notna(station_row['Fernziel_Ri2']) else "Direction 2"
        direction_choice = st.radio(
            "Affected side of the road",
            ["Both directions (full closure)", dir1_label, dir2_label],
        )
        if station_id not in stations_with_data:
            st.warning("No traffic counts are loaded for this station, so no schedule can be computed. "
                       "Stations with data are listed in the table under \"About the data\".")
    with right:
        st.markdown("**When**")
        earliest_start = st.date_input("Earliest possible start date", value=datetime.date.today())
        duration_weeks = st.slider("Construction duration (weeks)", 1, 26, 4)
        work_hours = st.select_slider("Daily working hours",
                                        options=["Night only (22-06)", "Day (06-18)", "24h (always)"],
                                        value="Day (06-18)")

    current_inputs = (station_id, duration_weeks, work_hours, direction_choice, earliest_start)
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
    direction_choice = st.session_state.direction_choice
    dir1_label = st.session_state.dir1_label
    dir2_label = st.session_state.dir2_label
    earliest_start = st.session_state.earliest_start

    station_data = df[df['Zst'] == station_id].copy()

    if station_data.empty:
        st.error(f"No traffic data is loaded for {station_name}, so no schedule can be computed. "
                 "Pick a different station.")
        return

    if direction_choice == dir1_label:
        station_data['effective_traffic'] = station_data['KFZ_R1']
        station_data['effective_trucks'] = station_data['Lkw_R1']
    elif direction_choice == dir2_label:
        station_data['effective_traffic'] = station_data['KFZ_R2']
        station_data['effective_trucks'] = station_data['Lkw_R2']
    else:
        station_data['effective_traffic'] = station_data['total_traffic']
        station_data['effective_trucks'] = station_data['total_trucks']

    station_data['effective_truck_ratio'] = station_data['effective_trucks'] / station_data['effective_traffic']

    if work_hours == "Night only (22-06)":
        hour_mask = (station_data['Stunde'] >= 22) | (station_data['Stunde'] <= 6)
    elif work_hours == "Day (06-18)":
        hour_mask = (station_data['Stunde'] >= 6) & (station_data['Stunde'] <= 18)
    else:
        hour_mask = pd.Series([True]*len(station_data), index=station_data.index)

    relevant = station_data[hour_mask]

    hourly_scores = relevant.groupby(['Wotag','Stunde']).agg(
        avg_traffic=('effective_traffic','mean'),
        avg_truck_ratio=('effective_truck_ratio','mean')
    ).reset_index()
    hourly_scores['day_name'] = hourly_scores['Wotag'].map(days_map)
    hourly_scores['score'] = 1 - (hourly_scores['avg_traffic'] / hourly_scores['avg_traffic'].max())
    hourly_scores['final_score'] = hourly_scores['score'] * (1 - hourly_scores['avg_truck_ratio'])
    hourly_scores = hourly_scores.dropna(subset=['final_score'])

    if hourly_scores.empty:
        st.error("There is not enough usable traffic data for this station and these working hours "
                 "to compute a schedule.")
        return

    top5 = hourly_scores.sort_values('final_score', ascending=False).head(5)
    worst = hourly_scores.sort_values('final_score').iloc[0]
    best = hourly_scores.sort_values('final_score', ascending=False).iloc[0]
    reduction = (1 - best['avg_traffic']/worst['avg_traffic']) * 100

    total_hours = duration_weeks * 7 * (8 if work_hours != "24h (always)" else 24)
    co2_best = best['avg_traffic'] * 0.24 * total_hours
    co2_worst = worst['avg_traffic'] * 0.24 * total_hours

    target_weekday = int(best['Wotag']) - 1
    days_ahead = (target_weekday - earliest_start.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    start_date = earliest_start + datetime.timedelta(days=days_ahead)
    end_date = start_date + datetime.timedelta(weeks=duration_weeks)

    best_hour = int(best['Stunde'])
    best_day_full = day_names_full[best['day_name']]
    window_label = f"{best_hour:02d}:00–{(best_hour + 4) % 24:02d}:00"

    # --- Headline -------------------------------------------------------
    with st.container(border=True):
        st.markdown("#### Recommended time for the roadworks")
        st.markdown(f"## {best_day_full}s, {window_label}, from {start_date.strftime('%d %B %Y')} "
                    f"to {end_date.strftime('%d %B %Y')}")
        st.write(f"Station: **{station_name}**. Affected side: **{direction_choice}**. "
                 f"Working hours: **{work_hours}**. The work slot repeats every week until the project ends.")
        st.caption(
            f"How this was chosen: every weekday-and-hour slot inside your working hours was scored using the "
            f"historical counts for this station ({', '.join(str(y) for y in years_loaded)} data). "
            f"Slots with less traffic on the affected side and a lower share of trucks score higher; "
            f"{best_day_full} at {best_hour:02d}:00 scored highest. "
            f"The start date is the first {best_day_full} after your earliest start date."
        )

    c1, c2, c3 = st.columns(3)
    c1.metric("Average traffic in the recommended hour", f"{best['avg_traffic']:.0f} vehicles/hour")
    c2.metric("Less traffic than the worst slot", f"{reduction:.0f}%",
              help=f"Compared with the lowest-scoring slot inside your working hours "
                   f"({day_names_full[worst['day_name']]} {int(worst['Stunde']):02d}:00, "
                   f"{worst['avg_traffic']:.0f} vehicles/hour).")
    c3.metric("Estimated CO2 avoided over the project", f"{(co2_worst-co2_best)/1000:.1f} t",
              help="Rough estimate: assumes each affected vehicle drives a 2 km detour at 120 g CO2/km "
                   "(0.24 kg per vehicle), compared with working in the worst slot.")

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

        days_ahead_seasonal = (target_weekday - candidate.weekday()) % 7
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
    full_pivot = station_data.groupby(['Wotag','Stunde'])['effective_traffic'].mean().unstack()
    fig, ax = plt.subplots(figsize=(12, 4))
    im = ax.imshow(full_pivot.values, aspect='auto', cmap='Blues')
    ax.set_yticks(range(len(full_pivot.index)))
    ax.set_yticklabels([days_map.get(d, d) for d in full_pivot.index])
    ax.set_xticks(range(len(full_pivot.columns)))
    ax.set_xticklabels([int(h) for h in full_pivot.columns], fontsize=8)
    ax.set_xlabel("Hour of day (BASt 'Stunde' value)")
    ax.set_ylabel("Day of week")
    ax.set_title(f"{station_name} — {direction_choice}", fontsize=10)
    if best['Wotag'] in full_pivot.index and best['Stunde'] in full_pivot.columns:
        row = list(full_pivot.index).index(best['Wotag'])
        col = list(full_pivot.columns).index(best['Stunde'])
        ax.add_patch(Rectangle((col - 0.5, row - 0.5), 1, 1, fill=False, edgecolor='#e8590c', linewidth=2.5))
    plt.colorbar(im, label='Average vehicles per hour')
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)
    st.caption("What this chart shows: measured historical traffic, not a forecast. Each cell is the average "
               "number of vehicles per hour on the selected side of the road for that weekday and hour, "
               "over all loaded years. Darker means more traffic. The orange box marks the recommended slot. "
               "The chart covers all 24 hours; the recommendation only considers your working hours.")

    st.subheader("Top 5 time slots")
    st.dataframe(
        top5[['day_name','Stunde','avg_traffic','avg_truck_ratio','final_score']]
        .rename(columns={'day_name':'Day','Stunde':'Hour','avg_traffic':'Avg vehicles/hour',
                         'avg_truck_ratio':'Truck share','final_score':'Score (0–1)'})
        .style.format({'Hour':'{:.0f}','Avg vehicles/hour':'{:.0f}','Truck share':'{:.1%}','Score (0–1)':'{:.2f}'})
        .background_gradient(subset=['Score (0–1)'], cmap='Greens'),
        width='stretch',
        hide_index=True,
    )

    with st.expander("How the score is calculated"):
        st.write("Each slot gets two sub-scores, which are multiplied:")
        st.markdown(
            "- **Traffic score** = 1 − (average traffic in this slot ÷ highest average traffic among the slots "
            "inside your working hours)\n"
            "- **Truck score** = 1 − average share of trucks in this slot\n"
            "- **Score** = traffic score × truck score. A slot only scores well if both are good."
        )
        pc1, pc2, pc3 = st.columns(3)
        pc1.metric("Traffic score (recommended slot)", f"{best['score']:.2f}")
        pc2.metric("Truck score (recommended slot)", f"{1-best['avg_truck_ratio']:.2f}")
        pc3.metric("Score (recommended slot)", f"{best['final_score']:.2f}")

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
    coverage = coords[['DZ_Nr', 'DZ_Name']].copy()
    coverage['Traffic data loaded'] = coverage['DZ_Nr'].isin(stations_with_data).map({True: 'yes', False: 'no'})
    coverage['Station forecast'] = coverage['DZ_Nr'].astype(int).astype(str).isin(prophet_results.keys()).map({True: 'yes', False: 'no (fallback)'})
    st.write(f"Hourly traffic counts: BASt (Bundesanstalt für Straßenwesen), years "
             f"{', '.join(str(y) for y in years_loaded)}. Station locations and direction names: BASt `Jawe2022.csv`. "
             f"{len(stations_with_data & set(coords['DZ_Nr']))} of {len(coords)} A3 stations have traffic data loaded.")
    st.dataframe(coverage.rename(columns={'DZ_Nr': 'Station ID', 'DZ_Name': 'Station'}),
                 width='stretch', hide_index=True)
