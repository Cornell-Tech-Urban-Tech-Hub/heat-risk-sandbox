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
from datetime import datetime, timedelta

# Set up the Streamlit app
# st.set_page_config(layout="wide")
st.title("Heat Risk and Health Index Dashboard")

# Sidebar for controls
st.sidebar.header("Controls")

# Day selection
today = datetime.today()
date_options = [(today + timedelta(days=i)).strftime("%m/%d/%Y") for i in range(7)]
day_options = [f"Day {i+1} - {date_options[i]}" for i in range(7)]
selected_day_label = st.sidebar.selectbox("Select Heat Risk Day", day_options)
selected_day = selected_day_label.split(' - ')[0]

# Load data
@st.cache_data
def load_data(selected_day):
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)

    # Construct the URL for the selected day
    formatted_day = selected_day.replace(' ', '+')
    current_date = today.strftime("%Y%m%d")
    url = f'https://heat-risk-dashboard.s3.amazonaws.com/heat_risk_analysis_{formatted_day}_{current_date}.geoparquet'
    
    local_file = os.path.join(data_dir, f"heat_risk_analysis_{selected_day}.geoparquet")

    # if not os.path.exists(local_file):
    print(f"Downloading {url}...")
    response = requests.get(url)
    response.raise_for_status()
    with open(local_file, 'wb') as file:
        file.write(response.content)
    print(f"Saved to {local_file}")
    # else:
    print(f"{local_file} already exists.")

    # Load the geoparquet file
    layer1_with_weighted_values = gpd.read_parquet(local_file)

    # Drop the highlight column if it exists
    if 'highlight' in layer1_with_weighted_values.columns:
        layer1_with_weighted_values = layer1_with_weighted_values.drop(columns='highlight')

    return layer1_with_weighted_values

layer1_with_weighted_values = load_data(selected_day)

# Load state and county data
@st.cache_data
def load_state_county_data():
    states_file = "data/us_states.parquet"
    counties_file = "data/us_counties.parquet"

    states = gpd.read_parquet(states_file)
    counties = gpd.read_parquet(counties_file)

    if not states.crs.is_geographic:
        states = states.to_crs(epsg=4326)
    if not counties.crs.is_geographic:
        counties = counties.to_crs(epsg=4326)

    return states, counties

states, counties = load_state_county_data()
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
with st.sidebar.expander('Learn more about HHI Indicator'):
    st.markdown("""
    <div style="max-height: 200px; overflow-y: auto;">
    <table style="width:100%">
    <tr>
        <th>HHI Indicator</th>
        <th>Description</th>
    </tr>
    </table>
    </div>
    """, unsafe_allow_html=True)

# Filtering options
heat_threshold = st.sidebar.multiselect("Select Heat Risk Levels", [0, 1, 2, 3, 4], default=[2, 3, 4])

# Expander for learning more about heat risk levels
with st.sidebar.expander('Learn more about heat risk levels'):
    st.markdown("""
    <div style="max-height: 200px; overflow-y: auto;">
    <table style="width:100%">
    <tr>
        <th>Risk Level</th>
        <th>Description</th>
    </tr>
    <tr>
        <td>0</td>
        <td>Little to no risk from expected heat</td>
    </tr>
    <tr>
        <td>1</td>
        <td>Minor - This level of heat affects primarily those individuals extremely sensitive to heat, especially when outdoors without effective cooling and/or adequate hydration.</td>
    </tr>
    <tr>
        <td>2</td>
        <td>Moderate - This level of heat affects most individuals sensitive to heat, especially those without effective cooling and/or adequate hydration. Impacts possible in some health systems and in heat-sensitive industries.</td>
    </tr>
    <tr>
        <td>3</td>
        <td>Major - This level of heat affects anyone without effective cooling and/or adequate hydration. Impacts likely in some health systems, heat-sensitive industries and infrastructure.</td>
    </tr>
    <tr>
        <td>4</td>
        <td>Extreme - This level of rare and/or long-duration extreme heat with little to no overnight relief affects anyone without effective cooling and/or adequate hydration. Impacts likely in most health systems, heat-sensitive industries and infrastructure.</td>
    </tr>
    </table>
    </div>
    """, unsafe_allow_html=True)

heat_health_index_threshold = st.sidebar.slider("Heat Health Index Percentile Threshold", 0, 100, 80)


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
        folium.GeoJson(selected_county_geom, name="County Boundary", style_function=lambda x: {'color': 'yellow', 'weight': 2, 'fillOpacity': 0.7}).add_to(m)

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
            sticky=True
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

st.sidebar.write("Please click the button below to download the filtered data as a CSV file.")
st.sidebar.download_button(label="Download", data=filtered_data.to_csv(), mime='text/csv')

# Data source information
st.sidebar.markdown("""
**Data Sources:**
- [NWS Heat Risk](https://www.wpc.ncep.noaa.gov/heatrisk/)
- [CDC Heat and Health Index](https://ephtracking.cdc.gov/Applications/heatTracker/)
""")


# Main dashboard
m = create_map(layer1_with_weighted_values, selected_hhi_indicator, heat_threshold, heat_health_index_threshold, selected_state, selected_county)
folium_static(m)

# Add legend using st.markdown
st.markdown(f'''
<div style="position: relative; width: 400px; height: 150px; padding: 10px;">
    <b>Legend</b> <br>
    <span style="display: inline-block; width: 20px; height: 20px; background-color: red; margin-right: 10px;"></span> Highlighted Areas (Heat Risk {heat_threshold} & HHI {heat_health_index_threshold}th percentile)<br>
    <span style="display: inline-block; width: 20px; height: 20px; background-color: blue; margin-right: 10px;"></span> Other Areas
</div>
''', unsafe_allow_html=True)


st.write(f"Number of highlighted cells: {layer1_with_weighted_values['highlight'].sum()}. Total number of cells: {len(layer1_with_weighted_values)}")
# st.write(f"Total number of cells: {len(layer1_with_weighted_values)}")

# Calculate highlighted states and their counts
# highlighted_states_counts = layer1_with_weighted_values[layer1_with_weighted_values['highlight']]['mode_STATE_ABV'].value_counts()
# highlighted_states_df = highlighted_states_counts.reset_index()
# highlighted_states_df.columns = ["State", "Cells"]
# highlighted_states_df = highlighted_states_df.sort_values("Cells", ascending=False)
# # Display the DataFrame in a scrollable table
# st.write("Highlighted States and Cells:")
# st.dataframe(highlighted_states_df, height=200)

# Create lower columns with specified proportions
# col1_lower, col2_lower = st.columns([0.65, 0.35], gap='small')


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

    st.subheader(f"Key Summary {title_suffix}")
    st.markdown(f"**Sociodemographic**")
    st.markdown(f"Affected population: {filtered_data['weighted_POP'].sum()}")

    # with st.expander("See detailed plot for affected population"):
    #     population_by_risk_level = filtered_data.groupby('raster_value')['weighted_POP'].sum().reset_index()
    #     # population_by_risk_level['raster_value'] = population_by_risk_level['raster_value'].astype(str)
    #     fig_population = px.bar(population_by_risk_level, x='raster_value', y='weighted_POP', 
    #         labels={'raster_value': 'Heat Risk Level', 'weighted_POP': 'Affected Population'},
    #         title="Population Affected by Heat Risk Level")
    #     st.plotly_chart(fig_population)

    with st.expander("See detailed plot for affected population"):
        # Prepare the data for stacked bar chart
        population_by_risk_level = filtered_data.groupby('raster_value')['weighted_POP'].sum().reset_index()
        population_by_risk_level['raster_value'] = population_by_risk_level['raster_value'].astype(str)

        # Create the horizontal stacked bar chart
        fig_population = px.bar(population_by_risk_level, 
                                y='raster_value', 
                                x='weighted_POP', 
                                color='raster_value',
                                labels={'raster_value': 'Heat Risk Level', 'weighted_POP': 'Affected Population'},
                                title="Population Affected by Heat Risk Level",
                                orientation='h',
                                height=300,
                                width=600)
        fig_population.update_layout(barmode='stack')
        st.plotly_chart(fig_population)


    st.markdown(f"Percentage of persons aged 65 and older estimate: {filtered_data['weighted_P_AGE65'].mean():.2f}%")

    with st.expander('See detailed plot for affected population'):
        age65_by_risk_level = filtered_data.groupby('raster_value')['weighted_P_AGE65'].mean().reset_index()
        age65_by_risk_level['raster_value'] = age65_by_risk_level['raster_value'].astype(str)
        fig_age65 = px.bar(age65_by_risk_level,
                           y='raster_value',
                           x='weighted_P_AGE65',
                           color='raster_value',
                           labels={'raster_value': 'Heat Risk Level', 'weighted_P_AGE65': 'Percentage of Persons Aged 65 and Older'},
                           title="Percentage of Persons Aged 65 and Older by Heat Risk Level",
                           orientation='h',
                           height=300,
                           width=600)
        fig_age65.update_layout(barmode='stack')
        st.plotly_chart(fig_age65)

    st.markdown(f"**Historical Heat and Health Burden**")
    # st.markdown(f"Percentile rank of heat-related EMS activation reported to NEMSIS: {filtered_data['weighted_PR_HRI'].mean():.2f}")
    st.markdown(f"Number of extreme heat days: {filtered_data['weighted_P_NEHD'].mean():.2f}")
    st.markdown(f"**Sensitivity Information**")
    st.markdown(f"Crude prevalence of persons (age 18+) with Coronary Heart Disease (CHD): {filtered_data['weighted_P_CHD'].mean():.2f}")
    st.markdown(f"Crude prevalence of persons (age 18+) with Obesity: {filtered_data['weighted_P_OBS'].mean():.2f}")
    st.markdown(f"**Natural and Built Environment**")
    st.markdown(f"Annual mean days above PM2.5 regulatory standard - 3-year average: {filtered_data['weighted_P_NEHD'].mean():.2f}")
else:
    st.subheader('Select a State or County to get key summaries')
