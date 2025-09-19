# frontend/app.py
import streamlit as st
import pandas as pd
import pydeck as pdk
import altair as alt

st.set_page_config(page_title="Delhi AQ Dashboard", layout="wide")
st.title("🌍 Delhi Air Quality Dashboard")

# --- DATA LOADING FUNCTIONS ---
@st.cache_data
def load_csv(path, parse_dates=None):
    try:
        df = pd.read_csv(path)
        if parse_dates:
            for col in parse_dates:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors="coerce")
        return df
    except Exception as e:
        st.error(f"Error loading {path}: {e}")
        return None

# --- LOAD DATA ---
stations_df = load_csv("stations.csv", parse_dates=["to"])
forgraphs_df = load_csv("forgraphs.csv", parse_dates=["to date"])
weather_df = load_csv("weather.csv", parse_dates=["valid_time"])
forecast_df = load_csv("forecast.csv", parse_dates=["timestamp"])

if stations_df is None or forgraphs_df is None or weather_df is None or forecast_df is None:
    st.stop()

# --- MASTER CONTROLS ---
st.sidebar.header("📊 Master Controls")
time_scope = st.sidebar.selectbox(
    "Time Scope",
    options=["Past Day", "Past Week", "Past Month", "Past Year", "All Time"],
    index=1
)

granularity = st.sidebar.selectbox(
    "Granularity",
    options=["Hourly", "Daily", "Weekly", "Monthly"],
    index=0
)

# --- HELPER FUNCTION FOR TIME FILTERING & RESAMPLING ---
def filter_resample(df, time_col, numeric_cols):
    # Filter by time scope
    max_time = df[time_col].max()
    if time_scope == "Past Day":
        start_time = max_time - pd.Timedelta(days=1)
    elif time_scope == "Past Week":
        start_time = max_time - pd.Timedelta(weeks=1)
    elif time_scope == "Past Month":
        start_time = max_time - pd.Timedelta(days=30)
    elif time_scope == "Past Year":
        start_time = max_time - pd.Timedelta(days=365)
    else:
        start_time = df[time_col].min()
    df_filtered = df[df[time_col] >= start_time].copy()
    
    # Resample
    df_filtered.set_index(time_col, inplace=True)
    rule_map = {"Hourly":"1H", "Daily":"1D", "Weekly":"7D", "Monthly":"30D"}
    df_resampled = df_filtered[numeric_cols].resample(rule_map[granularity]).mean().reset_index()
    return df_resampled

# --- MAIN TABS ---
main_tabs = st.tabs(["🌫️ Pollution", "🌦️ Weather", "🔮 Predictions"])

# =========================
# POLLUTION TAB
# =========================
with main_tabs[0]:
    st.header("Pollution Data")
    sub_tabs = st.tabs(["🗺️ Map", "📈 Trends"])

    # --- MAP SUBTAB ---
    with sub_tabs[0]:
        st.subheader("Real-Time Station Map")
        pollutant_choice = st.radio("Select Pollutant", ["NO2", "O3"], horizontal=True)
        pollutant_col = "no2" if pollutant_choice == "NO2" else "o3"

        latest_station_data = stations_df.sort_values("to").drop_duplicates("station", keep="last")

        def get_color(val):
            if pd.isna(val): 
                return [180, 180, 180]
            val = float(val)
            if val < 40: return [0, 255, 0]
            elif val < 80: return [255, 255, 0]
            else: return [255, 0, 0]

        latest_station_data["color"] = latest_station_data[pollutant_col].apply(get_color)

        view_state = pdk.ViewState(latitude=28.6139, longitude=77.2090, zoom=9.5, pitch=50)

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=latest_station_data,
            get_position="[Longitude, Latitude]",
            get_fill_color="color",
            get_radius=800,
            pickable=True,
            opacity=0.8,
        )

        tooltip_html = f"<b>Station:</b> {{station}}<br/><b>{pollutant_choice}:</b> {{{pollutant_col}}} µg/m³"

        st.pydeck_chart(pdk.Deck(
            map_style="dark",
            initial_view_state=view_state,
            layers=[layer],
            tooltip={"html": tooltip_html, "style": {"backgroundColor": "black", "color": "white"}}
        ))

    # --- TRENDS SUBTAB ---
    with sub_tabs[1]:
        st.subheader("Trends Over Time")
        pollutant_graph_choice = st.selectbox("Select Pollutant for Trend Graph:", ["NO2", "O3"])
        pollutant_map = {"NO2": "no2", "O3": "ozone"}
        pollutant_col = pollutant_map[pollutant_graph_choice]

        time_col = "to date" if "to date" in forgraphs_df.columns else "to"
        df = forgraphs_df[[time_col, pollutant_col]].dropna().rename(columns={time_col:"timestamp"})
        df_plot = filter_resample(df, "timestamp", [pollutant_col])

        nearest = alt.selection_point(nearest=True, on="mouseover", fields=["timestamp"], empty="none")

        line = alt.Chart(df_plot).mark_line().encode(
            x="timestamp:T",
            y=alt.Y(f"{pollutant_col}:Q", title="Concentration (µg/m³)"),
            tooltip=[alt.Tooltip("timestamp:T"), alt.Tooltip(f"{pollutant_col}:Q", format=".2f")]
        )

        points = line.mark_circle(size=60, opacity=0).encode(
            opacity=alt.condition(nearest, alt.value(1), alt.value(0))
        )

        rule = alt.Chart(df_plot).mark_rule(color="gray").encode(
            x="timestamp:T",
            opacity=alt.condition(nearest, alt.value(0.3), alt.value(0)),
            tooltip=[alt.Tooltip("timestamp:T", format="%Y-%m-%d %H:%M"),
                     alt.Tooltip(f"{pollutant_col}:Q", format=".2f")]
        ).add_params(nearest)

        st.altair_chart(alt.layer(line, points, rule).interactive(), use_container_width=True)

        with st.expander("📊 View Data Table"):
            st.dataframe(df_plot, use_container_width=True)

# =========================
# WEATHER TAB
# =========================
with main_tabs[1]:
    st.header("Weather Data")
    variable = st.selectbox(
        "Select Weather Variable:",
        [
            "Temperature (2m above surface)",
            "Dew Point (2m above surface)",
            "Zonal Wind (u10, east-west, 10m)",
            "Meridional Wind (v10, north-south, 10m)",
            "Surface Pressure (bar)"
        ]
    )

    mapping = {
        "Temperature (2m above surface)": ("t2m", "°C"),
        "Dew Point (2m above surface)": ("d2m", "K"),
        "Zonal Wind (u10, east-west, 10m)": ("u10", "m/s"),
        "Meridional Wind (v10, north-south, 10m)": ("v10", "m/s"),
        "Surface Pressure (bar)": ("sp", "bar"),
    }

    col, unit = mapping[variable]
    df = weather_df.copy()
    df_plot = filter_resample(df.rename(columns={"valid_time":"timestamp"}), "timestamp", [col])

    if col == "t2m":
        df_plot[col] = df_plot[col] - 273.15
        unit = "°C"

    nearest = alt.selection_point(nearest=True, on="timestamp", fields=["timestamp"], empty="none")

    line = alt.Chart(df_plot).mark_line().encode(
        x="timestamp:T",
        y=alt.Y(f"{col}:Q", title=f"{variable} ({unit})"),
        tooltip=[alt.Tooltip("timestamp:T"), alt.Tooltip(f"{col}:Q", format=".2f")]
    )

    points = line.mark_circle(size=60, opacity=0).encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    )

    rule = alt.Chart(df_plot).mark_rule(color="gray").encode(
        x="timestamp:T",
        opacity=alt.condition(nearest, alt.value(0.3), alt.value(0)),
        tooltip=[alt.Tooltip("timestamp:T", format="%Y-%m-%d %H:%M"),
                 alt.Tooltip(f"{col}:Q", format=".2f")]
    ).add_params(nearest)

    st.altair_chart(alt.layer(line, points, rule).interactive(), use_container_width=True)

    with st.expander("📊 View Weather Table"):
        st.dataframe(df_plot[["timestamp", col]].dropna(), use_container_width=True)

# =========================
# PREDICTIONS TAB
# =========================
with main_tabs[2]:
    st.header("Forecast Predictions")
    stations_list = forecast_df["station"].unique()
    selected_station = st.selectbox("Select Station:", stations_list)

    df = forecast_df[forecast_df["station"] == selected_station].dropna(subset=["pred_no2","pred_o3"])
    df_plot = filter_resample(df, "timestamp", ["pred_no2","pred_o3"])
    melted = df_plot.melt("timestamp", var_name="Pollutant", value_name="Value")

    nearest = alt.selection_point(nearest=True, on="timestamp", fields=["timestamp"], empty="none")

    line = alt.Chart(melted).mark_line().encode(
        x="timestamp:T",
        y="Value:Q",
        color="Pollutant:N",
        tooltip=["timestamp:T","Pollutant:N",alt.Tooltip("Value:Q", format=".2f")]
    )

    points = line.mark_circle(size=60, opacity=0).encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    )

    rule = alt.Chart(melted).mark_rule(color="gray").encode(
        x="timestamp:T",
        opacity=alt.condition(nearest, alt.value(0.3), alt.value(0)),
        tooltip=["timestamp:T","Pollutant:N",alt.Tooltip("Value:Q", format=".2f")]
    ).add_params(nearest)

    st.altair_chart(alt.layer(line, points, rule).interactive(), use_container_width=True)

    with st.expander("📊 View Forecast Table"):
        st.dataframe(df_plot, use_container_width=True)

