import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import matplotlib.pyplot as plt
from data_utils import load_traffic_data, load_coordinates
import datetime
import json
import requests

st.set_page_config(layout="wide", page_title="A3 Roadwork Scheduler")

st.title("🚧 A3 Roadwork Scheduler")
st.write("Enter a location, direction, and construction duration to find the best time to schedule it")

@st.cache_data
def load_data():
    df = load_traffic_data()
    coords = load_coordinates()
    return df, coords

@st.cache_data
def load_prophet_results():
    try:
        with open('prophet_results.json') as f:
            return json.load(f)
    except FileNotFoundError:
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
df, coords = load_data()
days_map = {1:'Mon', 2:'Tue', 3:'Wed', 4:'Thu', 5:'Fri', 6:'Sat', 7:'Sun'}
month_names = {1:'January',2:'February',3:'March',4:'April',5:'May',6:'June',
               7:'July',8:'August',9:'September',10:'October',11:'November',12:'December'}

col1, col2, col3, col4 = st.columns(4)
with col1:
    station_name = st.selectbox("📍 Location", sorted(coords['DZ_Name'].dropna().unique()))
with col2:
    duration_weeks = st.slider("⏱️ Construction duration (weeks)", 1, 26, 4)
with col3:
    work_hours = st.select_slider("🕐 Daily working hours",
                                    options=["Night only (22-06)", "Day (06-18)", "24h (always)"],
                                    value="Day (06-18)")
with col4:
    earliest_start = st.date_input("📅 Earliest possible start date", value=datetime.date.today())

station_row = coords[coords['DZ_Name']==station_name].iloc[0]
station_id = station_row['DZ_Nr']
dir1_label = f"→ {station_row['Fernziel_Ri1']}" if pd.notna(station_row['Fernziel_Ri1']) else "Direction 1"
dir2_label = f"→ {station_row['Fernziel_Ri2']}" if pd.notna(station_row['Fernziel_Ri2']) else "Direction 2"

direction_choice = st.radio(
    "🛣️ Which side of the road is affected?",
    ["Both directions (full closure)", dir1_label, dir2_label],
    horizontal=True
)

if "show_results" not in st.session_state:
    st.session_state.show_results = False

if st.button("🔍 Find Best Schedule", type="primary"):
    st.session_state.show_results = True
    st.session_state.station_id = station_id
    st.session_state.station_name = station_name
    st.session_state.duration_weeks = duration_weeks
    st.session_state.work_hours = work_hours
    st.session_state.direction_choice = direction_choice
    st.session_state.dir1_label = dir1_label
    st.session_state.dir2_label = dir2_label
    st.session_state.earliest_start = earliest_start

if st.session_state.show_results:
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
        st.error("No data available for this station.")
    else:
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

        st.success(f"### ✅ Recommended schedule: **{start_date.strftime('%d %B')} → {end_date.strftime('%d %B')}**")
        st.write(f"Affecting: **{direction_choice}** — Work during **{best['day_name']}s, {int(best['Stunde'])}:00–{int(best['Stunde'])+4}:00**, repeating weekly until the project is complete.")

        st.subheader("📅 Project Timeline")
        t1, t2, t3 = st.columns(3)
        t1.metric("Earliest possible start", earliest_start.strftime('%d %B %Y'))
        t2.metric("Recommended start", start_date.strftime('%d %B %Y'))
        t3.metric("Recommended end", end_date.strftime('%d %B %Y'))

        if duration_weeks <= 2:
            weather = get_weather_outlook(station_row['lat'], station_row['lon'], start_date)
            if weather:
                rain, temp = weather
                st.write(f"🌦️ Weather outlook for {start_date.strftime('%d %B')}: **{temp:.0f}°C**, **{rain:.1f}mm** precipitation expected. (Forecasts beyond ~15 days aren't reliable, so this only shows for near-term, short-duration projects.)")

        best_month = None
        if duration_weeks > 6:
            station_prophet = prophet_results.get(str(int(station_id)))

            if station_prophet:
                month_traffic = {int(k): v for k, v in station_prophet.items()}
            else:
                month_traffic = {1: 2751, 2: 2924, 3: 3043, 4: 3064, 5: 2945, 6: 2899,
                                  7: 3209, 8: 3011, 9: 2837, 10: 2636, 11: 2210, 12: 2065}
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

            st.info(f"🍂 **Seasonal tip:** since this project runs {duration_weeks} weeks, starting in **{month_names[best_month]}** (lowest A3 traffic month overall, on or after your earliest start date) instead could reduce disruption further. Suggested alternative: **{seasonal_start.strftime('%d %B %Y')} → {seasonal_end.strftime('%d %B %Y')}**, still on {best['day_name']}s. *(This forecast also accounts for German public holidays — though with only a couple of years of training data, the holiday-specific effect is a rough signal rather than a precise one.)*")

        c1, c2, c3 = st.columns(3)
        c1.metric("Traffic reduction vs worst hour", f"{reduction:.0f}%")
        c2.metric("CO2 saved over project", f"{(co2_worst-co2_best)/1000:.1f} tons")
        c3.metric("Avg traffic at best time", f"{best['avg_traffic']:.0f}/hr")

        st.subheader("📐 Scoring Breakdown")
        st.write("Recommendation combines two factors, in priority order:")
        pc1, pc2, pc3 = st.columns(3)
        pc1.metric("1️⃣ Congestion impact (primary)", f"{best['score']:.2f} / 1.00")
        pc2.metric("2️⃣ Freight/commuter impact (secondary)", f"{1-best['avg_truck_ratio']:.2f} / 1.00")
        pc3.metric("→ Combined priority score", f"{best['final_score']:.2f} / 1.00")

        st.subheader("Top 5 Specific Time Windows")
        st.dataframe(
            top5[['day_name','Stunde','avg_traffic','avg_truck_ratio','final_score']]
            .rename(columns={'day_name':'Day','Stunde':'Hour','avg_traffic':'Avg Traffic/hr','avg_truck_ratio':'Truck Ratio','final_score':'Score'})
            .style.format({'Hour':'{:.0f}','Avg Traffic/hr':'{:.0f}','Truck Ratio':'{:.1%}','Score':'{:.2f}'})
            .background_gradient(subset=['Score'], cmap='RdYlGn'),
            use_container_width=True
        )

        st.subheader("📊 Full Weekly Pattern")
        full_pivot = station_data.groupby(['Wotag','Stunde'])['effective_traffic'].mean().unstack()
        fig, ax = plt.subplots(figsize=(12,4))
        im = ax.imshow(full_pivot.values, aspect='auto', cmap='RdYlGn_r')
        ax.set_yticks(range(7))
        ax.set_yticklabels(['Mon','Tue','Wed','Thu','Fri','Sat','Sun'])
        ax.set_xlabel("Hour of day")
        ax.set_title(f"{station_name} — {direction_choice}")
        plt.colorbar(im, label='Avg vehicles/hour')
        st.pyplot(fig)

        st.caption(f"For your {duration_weeks}-week project ({work_hours.lower()}, {direction_choice}), repeating work during **{best['day_name']} {int(best['Stunde'])}:00** each week minimizes traffic disruption by {reduction:.0f}% and saves an estimated {(co2_worst-co2_best)/1000:.1f} tons of CO2 over the full project.")

        st.subheader("🗺️ A3 Network Overview")

        if duration_weeks > 6 and best_month is not None:
            month_mask = df['Datum'].dt.month == best_month
            station_avg_traffic = df[month_mask].groupby('Zst')['total_traffic'].mean().reset_index()
            map_period_label = f"for {month_names[best_month]} (recommended season)"
        else:
            station_avg_traffic = df.groupby('Zst')['total_traffic'].mean().reset_index()
            map_period_label = "all-time average"
        station_avg_traffic.columns = ['DZ_Nr', 'avg_traffic']

        st.caption(f"📍 The blue-ringed station is your selection ({station_name}). Colors show relative traffic levels across the A3 network ({map_period_label}) — use this to check if a nearby alternative station might be quieter.")

        map_data = coords.merge(station_avg_traffic, on='DZ_Nr', how='left')
        map_data['map_score'] = 1 - (map_data['avg_traffic'] / map_data['avg_traffic'].max())

        m = folium.Map(location=[49.6, 10.5], zoom_start=8)

        legend_html = '''
        <div style="position: fixed; bottom: 50px; left: 50px; z-index:9999; background: white; padding: 10px; border-radius: 5px; font-size: 14px;">
        <b>Traffic Level</b><br>
        <span style="color:green;">●</span> Low (good for roadworks)<br>
        <span style="color:orange;">●</span> Medium<br>
        <span style="color:red;">●</span> High (avoid)<br>
        <span style="color:blue;">●</span> Selected station
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))

        route_coords = map_data.dropna(subset=['lat','lon']).sort_values('lon')[['lat','lon']].values.tolist()
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
                popup=f"{row['DZ_Name']}<br>{row['avg_traffic']:.0f} veh/hr" if not pd.isna(row['avg_traffic']) else row['DZ_Name']
            ).add_to(m)

        st_folium(m, width=1400, height=500, key="a3_map")