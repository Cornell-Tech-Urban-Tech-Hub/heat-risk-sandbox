# Generated by Claude
# https://claude.ai/chat/d73f2283-4094-4775-b4fb-e892e302a848

import os
import requests
import zipfile
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.features import shapes
from pyproj import CRS
import folium
import matplotlib.pyplot as plt
import streamlit as st
from streamlit_folium import folium_static

# Helper functions
def download_file(url, local_filename):
    if not os.path.exists(local_filename):
        print(f"Downloading {url}...")
        response = requests.get(url)
        response.raise_for_status()
        with open(local_filename, 'wb') as file:
            file.write(response.content)
        print(f"Saved to {local_filename}")
    else:
        print(f"{local_filename} already exists.")

def geotiff_to_geodataframe(file_path):
    with rasterio.open(file_path) as src:
        image = src.read(1)
        mask = image != src.nodata
        results = (
            {'properties': {'raster_value': v}, 'geometry': s}
            for i, (s, v) 
            in enumerate(shapes(image, mask=mask, transform=src.transform))
        )
        geoms = list(results)
    
    gdf = gpd.GeoDataFrame.from_features(geoms, crs=src.crs)
    return gdf.to_crs(epsg=4326)

def convert_excel_to_parquet(excel_file_path, parquet_file_path):
    if not os.path.exists(parquet_file_path):
        df = pd.read_excel(excel_file_path)
        df.to_parquet(parquet_file_path, index=False)
        print(f"Converted {excel_file_path} to {parquet_file_path}")
    else:
        print(f"Parquet file {parquet_file_path} already exists.")

# Set up the Streamlit app
st.title("Heat Risk and Health Index Dashboard")

# Sidebar for controls
st.sidebar.header("Controls")

# Day selection
day_options = ["Day 1", "Day 2", "Day 3", "Day 4", "Day 5", "Day 6", "Day 7"]
selected_day = st.sidebar.selectbox("Select Heat Risk Day", day_options)

# Load data
@st.cache_data
def load_data():
    data_dir = "data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)

    # Load NWS Heat Risk data
    url_list = {
        "Day 1": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_1_Mercator.tif",
        "Day 2": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_2_Mercator.tif",
        "Day 3": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_3_Mercator.tif",
        "Day 4": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_4_Mercator.tif",
        "Day 5": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_5_Mercator.tif",
        "Day 6": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_6_Mercator.tif",
        "Day 7": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_7_Mercator.tif"
    }
    
    geodataframes = {}
    for day, url in url_list.items():
        file_path = os.path.join(data_dir, f"{day}.tif")
        if not os.path.exists(file_path):
            response = requests.get(url)
            with open(file_path, 'wb') as f:
                f.write(response.content)
                print(f"Downloaded {file_path}")
        gdf = geotiff_to_geodataframe(file_path)
        geodataframes[day] = gdf
    
    # Load CDC Heat and Health Index Data
    boundaries_url = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip"
    boundaries_zip = os.path.join(data_dir, "cb_2020_us_zcta520_500k.zip")
    if not os.path.exists(boundaries_zip):
        download_file(boundaries_url, boundaries_zip)
        with zipfile.ZipFile(boundaries_zip, 'r') as zip_ref:
            zip_ref.extractall(data_dir)
    boundaries_file = os.path.join(data_dir, "cb_2020_us_zcta520_500k.shp")
    zcta_boundaries = gpd.read_file(boundaries_file).to_crs(epsg=4326)
    
    excel_url = "https://gis.cdc.gov/HHI/Documents/HHI_Data.zip"
    excel_zip = os.path.join(data_dir, "HHI_Data.zip")
    excel_file = os.path.join(data_dir, "HHI Data 2024 United States.xlsx")
    parquet_file = os.path.join(data_dir, "HHI Data 2024 United States.parquet")
    
    if not os.path.exists(parquet_file):
        download_file(excel_url, excel_zip)
        with zipfile.ZipFile(excel_zip, 'r') as zip_ref:
            zip_ref.extractall(data_dir)
        convert_excel_to_parquet(excel_file, parquet_file)
    hhi_data = pd.read_parquet(parquet_file)
    
    hhi_data['ZCTA'] = hhi_data['ZCTA'].astype(str)
    zcta_boundaries['ZCTA5CE20'] = zcta_boundaries['ZCTA5CE20'].astype(str)
    zcta_with_hhi = zcta_boundaries.merge(hhi_data, left_on='ZCTA5CE20', right_on='ZCTA', how='inner')
    
    return geodataframes, zcta_with_hhi

geodataframes, zcta_with_hhi = load_data()

# CDC Heat and Health Index indicator selection
hhi_columns = zcta_with_hhi.select_dtypes(include=[np.number]).columns.drop('geometry', errors='ignore')
selected_hhi_indicator = st.sidebar.selectbox("Select CDC Heat and Health Index Indicator", hhi_columns)

# Filtering options
heat_threshold = st.sidebar.multiselect("Select Heat Risk Levels", [0, 1, 2, 3, 4], default=[2, 3, 4])
heat_health_index_threshold = st.sidebar.slider("Heat Health Index Percentile Threshold", 0, 100, 80)

# Create the combined map
def create_combined_map(layer1, layer2, selected_hhi_indicator, heat_threshold, heat_health_index_threshold):
    # Ensure both layers are in the same CRS
    if layer1.crs != layer2.crs:
        layer2 = layer2.to_crs(layer1.crs)

    # If the CRS is geographic, reproject to a suitable projected CRS
    if layer1.crs.is_geographic:
        utm_crs = CRS.from_epsg(5070)
        layer1 = layer1.to_crs(utm_crs)
        layer2 = layer2.to_crs(utm_crs)

    # Spatial join
    joined = gpd.overlay(layer1, layer2, how='intersection')

    # Calculate intersection area and weight
    joined['intersection_area'] = joined.geometry.area
    joined['weight'] = joined['intersection_area'] / joined.groupby(level=0)['intersection_area'].transform('sum')

    # Identify numeric columns
    numeric_columns = layer2.select_dtypes(include=[np.number]).columns.drop('geometry', errors='ignore')
    non_numeric_columns = layer2.columns.drop(numeric_columns).drop('geometry', errors='ignore')

    # Apply weight to numeric columns from layer2
    for col in numeric_columns:
        joined[f'weighted_{col}'] = joined[col] * joined['weight']

    # Handle non-numeric columns
    for col in non_numeric_columns:
        joined[f'mode_{col}'] = joined.groupby(level=0).apply(
            lambda x: pd.Series({
                col: x.loc[x['intersection_area'].idxmax(), col]
            })
        )

    # Group by original grid cells
    numeric_result = joined.groupby(level=0).agg({f'weighted_{col}': 'sum' for col in numeric_columns})
    non_numeric_result = joined.groupby(level=0).agg({f'mode_{col}': 'first' for col in non_numeric_columns})

    # Combine results
    result = pd.concat([numeric_result, non_numeric_result], axis=1)

    # Merge the result back to the original layer1
    layer1_with_weighted_values = layer1.join(result)

    # Calculate the percentile threshold
    percentile_threshold = np.percentile(layer1_with_weighted_values[f'weighted_{selected_hhi_indicator}'], heat_health_index_threshold)

    # Create a new column to flag the records we want to highlight
    layer1_with_weighted_values['highlight'] = (
        (layer1_with_weighted_values[f'weighted_{selected_hhi_indicator}'] >= percentile_threshold) & 
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

    # Add a legend
    legend_html = f'''
        <div style="position: fixed; bottom: 50px; left: 50px; width: 220px; height: 90px; 
                    border:2px solid grey; z-index:9999; font-size:14px;
                    background-color:white;
                    ">
          &nbsp; Legend <br>
          &nbsp; <i class="fa fa-square fa-1x"
                     style="color:red"></i> {heat_health_index_threshold}th percentile & raster {heat_threshold} <br>
          &nbsp; <i class="fa fa-square fa-1x"
                     style="color:blue"></i> Other cells
        </div>
        '''
    m.get_root().html.add_child(folium.Element(legend_html))

    return m, layer1_with_weighted_values

# Create and display the map
m, layer1_with_weighted_values = create_combined_map(geodataframes[selected_day], zcta_with_hhi, selected_hhi_indicator, heat_threshold, heat_health_index_threshold)
folium_static(m)

# Display statistics
st.write(f"Number of highlighted cells: {layer1_with_weighted_values['highlight'].sum()}")
st.write(f"Total number of cells: {len(layer1_with_weighted_values)}")