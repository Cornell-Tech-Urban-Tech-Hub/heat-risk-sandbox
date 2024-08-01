import os
import requests
import geopandas as gpd
import numpy as np
import folium
import streamlit as st
from streamlit_folium import folium_static
import plotly.express as px
import pandas as pd

# Set up the Streamlit app
st.set_page_config(layout="wide")
st.title("Heat Risk and Health Index Dashboard")

# Sidebar for controls
st.sidebar.header("Controls")

# Day selection
day_options = ["Day 1", "Day 2", "Day 3", "Day 4", "Day 5", "Day 6", "Day 7"]
selected_day = st.sidebar.selectbox("Select Heat Risk Day", day_options)

# Load data
@st.cache_data
def load_data(selected_day):
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)

    # Construct the URL for the selected day
    url = f"https://heat-and-health-dashboard.s3.amazonaws.com/heat_risk_analysis_{selected_day.replace(' ', '+')}_20240723.geoparquet"
    
    local_file = os.path.join(data_dir, f"heat_risk_analysis_{selected_day}.geoparquet")

    if not os.path.exists(local_file):
        print(f"Downloading {url}...")
        response = requests.get(url)
        response.raise_for_status()
        with open(local_file, 'wb') as file:
            file.write(response.content)
        print(f"Saved to {local_file}")
    else:
        print(f"{local_file} already exists.")

    # Load the geoparquet file
    layer1_with_weighted_values = gpd.read_parquet(local_file)
    
    return layer1_with_weighted_values

layer1_with_weighted_values = load_data(selected_day)

# Load state and county data
@st.cache_data
def load_state_county_data():
    states_file = "data/us_states.parquet"
    counties_file = "data/us_counties.parquet"

    states = gpd.read_parquet(states_file)
    counties = gpd.read_parquet(counties_file)
    
    return states, counties

states, counties = load_state_county_data()

# Sort states and counties alphabetically
state_names = ["Select a State"] + sorted(states['NAME'].tolist())
selected_state = st.sidebar.selectbox("Select State", state_names)

# Filter counties based on selected state
if selected_state != "Select a State":
    filtered_counties = counties[counties['STATE_NAME'] == selected_state]
    county_names = ["Select a County"] + sorted(filtered_counties['NAME'].tolist())
else:
    filtered_counties = counties
    county_names = ["Select a County"]
selected_county = st.sidebar.selectbox("Select County", county_names)

# Get the list of available columns for HHI indicators
hhi_columns = [col for col in layer1_with_weighted_values.columns if col.startswith('weighted_')]
# Ensure "weighted_OVERALL_SCORE" is in the list and move it to the front
if "weighted_OVERALL_SCORE" in hhi_columns:
    hhi_columns = ["weighted_OVERALL_SCORE"] + [col for col in hhi_columns if col != "weighted_OVERALL_SCORE"]
else:
    st.warning("'weighted_OVERALL_SCORE' is not present in the dataset. Using the first available column as default.")

# CDC Heat and Health Index indicator selection
selected_hhi_indicator = st.sidebar.selectbox(
    "Select CDC Heat and Health Index Indicator", 
    hhi_columns,
    index=0  # This will select the first item in the list, which is now "weighted_OVERALL_SCORE" if it exists
)

# Filtering options
heat_threshold = st.sidebar.multiselect("Select Heat Risk Levels", [0, 1, 2, 3, 4], default=[2, 3, 4])
heat_health_index_threshold = st.sidebar.slider("Heat Health Index Percentile Threshold", 0, 100, 80)

# Update session state with current selections
selected_day = selected_day
selected_hhi_indicator = selected_hhi_indicator
heat_threshold = heat_threshold
heat_health_index_threshold = heat_health_index_threshold
selected_state = selected_state
selected_county = selected_county

# Data source information
st.sidebar.markdown("""
**Data Sources:**
- [NWS Heat Risk](https://www.wpc.ncep.noaa.gov/heatrisk/)
- [CDC Heat and Health Index](https://ephtracking.cdc.gov/Applications/heatTracker/)
""")

# Create the map with tooltips
def create_map(layer1_with_weighted_values, selected_hhi_indicator, heat_threshold, heat_health_index_threshold, selected_state, selected_county):
    # Calculate the percentile threshold
    percentile_threshold = np.percentile(layer1_with_weighted_values[selected_hhi_indicator], heat_health_index_threshold)

    # Create a new column to flag the records we want to highlight
    layer1_with_weighted_values['highlight'] = (
        (layer1_with_weighted_values[selected_hhi_indicator] >= percentile_threshold) & 
        (layer1_with_weighted_values['raster_value'].isin(heat_threshold))
    )

    # Ensure the GeoDataFrame is in a geographic CRS (WGS84)
    if not layer1_with_weighted_values.crs.is_geographic:
        layer1_with_weighted_values = layer1_with_weighted_values.to_crs(epsg=4326)

    # Filter state and county
    if selected_state != "Select a State":
        selected_state_geom = states[states['NAME'] == selected_state].geometry.values[0]
    else:
        selected_state_geom = None

    if selected_county != "Select a County" and selected_state != "Select a State":
        selected_county_geom = counties[(counties['STATE_NAME'] == selected_state) & (counties['NAME'] == selected_county)].geometry.values[0]
    else:
        selected_county_geom = None

    # Calculate the center of the map
    center_lat = layer1_with_weighted_values.geometry.centroid.y.mean()
    center_lon = layer1_with_weighted_values.geometry.centroid.x.mean()

    # Set initial view for the entire US
    initial_location = [center_lat, center_lon]
    initial_zoom = 4

    # Adjust view if a state or county is selected
    if selected_state_geom is not None:
        initial_location = [selected_state_geom.centroid.y, selected_state_geom.centroid.x]
        initial_zoom = 6
    if selected_county_geom is not None:
        initial_location = [selected_county_geom.centroid.y, selected_county_geom.centroid.x]
        initial_zoom = 8

    # Create a map
    m = folium.Map(location=initial_location, zoom_start=initial_zoom)

    # Add state boundary to the map
    if selected_state_geom is not None:
        folium.GeoJson(selected_state_geom, name="State Boundary", style_function=lambda x: {'color': 'green', 'weight': 2, 'fillOpacity': 0.1}).add_to(m)

    # Add county boundary to the map
    if selected_county_geom is not None:
        folium.GeoJson(selected_county_geom, name="County Boundary", style_function=lambda x: {'color': 'purple', 'weight': 2, 'fillOpacity': 0.1}).add_to(m)

    # Add all polygons to the map with tooltips
    folium.GeoJson(
        layer1_with_weighted_values,
        style_function=lambda feature: {
            'fillColor': 'red' if feature['properties']['highlight'] else 'blue',
            'color': 'black',
            'weight': 0.1,
            'fillOpacity': 0.7 if feature['properties']['highlight'] else 0.3,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=[selected_hhi_indicator, 'raster_value'],
            aliases=[selected_hhi_indicator.replace('weighted_', ''), 'Heat Risk Level:'],
            localize=True,
            sticky=False
        )
    ).add_to(m)

    # Add a legend
    legend_html = f'''
        <div style="position: fixed; bottom: 50px; left: 50px; width: 220px; height: 90px; 
                    border:2px solid grey; z-index:9999; font-size:14px;
                    background-color:white;
                    ">
        &nbsp; Legend <br>
        &nbsp; <i class="fa fa-square fa-1x"
                    style="color:red"></i> Highlighted Areas (Heat Risk {heat_threshold} & HHI {heat_health_index_threshold}th percentile)<br>
        &nbsp; <i class="fa fa-square fa-1x"
                    style="color:blue"></i> Other Areas
        </div>
        '''
    m.get_root().html.add_child(folium.Element(legend_html))

    return m

# Initialize filtered_data as an empty DataFrame
filtered_data = pd.DataFrame()

# Dashboard Main Panel
with st.container():
    m = create_map(layer1_with_weighted_values, selected_hhi_indicator, heat_threshold, heat_health_index_threshold, selected_state, selected_county)
    folium_static(m)

    # Display statistics
    st.write(f"Number of highlighted cells: {layer1_with_weighted_values['highlight'].sum()}")
    st.write(f"Total number of cells: {len(layer1_with_weighted_values)}")

# Display tables only if a state or county is selected
if selected_state != "Select a State" or selected_county != "Select a County":
    with st.container():
        st.subheader("Data Analysis")

        if selected_county != "Select a County" and selected_state != "Select a State":
            selected_county_geom = counties[(counties['STATE_NAME'] == selected_state) & (counties['NAME'] == selected_county)].geometry.values[0]
            filtered_data = layer1_with_weighted_values[layer1_with_weighted_values.intersects(selected_county_geom)]
            title_suffix = f" - {selected_state}, {selected_county}"
        elif selected_state != "Select a State":
            selected_state_geom = states[states['NAME'] == selected_state].geometry.values[0]
            filtered_data = layer1_with_weighted_values[layer1_with_weighted_values.intersects(selected_state_geom)]
            title_suffix = f" - {selected_state}"
        else:
            filtered_data = layer1_with_weighted_values
            title_suffix = ""

        st.subheader(f"Population Affected by Heat Risk Level{title_suffix}")
        population_by_risk_level = filtered_data.groupby('raster_value')['weighted_POP'].sum().reset_index()
        st.dataframe(population_by_risk_level)

        st.subheader(f"Percentage of Persons Aged 65 and Older by Heat Risk Level{title_suffix}")
        age65_by_risk_level = filtered_data.groupby('raster_value')['weighted_P_AGE65'].mean().reset_index()
        st.dataframe(age65_by_risk_level)

# Provide download option
st.header("Download Data")
st.download_button(label="Download Filtered Data as CSV", data=filtered_data.to_csv(), mime='text/csv')
