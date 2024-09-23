import os
import time
from functools import lru_cache
import requests
import geopandas as gpd
from datetime import datetime
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import folium
from io import BytesIO
import pytz
from shapely.geometry import Point, mapping
import pyarrow.parquet as pq
from shapely import wkb
import json
from shapely.errors import GEOSException
import boto3
import re

def scan_archive_dates():
    cloudfront_url = os.environ.get('CLOUDFRONT_URL', 'https://heat-risk-dashboard.s3.amazonaws.com')
    bucket_name = "heat-risk-dashboard"
    st.write(f"Scanning S3 bucket: {bucket_name} for available dates...")
    s3 = boto3.client('s3')

    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket_name)

    keys = []
    dates = set()
    for page in pages:
        for obj in page.get('Contents', []):
            key = obj['Key']
            keys.append(key)
            match = re.search(r'\d{8}', key)
            if match:
                date_str = match.group(0)
                date_obj = datetime.strptime(date_str, '%Y%m%d')
                dates.add(date_obj)
    dates = sorted(dates)

    return dates

@st.cache_data(ttl=300)  # Increased TTL to 5 min
def load_data(selected_day, selected_date):
    tz = pytz.timezone('America/New_York')
    formatted_day = selected_day.replace(' ', '+')
    # current_date = datetime.now(tz).strftime("%Y%m%d")
    current_date = datetime.strptime(selected_date, '%m/%d/%Y').strftime("%Y%m%d")
    
    cloudfront_url = os.environ.get('CLOUDFRONT_URL', 'https://heat-risk-dashboard.s3.amazonaws.com')
    url = f'{cloudfront_url}/heat_risk_analysis_{formatted_day}_{current_date}.geoparquet'
    # with st.sidebar:
    #     with st.expander("Data Source URL"):
    #         st.warning(f"Loaded {selected_day} forecast data for {selected_date} from {url}...")

    start_time = time.time()

    try:
        print(f"Downloading {url}...")
        with requests.get(url, stream=True) as response:
            response.raise_for_status()
            data = BytesIO(response.content)
        
        # Use pyarrow to read the Parquet file
        table = pq.read_table(data)
        df = table.to_pandas()

        # Convert the geometry column from WKB to shapely geometries
        df['geometry'] = df['geometry'].apply(lambda x: wkb.loads(x) if x else None)

        # Create GeoDataFrame and set the geometry column
        gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")
        
        # # Filter to include only New York state
        # gdf = gdf[gdf['mode_STATE'] == 'NY']

        end_time = time.time()
        download_time = end_time - start_time
        
        print(f"Download and processing completed in {download_time:.2f} seconds")
        # st.success(f"Data loaded successfully in {download_time:.2f} seconds")

        return gdf

    except requests.exceptions.RequestException as e:
        end_time = time.time()
        download_time = end_time - start_time

        st.error(f'{current_date},{url}')
        st.error(f"Failed to download data: {e}")
        print(f"Download failed after {download_time:.2f} seconds")
        return None
    
    except Exception as e:
        end_time = time.time()
        download_time = end_time - start_time

        st.error(f"An error occurred while loading the data: {e}")
        print(f"Data loading failed after {download_time:.2f} seconds")
        return None

@lru_cache(maxsize=None)
def load_state_county_zip_data():
    states_file = "data/us_states_reduced.parquet"
    counties_file = "data/us_counties_reduced.parquet"
    zipcodes_file = "data/us_zipcodes_reduced.parquet"

    states = gpd.read_parquet(states_file)
    counties = gpd.read_parquet(counties_file)
    zipcodes = gpd.read_parquet(zipcodes_file)

    for gdf in [states, counties, zipcodes]:
        if not gdf.crs.is_geographic:
            gdf.to_crs(epsg=4326, inplace=True)

    return states, counties, zipcodes

@lru_cache(maxsize=1000)
def get_zipcode_boundary(zip_code):
    _, _, zipcodes = load_state_county_zip_data()
    column_name = 'ZCTA5CE10'
    return zipcodes[zipcodes[column_name] == str(zip_code)]

def load_geographic_data():
    states, counties, _ = load_state_county_zip_data()

    # state_names = ["Select a State"] + sorted(states['NAME'].unique())
    selected_state = "New York"

    if selected_state != "Select a State":
        filtered_counties = counties[counties['STATE_NAME'] == selected_state]
        county_names = ["Select a County"] + sorted(filtered_counties['NAME'].unique())
    else:
        county_names = ["Select a County"]

    selected_county = st.sidebar.selectbox("Select County", county_names)

    zip_code = st.sidebar.text_input("Enter ZIP Code to Zoom In", placeholder="e.g., 10044")
    zipcode_boundary = get_zipcode_boundary(zip_code) if zip_code else None

    return states, counties, selected_state, selected_county, zipcode_boundary

def generate_column_mapping(columns, prefix='weighted_', replacement='weighted ', title_case=True):
    if title_case:
        return {col: col.replace(prefix, replacement).replace('_', ' ').title() for col in columns if col.startswith(prefix)}
    else:
        return {col: col.replace(prefix, replacement).replace('_', ' ') for col in columns if col.startswith(prefix)}

def move_column_to_front(columns, column_name):
    if column_name in columns:
        return [column_name] + [col for col in columns if col != column_name]
    return columns

@lru_cache(maxsize=None)
def load_hhi_description(file_path='data/HHI_Data_Dictionary_2024.csv'):
    return pd.read_csv(file_path)

def get_hhi_indicator_description(hhi_desc_df, indicator_name):
    try:
        return hhi_desc_df.loc[hhi_desc_df['weighted_2024_VARIABLE_NAME'] == indicator_name, '2024_DESCRIPTION'].values[0]
    except IndexError:
        return "No description available for this indicator."

def get_heat_risk_levels_description():
    return """
    **Heat Risk Levels:**
    
    - **0:** Little to no risk from expected heat.
    - **1:** Minor - This level of heat affects primarily those individuals extremely sensitive to heat, especially when outdoors without effective cooling and/or adequate hydration.
    - **2:** Moderate - This level of heat affects most individuals sensitive to heat, especially those without effective cooling and/or adequate hydration. Impacts possible in some health systems and in heat-sensitive industries.
    - **3:** Major - This level of heat affects anyone without effective cooling and/or adequate hydration. Impacts likely in some health systems, heat-sensitive industries, and infrastructure.
    - **4:** Extreme - This level of rare and/or long-duration extreme heat with little to no overnight relief affects anyone without effective cooling and/or adequate hydration. Impacts likely in most health systems, heat-sensitive industries, and infrastructure.
    """

@lru_cache(maxsize=None)
def project_single_geometry(geom, from_crs, to_crs):
    return gpd.GeoSeries([geom], crs=from_crs).to_crs(to_crs)[0]

def project_geometries(geometries, from_crs, to_crs):
    if isinstance(geometries, (list, tuple)):
        return [project_single_geometry(geom, from_crs, to_crs) for geom in geometries]
    else:
        return project_single_geometry(geometries, from_crs, to_crs)

def create_map(layer1_with_weighted_values, selected_hhi_indicator, heat_threshold, heat_health_index_threshold, selected_state, selected_county, states, counties, zipcode_boundary=None):
    if layer1_with_weighted_values.empty:
        st.warning("The data is empty. Please check your inputs.")
        return None

    # Filter out rows where raster_value is not in heat_threshold
    layer1_with_weighted_values = layer1_with_weighted_values[layer1_with_weighted_values['raster_value'].isin(heat_threshold)]

    if layer1_with_weighted_values.empty:
        st.warning("No data matches the selected heat threshold. Please adjust your inputs.")
        return None

    percentile_threshold = np.percentile(layer1_with_weighted_values[selected_hhi_indicator], heat_health_index_threshold)

    highlighted_areas = layer1_with_weighted_values.copy()
    highlighted_areas['highlight'] = highlighted_areas[selected_hhi_indicator] >= percentile_threshold

    # Project all geometries to EPSG:5070 once
    highlighted_areas_projected = highlighted_areas.to_crs(epsg=5070)
    states_projected = states.to_crs(epsg=5070)
    counties_projected = counties.to_crs(epsg=5070)

    # Simplify geometries with error handling
    tolerance = 1000  # Adjust this value to balance between speed and accuracy
    
    def safe_simplify(geometry):
        try:
            return geometry.simplify(tolerance)
        except GEOSException:
            return geometry

    highlighted_areas_projected['geometry'] = highlighted_areas_projected.geometry.apply(safe_simplify)
    states_projected['geometry'] = states_projected.geometry.apply(safe_simplify)
    counties_projected['geometry'] = counties_projected.geometry.apply(safe_simplify)

    # Set initial map center and zoom to continental US
    initial_location = [39.8283, -98.5795]  # Approximate center of the continental US
    initial_zoom = 4

    # Determine the bounds for zooming
    if zipcode_boundary is not None and not zipcode_boundary.empty:
        zoom_area = zipcode_boundary.to_crs(epsg=4326)
        initial_zoom = 13
    elif selected_county != "Select a County" and selected_state != "Select a State":
        zoom_area = counties[(counties['STATE_NAME'] == selected_state) & (counties['NAME'] == selected_county)].to_crs(epsg=4326)
        initial_zoom = 8
    elif selected_state != "Select a State":
        zoom_area = states[states['NAME'] == selected_state].to_crs(epsg=4326)
        initial_zoom = 6
    else:
        zoom_area = None

    # Create the map object
    m = folium.Map(location=initial_location, zoom_start=initial_zoom, tiles='Cartodb Positron')

    # Create a mapping of risk levels to color indices
    unique_risk_levels = sorted(highlighted_areas['raster_value'].unique())
    risk_to_color_index = {level: i for i, level in enumerate(unique_risk_levels)}

    # Adjust color map based on the number of unique heat risk levels in the filtered data
    color_map = px.colors.sequential.Reds[-len(unique_risk_levels):]  # Use the most intense colors from the Reds color scale

    def style_function(feature):
        risk_level = feature['properties']['raster_value']
        color_index = risk_to_color_index.get(risk_level, 0)  # Default to 0 if risk level is not found
        return {
            'fillColor': color_map[color_index],
            'color': 'black',
            'weight': 0.1,
            'fillOpacity': 0.7 if feature['properties']['highlight'] else 0.3,
        }

    # Add the GeoJson layer
    folium.GeoJson(
        highlighted_areas_projected.to_crs(epsg=4326).__geo_interface__,
        style_function=style_function,
        tooltip=folium.GeoJsonTooltip(
            fields=[selected_hhi_indicator, 'raster_value'],
            aliases=[selected_hhi_indicator.replace('weighted_', ''), 'Heat Risk Level:'],
            localize=True,
            sticky=True
        )
    ).add_to(m)

    # Fit bounds if a specific area is selected
    if zoom_area is not None and not zoom_area.empty:
        bounds = zoom_area.total_bounds
        m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])

    return m

def create_plot(data, y_column, x_column, color_column, title, y_label, x_label, height=300, width=600):
    fig = px.bar(data, 
                 y=y_column, 
                 x=x_column, 
                 color=color_column,
                 labels={y_column: y_label, x_column: x_label},
                 title=title,
                 orientation='h',
                 height=height,
                 width=width)
    fig.update_layout(barmode='stack')
    return fig
