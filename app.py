import datetime
import html
import json
import math
import os

import altair as alt
import folium
import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium

import scheduler
from data_utils import (BASE_DIR, check_data, load_coordinates, load_traffic_data, resolve_data_dir,
                        year_status)

st.set_page_config(page_title="A3 Roadwork Scheduler", layout="wide")

ACCENT = '#2563eb'
MARK = '#d9480f'          # recommended window in charts; contrasts with the blue scale
MUTED = '#6b7280'
SCALE = ['#f7fafd', '#c9dcf5', '#7ea6e3', '#3a6fd0']      # light to accent, no near-black blocks
AXIS = dict(labelFontSize=11, titleFontSize=11, labelColor='#4b5563', titleColor='#374151',
            domainColor='#d1d5db', tickColor='#d1d5db')

st.markdown("""
<style>
.block-container {max-width: 1100px; padding-top: 2rem; padding-bottom: 4rem;}
h1 {font-weight: 650; letter-spacing: -0.01em;}
.step {font-size: 0.8rem; font-weight: 600; color: #2563eb; text-transform: uppercase; letter-spacing: 0.06em;}
.result {border: 1px solid #dbe4f0; border-left: 5px solid #2563eb; border-radius: 12px;
         padding: 1.25rem 1.5rem; margin: 0.5rem 0 1.25rem 0; background: #fbfcfe;}
.result .label {color: #4b5563; font-size: 0.9rem; margin-bottom: 0.2rem;}
.result .window {font-size: 2rem; font-weight: 650; color: #111827; line-height: 1.2;}
.result .dates {color: #374151; margin-top: 0.3rem;}
.facts {display: flex; flex-wrap: wrap; gap: 0.75rem 2.5rem; margin-top: 1rem;}
.fact .value {font-size: 1.35rem; font-weight: 600; color: #111827;}
.fact .what {color: #4b5563; font-size: 0.85rem;}
.result .note {color: #4b5563; font-size: 0.85rem; margin-top: 0.9rem;}
@media (max-width: 640px) {
  .result {padding: 1rem;}
  .result .window {font-size: 1.5rem;}
  .fact .value {font-size: 1.15rem;}
}
</style>
""", unsafe_allow_html=True)

SIDE_ANY = 'both'
SHIFT_LABELS = {'day': 'Day 06–18', 'night': 'Night 22–06', 'any': 'Any time'}
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


# --- Data ---------------------------------------------------------------------
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
def load_accuracy():
    try:
        with open(os.path.join(BASE_DIR, 'accuracy.json'), encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


@st.cache_data
def recommendation(data_dir, station, side, shift, hours, earliest, weeks):
    df, _ = load_data(data_dir)
    return scheduler.recommend(df[df['Zst'] == station], side, shift, hours, earliest, weeks)


def weather_outlook(lat, lon, day):
    """Open-Meteo forecast; only reliable within about 15 days. None if unavailable."""
    if not 0 <= (day - datetime.date.today()).days <= 15:
        return None
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=5, params={
            'latitude': lat, 'longitude': lon, 'daily': 'precipitation_sum,temperature_2m_max',
            'timezone': 'Europe/Berlin', 'start_date': str(day), 'end_date': str(day)})
        r.raise_for_status()
        daily = r.json()['daily']
        return daily['precipitation_sum'][0], daily['temperature_2m_max'][0]
    except Exception:
        return None


def months_text(months):
    """'Sep–Dec', 'Nov–Feb' (across the year end) or 'all months'."""
    months = set(months)
    if len(months) == 12:
        return "all months"
    first = next(m for m in range(1, 13) if ((m - 2) % 12) + 1 not in months and m in months)
    last = first
    while (last % 12) + 1 in months:
        last = (last % 12) + 1
    return MONTHS[first - 1] if first == last else f"{MONTHS[first - 1]}–{MONTHS[last - 1]}"


def distance_km(lat1, lon1, lat2, lon2):
    dx = (lon1 - lon2) * 111.3 * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat1 - lat2) * 111.3
    return math.hypot(dx, dy)


st.title("A3 Roadwork Scheduler")
st.markdown("Find the quietest time for roadworks at a traffic counting station on the A3 motorway in Bavaria, "
            "based on measured hourly traffic counts.")

data_dir, is_sample = resolve_data_dir()
try:
    df, coords = load_data(data_dir)
except Exception as e:
    st.error("No traffic data was found, so the app cannot make a recommendation yet. "
             "Run `python scripts/fetch_data.py` (see the README, section \"Data\") and reload this page.")
    with st.expander("Technical details"):
        st.code(f"{type(e).__name__}: {e}")
    st.stop()

years = year_status(data_dir)
used_years = sorted(int(y) for y in df['year'].unique())
stations_with_data = set(int(z) for z in df['Zst'].unique())
check_issues, check_table = run_data_check(df, not is_sample)
accuracy = load_accuracy()

source_line = f"Data: BASt hourly counts {', '.join(map(str, used_years))}"
if years['missing'] and not is_sample:
    source_line += f" ({', '.join(map(str, years['missing']))} not installed)"
source_line += f" · {len(stations_with_data)} stations with data."
if is_sample:
    st.info("Demo mode: only a small sample of the data is installed (3 stations, March–June 2023). "
            "Results are for trying the app out. See the README, section \"Data\", for the full data.")
st.caption(source_line)

# --- Inputs ---------------------------------------------------------------------
with st.expander("Advanced"):
    show_all = st.checkbox("Also list stations without traffic data", value=False)
    st.caption("Years used: " + ', '.join(map(str, used_years)) + ". Change them with the environment variable "
               "A3_YEARS before starting the app (README, section \"Data\"). Times are local clock times.")

choices = coords if show_all else coords[coords['DZ_Nr'].isin(stations_with_data)]
choices = choices.assign(has_data=choices['DZ_Nr'].isin(stations_with_data))
choices = choices.sort_values(['has_data', 'DZ_Name'], ascending=[False, True])
labels = {int(r.DZ_Nr): r.DZ_Name if r.has_data else f"{r.DZ_Name} (no data)" for r in choices.itertuples()}

c1, c2, c3 = st.columns(3, gap="large")
with c1:
    st.markdown('<div class="step">1 · Where</div>', unsafe_allow_html=True)
    station_id = st.selectbox("Counting station", list(labels), format_func=labels.get)
    station = coords[coords['DZ_Nr'] == station_id].iloc[0]
    side_options = {SIDE_ANY: "Both directions (full closure)",
                    'R1': f"Towards {station['Fernziel_Ri1']}" if pd.notna(station['Fernziel_Ri1']) else "Direction 1",
                    'R2': f"Towards {station['Fernziel_Ri2']}" if pd.notna(station['Fernziel_Ri2']) else "Direction 2"}
    side = st.radio("Closed lanes", list(side_options), format_func=side_options.get)
with c2:
    st.markdown('<div class="step">2 · Work</div>', unsafe_allow_html=True)
    shift = st.segmented_control("Working hours", list(SHIFT_LABELS), format_func=SHIFT_LABELS.get,
                                 default='day') or 'day'
    max_hours = min(12, len(scheduler.SHIFTS[shift][1]))
    hours = st.slider("Hours per work session", 1, max_hours, min(4, max_hours),
                      help="One uninterrupted work session. The app looks for the quietest block of this length.")
with c3:
    st.markdown('<div class="step">3 · When</div>', unsafe_allow_html=True)
    earliest = st.date_input("Earliest start", value=datetime.date.today(), format="DD.MM.YYYY")
    weeks = st.slider("Duration (weeks, one session per week)", 1, 26, 4)

st.divider()

# --- Result -----------------------------------------------------------------------
if station_id not in stations_with_data:
    nearby = sorted(((distance_km(station['lat'], station['lon'], r.lat, r.lon), r.DZ_Name)
                     for r in coords.itertuples()
                     if r.DZ_Nr in stations_with_data), key=lambda x: x[0])[:2]
    near = ' and '.join(f"{name} ({d:.0f} km away)" for d, name in nearby)
    st.info(f"There are no traffic counts for {station['DZ_Name']} in the years used, so no recommendation "
            f"can be made here. Stations with data nearby: {near}.")
    st.stop()

rec = recommendation(data_dir, station_id, side, shift, hours, earliest, weeks)
if rec is None:
    st.info("There are not enough counts for this station and these working hours to make a recommendation. "
            "Try another station or longer working hours.")
    st.stop()

best, busiest = rec['best'], rec['busiest']
window_text = rec['label'].split(', ', 1)[1]
low_high = scheduler.expected_range(rec['expected'], accuracy)
season_text = months_text(scheduler.season_months(rec['months'], rec['estimate_profile']))
last_session = rec['start_date'] + datetime.timedelta(weeks=weeks - 1)
if low_high:
    traffic_value = f"{low_high[0]:,.0f}–{low_high[1]:,.0f}"
    traffic_note = (f"Estimate from the {', '.join(map(str, used_years))} counts for {season_text}. In tests on past "
                    f"weeks, the measured traffic was inside this range about 8 times out of 10.")
else:
    traffic_value = f"about {rec['expected']:,.0f}"
    traffic_note = f"Estimate from the {', '.join(map(str, used_years))} counts for {season_text}."
busiest_label = scheduler.window_label(int(busiest['dow']), int(busiest['clock']), hours).replace('s, ', ' ', 1)
holiday_note = ""
if rec['holidays_on_work_days']:
    days = ', '.join(f"{d:%d %b}" for d, _ in rec['holidays_on_work_days'])
    holiday_note = f"<div class='note'>Public holiday on a work day: {html.escape(days)}.</div>"
station_note = ""
if not check_table.empty:
    row = check_table[check_table['station'] == station_id]
    if len(row) and row['estimated_share'].mean() >= 0.25:
        station_note = (f"<div class='note'>{row['estimated_share'].mean():.0%} of this station's counts are "
                        f"estimates by BASt, so its figures are less certain.</div>")

st.markdown(f"""
<div class="result">
  <div class="label">Recommended work window · {html.escape(station['DZ_Name'])} · {html.escape(side_options[side])}</div>
  <div class="window">{html.escape(rec['label'])}</div>
  <div class="dates">{weeks} weekly session{'s' if weeks > 1 else ''} of {hours} h:
     {f"{rec['start_date']:%d %b %Y} to {last_session:%d %b %Y}" if weeks > 1 else f"{rec['start_date']:%d %b %Y}"}</div>
  <div class="facts">
    <div class="fact"><div class="value">{traffic_value}</div><div class="what">vehicles per hour expected</div></div>
    <div class="fact"><div class="value">{rec['reduction']:.0%} quieter</div>
         <div class="what">than the busiest {hours}-hour window ({html.escape(busiest_label)})</div></div>
  </div>
  <div class="note">{html.escape(traffic_note)}</div>
  {holiday_note}{station_note}
</div>
""", unsafe_allow_html=True)

tab_week, tab_map, tab_month, tab_details, tab_data = st.tabs(["Week", "Map", "Months", "Details", "Data"])

with tab_week:
    day_short = [d[:3] for d in scheduler.DAY_NAMES]
    prof = rec['profile']
    cells = pd.DataFrame({'day': [day_short[i // 24] for i in range(168)], 'hour': [i % 24 for i in range(168)],
                          'traffic': prof['avg_traffic'].round().to_numpy()})
    cells['time'] = cells['hour'].map(lambda h: f"{h:02d}:00–{(h + 1) % 24:02d}:00")
    window_slots = [(int(best['start_slot']) + k) % 168 for k in range(hours)]
    base = alt.Chart(cells).encode(
        x=alt.X('hour:O', title='Time of day', axis=alt.Axis(values=list(range(0, 24, 3)), labelAngle=0,
                labelExpr="(datum.value < 10 ? '0' : '') + datum.value + ':00'", labelOverlap='parity',
                labelSeparation=12, **AXIS)),
        y=alt.Y('day:O', sort=day_short, title=None, axis=alt.Axis(labelOverlap=False, **AXIS)))
    heat = base.mark_rect().encode(
        color=alt.Color('traffic:Q', title='Vehicles/hour', scale=alt.Scale(range=SCALE),
                        legend=alt.Legend(orient='bottom', gradientLength=220, labelFontSize=11, titleFontSize=11,
                                          labelColor='#4b5563', titleColor='#374151')),
        tooltip=[alt.Tooltip('day:O', title='Day'), alt.Tooltip('time:N', title='Time'),
                 alt.Tooltip('traffic:Q', title='Vehicles/hour', format=',.0f')])
    # Outline the exact cells of the window (it may cross midnight)
    mark = alt.Chart(cells.iloc[window_slots]).mark_rect(fill=None, stroke=MARK, strokeWidth=2.5).encode(
        x='hour:O', y=alt.Y('day:O', sort=day_short))
    st.altair_chart((heat + mark).properties(height=alt.Step(30)), width='stretch')
    side_text = "both directions" if side == SIDE_ANY else side_options[side].replace('Towards', 'towards')
    st.caption(f"Average measured traffic for each day and hour ({side_text}), "
               f"all of {', '.join(map(str, used_years))} except public holidays. "
               "The orange outline marks the recommended window. Darker = more traffic.")

with tab_map:
    avg = df.groupby('Zst')['total_traffic'].mean()
    m = coords.assign(avg=coords['DZ_Nr'].map(avg).round(), selected=coords['DZ_Nr'] == station_id)
    m['traffic'] = m['avg'].map(lambda v: 'no data' if pd.isna(v) else f"{v:,.0f} vehicles/hour")
    proj = dict(type='mercator')
    route = alt.Chart(m.sort_values('lon').assign(order=range(len(m)))).mark_line(
        color='#e5e7eb', strokeWidth=4).encode(longitude='lon:Q', latitude='lat:Q', order='order:Q')
    tooltip = [alt.Tooltip('DZ_Name:N', title='Station'), alt.Tooltip('traffic:N', title='Average')]
    # Stations without counts in their own layer: Vega drops empty values from a colour scale
    no_counts = alt.Chart(m[m['avg'].isna()]).mark_circle(size=45, color='#b8bec8', opacity=1).encode(
        longitude='lon:Q', latitude='lat:Q', tooltip=tooltip)
    points = alt.Chart(m[m['avg'].notna()]).mark_circle(size=70, stroke='#9ca3af', strokeWidth=0.5,
                                                        opacity=1).encode(
        longitude='lon:Q', latitude='lat:Q',
        color=alt.Color('avg:Q', title='Average vehicles/hour', scale=alt.Scale(range=SCALE, domainMin=0),
                        legend=alt.Legend(orient='bottom', gradientLength=220, labelFontSize=11, titleFontSize=11,
                                          labelColor='#4b5563', titleColor='#374151')),
        tooltip=tooltip)
    ring = alt.Chart(m[m['selected']]).mark_circle(size=320, fill=None, stroke=MARK, strokeWidth=2.5).encode(
        longitude='lon:Q', latitude='lat:Q')
    towns = pd.DataFrame([('Aschaffenburg', 49.97, 9.15, 'left'), ('Würzburg', 49.79, 9.95, 'center'),
                          ('Nürnberg', 49.45, 11.08, 'center'), ('Regensburg', 49.01, 12.10, 'center'),
                          ('Passau', 48.57, 13.43, 'right')], columns=['name', 'lat', 'lon', 'align'])
    labels_layer = alt.layer(*[alt.Chart(towns[towns['align'] == a]).mark_text(
        dy=16, fontSize=11, color=MUTED, align=a).encode(longitude='lon:Q', latitude='lat:Q', text='name:N')
        for a in ('left', 'center', 'right')])
    st.altair_chart(alt.layer(route, no_counts, points, ring, labels_layer).project(**proj).properties(height=340),
                    width='stretch')
    st.caption("Counting stations on the A3 in Bavaria, coloured by average traffic (both directions); grey = no "
               "counts. The orange ring is your station. The grey line joins the stations from west to east and "
               "only roughly follows the road.")
    with st.expander("Interactive map with streets (needs an internet connection)"):
        fmap = folium.Map(location=[49.4, 11.0], zoom_start=7, tiles='OpenStreetMap')
        for r in m.itertuples():
            folium.CircleMarker([r.lat, r.lon], radius=9 if r.selected else 5,
                                color=MARK if r.selected else ('#9ca3af' if pd.isna(r.avg) else ACCENT),
                                fill=True, fill_opacity=0.8, popup=f"{r.DZ_Name}<br>{r.traffic}").add_to(fmap)
        st_folium(fmap, height=420, use_container_width=True, key="a3_map", returned_objects=[])

with tab_month:
    rows, _ = scheduler.prepare(df[df['Zst'] == station_id], side)
    in_window = rows[(rows['dow'] * 24 + rows['clock']).isin(set(window_slots))]
    by_month = in_window.groupby(in_window['Datum'].dt.month)['traffic'].mean().reindex(range(1, 13))
    bars = pd.DataFrame({'month': MONTHS, 'traffic': by_month.round().to_numpy(),
                         'project': ['your project' if mth in rec['months'] else 'other months' for mth in range(1, 13)]})
    chart = alt.Chart(bars).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        x=alt.X('month:O', sort=MONTHS, title=None, axis=alt.Axis(labelAngle=0, **AXIS)),
        y=alt.Y('traffic:Q', title='Vehicles/hour', axis=alt.Axis(grid=True, gridColor='#eef0f3', **AXIS)),
        color=alt.Color('project:N', scale=alt.Scale(domain=['your project', 'other months'],
                                                     range=[ACCENT, '#cbd5e1']),
                        legend=alt.Legend(orient='bottom', title=None, labelFontSize=11, labelColor='#374151')),
        tooltip=[alt.Tooltip('month:O', title='Month'), alt.Tooltip('traffic:Q', title='Vehicles/hour', format=',.0f')])
    st.altair_chart(chart.properties(height=260), width='stretch')
    best_day = scheduler.DAY_NAMES[int(best['dow'])]
    quietest = by_month.idxmin() if by_month.notna().any() else None
    st.caption(f"Measured average traffic in the recommended window ({best_day}s, {window_text}) for each month "
               f"of {', '.join(map(str, used_years))}."
               + (f" Quietest month for this window: {MONTHS[quietest - 1]}." if quietest else "")
               + (" Months without bars have no counts." if by_month.isna().any() else ""))

with tab_details:
    top = rec['windows'].head(5)
    st.markdown("**The five best windows**")
    st.dataframe(pd.DataFrame({
        'Window': [scheduler.window_label(int(r.dow), int(r.clock), hours) for r in top.itertuples()],
        'Average traffic, all year (vehicles/hour)': top['avg_traffic'].round(),
        'Trucks (%)': top['avg_truck_ratio'] * 100,
        'Score (0–1)': top['score'],
    }), hide_index=True, width='stretch', column_config={
        'Average traffic, all year (vehicles/hour)': st.column_config.NumberColumn(format='%d'),
        'Trucks (%)': st.column_config.NumberColumn(format='%.1f'),
        'Score (0–1)': st.column_config.NumberColumn(format='%.2f')})
    st.markdown(
        "**How the window is chosen.** Every block of consecutive hours inside your working hours is scored on "
        "the average traffic of all measured weeks (less traffic and fewer trucks score higher). Public holidays "
        "and counts BASt marked as implausible are left out. The expected traffic is then taken from the same "
        "months of the year as your project, plus one month on either side.")
    total_hours = weeks * hours
    co2 = (float(busiest['avg_traffic']) - rec['expected']) * 0.24 * total_hours / 1000
    st.markdown(f"**Rough CO2 comparison.** Working in this window instead of the busiest one affects about "
                f"{(float(busiest['avg_traffic']) - rec['expected']) * total_hours:,.0f} fewer vehicles over the "
                f"project. If each of them drove a 2 km detour at 120 g CO2/km, that would be about {co2:,.1f} t "
                "of CO2. This is an illustration, not a measurement.")
    weather = weather_outlook(station['lat'], station['lon'], rec['start_date'])
    if weather:
        st.markdown(f"**Weather on {rec['start_date']:%d %b}** (Open-Meteo forecast): up to {weather[1]:.0f} °C, "
                    f"{weather[0]:.1f} mm precipitation.")
    if rec['holidays']:
        st.markdown("**Public holidays in Bavaria during the project:** " +
                    ', '.join(f"{d:%d %b %Y} ({n})" for d, n in rec['holidays']))

with tab_data:
    st.markdown("Hourly traffic counts and station list: Bundesanstalt für Straßenwesen (BASt), automatische "
                "Dauerzählstellen, licensed under the [Datenlizenz Deutschland – Namensnennung – Version 2.0]"
                "(https://www.govdata.de/dl-de/by-2-0). The files were reorganised and station names repaired "
                "(see DATA_LICENSE.md).")
    year_lines = [f"Years used: {', '.join(map(str, used_years))}."]
    if years['missing'] and not is_sample:
        year_lines.append(f"Configured but not installed: {', '.join(map(str, years['missing']))}.")
    if years['ignored'] and not is_sample:
        year_lines.append(f"Installed but not used: {', '.join(map(str, years['ignored']))}.")
    st.markdown(' '.join(year_lines) + f" {len(stations_with_data)} of {len(coords)} stations have counts "
                "for the years used.")
    if accuracy:
        st.markdown(f"**Accuracy in tests on past weeks:** hourly error {accuracy['hourly_mape']:.0f}%, "
                    f"recommended window among the 3 quietest in {accuracy['top3']:.0%} of "
                    f"{accuracy['tests']} tests (README, section \"Accuracy\").")
    if check_issues:
        st.markdown("**Data check findings**")
        for issue in check_issues:
            st.markdown(f"- {issue}")
    else:
        st.markdown("**Data check:** no problems found (hours per year, duplicates, impossible values).")
    table = coords[['DZ_Nr', 'DZ_Name']].assign(
        data=coords['DZ_Nr'].isin(stations_with_data).map({True: 'yes', False: 'no'}))
    if not check_table.empty:
        est = check_table.groupby('station')['estimated_share'].mean()
        table['estimated'] = table['DZ_Nr'].map(est).map(lambda v: '' if pd.isna(v) else f"{v:.0%}")
    st.dataframe(table.rename(columns={'DZ_Nr': 'Station', 'DZ_Name': 'Name', 'data': 'Counts',
                                       'estimated': 'Estimated by BASt'}), hide_index=True, width='stretch')
