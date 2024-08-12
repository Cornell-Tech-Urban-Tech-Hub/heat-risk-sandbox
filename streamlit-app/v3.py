import os
import requests
import geopandas as gpd
import numpy as np
import folium
import streamlit as st
from streamlit_folium import folium_static
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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
    formatted_day = selected_day.replace(' ', '+')
    url = f'https://heat-risk-dashboard.s3.amazonaws.com/heat_risk_analysis_{formatted_day}_20240801.geoparquet'
    # url = 'https://heat-risk-dashboard.s3.amazonaws.com/heat_risk_analysis_Day+1_20240801.geoparquet'
    # old url format: 
    # url = 'https://heat-and-health-dashboard.s3.amazonaws.com/heat_risk_analysis_{selected_day.replace(' ', '+')}_20240723.geoparquet'
    
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

# Function to count affected counties
def count_affected_counties_by_level(layer1_with_weighted_values, counties, heat_threshold):
    county_counts_by_level = {level: 0 for level in heat_threshold}
    
    for level in heat_threshold:
        affected_counties = layer1_with_weighted_values[layer1_with_weighted_values['raster_value'] == level]
        affected_county_geoms = affected_counties.geometry

        county_counts = []
        for county_geom in counties.geometry:
            affected_cells = affected_county_geoms.intersects(county_geom).sum()
            if affected_cells > 0:
                county_counts.append(1)
            else:
                county_counts.append(0)

        counties[f'Heat_Risk_Level_{level}'] = county_counts
        county_counts_by_level[level] = sum(counties[f'Heat_Risk_Level_{level}'])
    
    return county_counts_by_level

# Initialize filtered_data as an empty DataFrame
filtered_data = pd.DataFrame()

# Create top columns with specified proportions
col1, col2 = st.columns([0.8, 0.2], gap='small')

with col1:
    m = create_map(layer1_with_weighted_values, selected_hhi_indicator, heat_threshold, heat_health_index_threshold, selected_state, selected_county)
    folium_static(m)

with col2:
    st.write(f"Number of highlighted cells: {layer1_with_weighted_values['highlight'].sum()}")
    st.write(f"Total number of cells: {len(layer1_with_weighted_values)}")

    # Count the affected counties by heat risk level
    affected_counties_summary = count_affected_counties_by_level(layer1_with_weighted_values, counties, heat_threshold)
    st.write("Summary of Affected Counties by Heat Risk Levels")
    for level, count in affected_counties_summary.items():
        st.write(f"Heat Risk Level {level}: {count} counties affected")

    st.write("Download Data")
    st.download_button(label="Download Filtered Data as CSV", data=filtered_data.to_csv(), mime='text/csv')

# Create lower columns with specified proportions
col1_lower, col2_lower = st.columns([0.65, 0.35], gap='small')

with col1_lower:
    # Display text-based data analysis
    if selected_state != "Select a State" or selected_county != "Select a County":
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

        # Display the text information
        st.subheader(f"Key Summary {title_suffix}")
        st.markdown(f"**Sociodemographic**")
        st.markdown(f"Affected population: {filtered_data['weighted_POP'].sum()}")
        st.markdown(f"Percentage of persons aged 65 and older estimate: {filtered_data['weighted_P_AGE65'].mean():.2f}%")   
        st.markdown(f"**Historical Heat and Health Burden**")
        st.markdown(f"Percentile rank of heat-related EMS activation reported to NEMSIS: {filtered_data['weighted_PR_HRI'].mean():.2f}")
        st.markdown(f"Number of extreme heat days: {filtered_data['weighted_P_NEHD'].mean():.2f}")
        st.markdown(f"**Sensitivity Information**")
        st.markdown(f"Crude prevalence of persons (age 18+) with Coronary Heart Disease (CHD): {filtered_data['weighted_P_CHD'].mean():.2f}")
        st.markdown(f"Crude prevalence of persons (age 18+) with Obesity: {filtered_data['weighted_P_OBS'].mean():.2f}")
        st.markdown(f"**Natural and Built Environment**")
        st.markdown(f"Annual mean days above PM2.5 regulatory standard - 3-year average: {filtered_data['weighted_P_NEHD'].mean():.2f}")

# with col2_lower:
#     if not filtered_data.empty:
#         # st.subheader("Population Affected by Heat Risk Level")
#         population_by_risk_level = filtered_data.groupby('raster_value')['weighted_POP'].sum().reset_index()
#         fig = px.bar(population_by_risk_level, x='raster_value', y='weighted_POP', 
#              labels={'raster_value': 'Heat Risk Level', 'weighted_POP': 'Affected Population'},
#              title="Population Affected by Heat Risk Level")
#         st.plotly_chart(fig)

with col2_lower:
    if not filtered_data.empty:
        # Population Affected by Heat Risk Level plot
        population_by_risk_level = filtered_data.groupby('raster_value')['weighted_POP'].sum().reset_index()
        fig_population = px.bar(population_by_risk_level, x='raster_value', y='weighted_POP', 
             labels={'raster_value': 'Heat Risk Level', 'weighted_POP': 'Affected Population'},
             title="Population Affected by Heat Risk Level")
        st.plotly_chart(fig_population)
        
        # Percentage of Persons Aged 65 and Older by Heat Risk Level plot
        age65_by_risk_level = filtered_data.groupby('raster_value')['weighted_P_AGE65'].mean().reset_index()
        fig_age65 = px.bar(age65_by_risk_level, x='raster_value', y='weighted_P_AGE65', 
             labels={'raster_value': 'Heat Risk Level', 'weighted_P_AGE65': 'Percentage of Persons Aged 65 and Older'},
             title="Percentage of Persons Aged 65 and Older by Heat Risk Level")
        st.plotly_chart(fig_age65)

