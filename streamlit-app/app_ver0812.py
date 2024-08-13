import os
import requests
import zipfile
import geopandas as gpd
import numpy as np
import folium
import streamlit as st
from streamlit_folium import folium_static
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# Helper function to download files
def download_file(url, local_filename):
    if not os.path.exists(local_filename):
        print(f"Downloading {url}...")
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(local_filename, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        print(f"Saved to {local_filename}")
    else:
        print(f"{local_filename} already exists.")

# Set up the Streamlit app
st.title("Heat Risk and Health Index Dashboard")

# Sidebar for controls
st.sidebar.header("Controls")

# Day selection
day_options = ["Day 1", "Day 2", "Day 3", "Day 4", "Day 5", "Day 6", "Day 7"]
selected_day = st.sidebar.selectbox("Select Heat Risk Day", day_options)

# Clear cache when day selection changes
@st.cache_resource
def clear_cache():
    st.cache_data.clear()

# Load data
@st.cache_data
def load_data(selected_day):
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)

    # Construct the URL for the selected day
    url = f"https://heat-risk-dashboard.s3.amazonaws.com/heat_risk_analysis_{selected_day.replace(' ', '+')}_20240807.geoparquet"
    
    local_file = os.path.join(data_dir, f"heat_risk_analysis_{selected_day}.geoparquet")

    if not os.path.exists(local_file):
        st.info(f"Downloading data for {selected_day}...")
        response = requests.get(url)
        response.raise_for_status()
        with open(local_file, 'wb') as file:
            file.write(response.content)
        st.info(f"Saved to {local_file}")

    # Load the geoparquet file
    layer1_with_weighted_values = gpd.read_parquet(local_file)
    
    return layer1_with_weighted_values

# Clear cache and load new data when the day changes
clear_cache()
layer1_with_weighted_values = load_data(selected_day)

# Load US county data
@st.cache_data
def load_county_data():
    data_dir = "data"
    counties_dir = os.path.join(data_dir, "counties")
    os.makedirs(counties_dir, exist_ok=True)
    
    counties_url = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_county_20m.zip"
    counties_zip = os.path.join(counties_dir, "cb_2020_us_county_20m.zip")

    if not os.path.exists(counties_zip):
        download_file(counties_url, counties_zip)
        with zipfile.ZipFile(counties_zip, 'r') as zip_ref:
            zip_ref.extractall(counties_dir)

    counties_file = os.path.join(counties_dir, "cb_2020_us_county_20m.shp")
    counties_gdf = gpd.read_file(counties_file)

    # Ensure the GeoDataFrame is in WGS84 CRS
    if counties_gdf.crs != "EPSG:4326":
        counties_gdf = counties_gdf.to_crs(epsg=4326)
    
    return counties_gdf

counties_gdf = load_county_data()

# Load US ZIP code data from U.S. Census Bureau TIGER/Line Shapefiles
@st.cache_data
def load_zipcode_data():
    data_dir = "data"
    zipcodes_dir = os.path.join(data_dir, "zipcodes")
    os.makedirs(zipcodes_dir, exist_ok=True)
    
    zipcodes_url = "https://www2.census.gov/geo/tiger/TIGER2020/ZCTA5/tl_2020_us_zcta510.zip"
    zipcodes_zip = os.path.join(zipcodes_dir, "tl_2020_us_zcta510.zip")

    if not os.path.exists(zipcodes_zip):
        download_file(zipcodes_url, zipcodes_zip)
        with zipfile.ZipFile(zipcodes_zip, 'r') as zip_ref:
            zip_ref.extractall(zipcodes_dir)

    zipcodes_file = os.path.join(zipcodes_dir, "tl_2020_us_zcta510.shp")
    zipcodes_gdf = gpd.read_file(zipcodes_file)

    # Ensure the GeoDataFrame is in WGS84 CRS
    if zipcodes_gdf.crs != "EPSG:4326":
        zipcodes_gdf = zipcodes_gdf.to_crs(epsg=4326)
    
    return zipcodes_gdf

zipcodes_gdf = load_zipcode_data()

# State selection
states = np.append(["Select State"], sorted(counties_gdf["STATE_NAME"].unique()))
selected_state = st.sidebar.selectbox("Select State", states)

# County selection based on selected state
selected_county = None
if selected_state and selected_state != "Select State":
    counties_in_state = counties_gdf[counties_gdf["STATE_NAME"] == selected_state]
    counties = np.append(["Select County"], sorted(counties_in_state["NAME"].unique()))
    selected_county = st.sidebar.selectbox("Select County", counties)

# ZIP code input
zip_code = st.sidebar.text_input("Enter ZIP code to zoom in")

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

# Geocode ZIP code
geolocator = Nominatim(user_agent="heat-risk-dashboard", timeout=10)
location = None

def geocode_zip(zip_code):
    try:
        return geolocator.geocode({"postalcode": zip_code, "country": "US"})
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        st.sidebar.error(f"Geocoding error: {e}")
        return None

# Determine map center and get boundary
center_lat, center_lon = 37.0902, -95.7129  # Default center on the United States
zoom_level = 4
boundary_gdf = None
zipcode_boundary_gdf = None
filtered_data = layer1_with_weighted_values  # Default to the full dataset

if zip_code:
    location = geocode_zip(zip_code)
    if location:
        center_lat = location.latitude
        center_lon = location.longitude
        zoom_level = 12
        point = gpd.GeoDataFrame(geometry=[gpd.points_from_xy([center_lon], [center_lat])[0]], crs="EPSG:4326")
        county_row = counties_gdf[counties_gdf.contains(point.geometry[0])]
        zipcode_row = zipcodes_gdf[zipcodes_gdf.contains(point.geometry[0])]
        if not county_row.empty:
            boundary_gdf = county_row  # Set boundary to the county
        if not zipcode_row.empty:
            zipcode_boundary_gdf = zipcode_row  # Set boundary to the ZIP code

elif selected_state and selected_state != "Select State":
    state_row = counties_gdf[counties_gdf["STATE_NAME"] == selected_state]
    state_center = state_row.geometry.centroid
    center_lat = state_center.y.mean()
    center_lon = state_center.x.mean()
    zoom_level = 7
    boundary_gdf = state_row  # Set boundary to the state
    filtered_data = gpd.sjoin(layer1_with_weighted_values, state_row, how="left", predicate="within")  # Filter by state
    if selected_county and selected_county != "Select County":
        county_row = counties_gdf[(counties_gdf["STATE_NAME"] == selected_state) & (counties_gdf["NAME"] == selected_county)]
        if not county_row.empty:
            county_center = county_row.geometry.centroid
            center_lat = county_center.y.values[0]
            center_lon = county_center.x.values[0]
            zoom_level = 10
            boundary_gdf = county_row  # Set boundary to the county
            filtered_data = gpd.sjoin(layer1_with_weighted_values, county_row, how="left", predicate="within")  # Filter by county

# Create the map
def create_map(layer1_with_weighted_values, selected_hhi_indicator, heat_threshold, heat_health_index_threshold, center_lat, center_lon, zoom_level, boundary_gdf=None, zipcode_boundary_gdf=None):
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

    # Create a map
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_level)

    # Add all polygons to the map
    folium.GeoJson(
        layer1_with_weighted_values,
        style_function=lambda feature: {
            'fillColor': 'red' if feature['properties']['highlight'] else 'blue',
            'color': 'black',
            'weight': 0.1,
            'fillOpacity': 0.7 if feature['properties']['highlight'] else 0.3,
        }
    ).add_to(m)

    # Add county boundary if available
    if boundary_gdf is not None:
        folium.GeoJson(
            boundary_gdf,
            style_function=lambda feature: {
                'fillColor': 'none',
                'color': 'yellow',
                'weight': 3,
                'fillOpacity': 0
            }
        ).add_to(m)

    # Add ZIP code boundary if available
    if zipcode_boundary_gdf is not None:
        folium.GeoJson(
            zipcode_boundary_gdf,
            style_function=lambda feature: {
                'fillColor': 'none',
                'color': 'green',
                'weight': 2,
                'fillOpacity': 0
            }
        ).add_to(m)

    # Add a legend
    legend_html = f'''
        <div style="position: fixed; bottom: 50px; left: 50px; width: 220px; height: 110px; 
                    border:2px solid grey; z-index:9999; font-size:14px;
                    background-color:white;
                    ">
        &nbsp; Legend <br>
        &nbsp; <i class="fa fa-square fa-1x"
                    style="color:red"></i> NWS Heat Risk {heat_threshold} & CDC HHI {heat_health_index_threshold}th percentile<br>
        &nbsp; <i class="fa fa-square fa-1x"
                    style="color:blue"></i> Other cells<br>
        &nbsp; <i class="fa fa-square fa-1x"
                    style="color:yellow"></i> County boundary<br>
        &nbsp; <i class="fa fa-square fa-1x"
                    style="color:green"></i> ZIP code boundary
        </div>
        '''
    m.get_root().html.add_child(folium.Element(legend_html))

    return m

# Ensure the 'highlight' column is created
filtered_data = filtered_data.copy()
percentile_threshold = np.percentile(filtered_data[selected_hhi_indicator], heat_health_index_threshold)
filtered_data['highlight'] = (
    (filtered_data[selected_hhi_indicator] >= percentile_threshold) &
    (filtered_data['raster_value'].isin(heat_threshold))
)

# Filter data for highlighted cells and total cells within the selected area
filtered_data = filtered_data[filtered_data[selected_hhi_indicator].notnull()]  # Ensure data is not null
highlighted_cells = filtered_data[filtered_data['highlight']].shape[0]
total_cells = filtered_data.shape[0]

# Create and display the map
m = create_map(filtered_data, selected_hhi_indicator, heat_threshold, heat_health_index_threshold, center_lat, center_lon, zoom_level, boundary_gdf, zipcode_boundary_gdf)
folium_static(m)

# Display statistics
st.write(f"Number of highlighted cells in the selected area: {highlighted_cells}")
st.write(f"Total number of cells in the selected area: {total_cells}")

# Display county-level statistics if a county boundary is available
if boundary_gdf is not None:
    county_data = gpd.sjoin(filtered_data, boundary_gdf, how="inner", predicate="within")
    county_highlighted_cells = county_data[county_data['highlight']].shape[0]
    county_total_cells = county_data.shape[0]
    county_name = boundary_gdf.iloc[0]['NAME']

    st.write(f"County: {county_name}")
    st.write(f"Number of highlighted cells in {county_name} County: {county_highlighted_cells}")
    st.write(f"Total number of cells in {county_name} County: {county_total_cells}")
