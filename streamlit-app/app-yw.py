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
def create_map(layer1_with_weighted_values, selected_hhi_indicator, heat_threshold, heat_health_index_threshold):
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

    # Calculate the center of the map
    center_lat = layer1_with_weighted_values.geometry.centroid.y.mean()
    center_lon = layer1_with_weighted_values.geometry.centroid.x.mean()

    # Create a map
    m = folium.Map(location=[center_lat, center_lon], zoom_start=4)

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
            fields=['raster_value', 'weighted_POP', 'weighted_NBE_SCORE', 'weighted_P_AGE65'],
            aliases=['Heat Risk Level:', 'Affected Population:', 'NBE Score:', 'Percentage of Persons 65+'],
            localize=True
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

# Dashboard Main Panel
with st.container():
    m = create_map(layer1_with_weighted_values, selected_hhi_indicator, heat_threshold, heat_health_index_threshold)
    folium_static(m)

    # Display statistics
    st.write(f"Number of highlighted cells: {layer1_with_weighted_values['highlight'].sum()}")
    st.write(f"Total number of cells: {len(layer1_with_weighted_values)}")

with st.container():
    st.subheader("Data Analysis")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Population Affected by Heat Risk Level")
        # Bar chart of population by heat risk level
        population_by_risk_level = layer1_with_weighted_values.groupby('raster_value')['weighted_POP'].sum().reset_index()
        fig_bar = px.bar(population_by_risk_level, x='raster_value', y='weighted_POP', title="Population Affected by Heat Risk Level",
                         labels={'raster_value': 'Heat Risk Level', 'weighted_POP': 'Population Affected'})
        st.plotly_chart(fig_bar)

        st.subheader("Percentage of Persons Aged 65 and Older by Heat Risk Level")
        # Bar chart of percentage of persons aged 65 and older by heat risk level
        age65_by_risk_level = layer1_with_weighted_values.groupby('raster_value')['weighted_P_AGE65'].mean().reset_index()
        fig_bar_age65 = px.bar(age65_by_risk_level, x='raster_value', y='weighted_P_AGE65', title="Percentage of Persons Aged 65 and Older by Heat Risk Level",
                               labels={'raster_value': 'Heat Risk Level', 'weighted_P_AGE65': 'Percentage of Persons Aged 65 and Older'})
        st.plotly_chart(fig_bar_age65)

    with col2:
        st.subheader("Box Plot of Selected HHI Indicator by Heat Risk Level")
        # Box plot of selected HHI indicator by heat risk level
        fig_box = px.box(layer1_with_weighted_values, x='raster_value', y=selected_hhi_indicator, title=f"Box Plot of {selected_hhi_indicator} by Heat Risk Level",
                         labels={'raster_value': 'Heat Risk Level', selected_hhi_indicator: 'HHI Indicator'})
        st.plotly_chart(fig_box)

        st.subheader("Box Plot of Natural and Built Environment Scores by Heat Risk Level")
        # Box plot of weighted_NBE_SCORE by heat risk level
        fig_box_nbe = px.box(layer1_with_weighted_values, x='raster_value', y='weighted_NBE_SCORE', title="Box Plot of Natural and Built Environment Scores by Heat Risk Level",
                             labels={'raster_value': 'Heat Risk Level', 'weighted_NBE_SCORE': 'Natural and Built Environment Scores'})
        st.plotly_chart(fig_box_nbe)



# Provide download option
st.header("Download Data")
st.download_button(label="Download Filtered Data as CSV", data=layer1_with_weighted_values.to_csv(), mime='text/csv')
