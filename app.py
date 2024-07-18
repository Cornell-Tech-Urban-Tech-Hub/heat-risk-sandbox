import streamlit as st
import folium
from streamlit_folium import folium_static
import geopandas as gpd
import pandas as pd
import os
import requests
import zipfile
import rasterio
from rasterio.features import shapes, rasterize
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling
import branca.colormap as cm
import numpy as np

data_dir = "data"

st.set_page_config(layout="wide")

# Setup and helper functions
if not os.path.exists(data_dir):
    os.makedirs(data_dir, exist_ok=True)

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

def vector_to_raster(gdf, value_column, resolution):
    bounds = gdf.total_bounds
    width = int((bounds[2] - bounds[0]) / resolution)
    height = int((bounds[3] - bounds[1]) / resolution)
    transform = from_bounds(*bounds, width, height)
    
    shapes = ((geom, value) for geom, value in zip(gdf.geometry, gdf[value_column]))
    raster = rasterize(shapes=shapes, out_shape=(height, width), transform=transform)
    return raster, transform

def map_algebra(raster1, raster2, operation='multiply'):
    if operation == 'multiply':
        return raster1 * raster2
    elif operation == 'add':
        return raster1 + raster2
    # Add more operations as needed

# Load data functions (keep existing load functions)

@st.cache_data
def load_heat_risk_data():
    geodataframes = {}
    for day, url in url_list.items():
        file_path = os.path.join(data_dir, f"{day}.tif")
        if not os.path.exists(file_path):
            response = requests.get(url)
            with open(file_path, 'wb') as f:
                f.write(response.content)
        gdf = geotiff_to_geodataframe(file_path)
        geodataframes[day] = gdf
    return geodataframes

@st.cache_data
def load_cdc_data():
    excel_url = "https://gis.cdc.gov/HHI/Documents/HHI_Data.zip"
    excel_zip = f"{data_dir}/HHI_Data.zip"
    if not os.path.exists(excel_zip):
        download_file(excel_url, excel_zip)
        with zipfile.ZipFile(excel_zip, 'r') as zip_ref:
            zip_ref.extractall(data_dir)
    excel_file = f"{data_dir}/HHI Data 2024 United States.xlsx"
    return pd.read_excel(excel_file)

@st.cache_data
def load_zcta_boundaries():
    boundaries_url = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip"
    boundaries_zip = f"{data_dir}/cb_2020_us_zcta520_500k.zip"
    if not os.path.exists(boundaries_zip):
        download_file(boundaries_url, boundaries_zip)
        with zipfile.ZipFile(boundaries_zip, 'r') as zip_ref:
            zip_ref.extractall(data_dir)
    boundaries_file = f"{data_dir}/cb_2020_us_zcta520_500k.shp"
    return gpd.read_file(boundaries_file).to_crs(epsg=4326)

@st.cache_data
def prepare_layer2():
    hhi_data = load_cdc_data()
    boundaries = load_zcta_boundaries()
    hhi_data['ZCTA'] = hhi_data['ZCTA'].astype(str)
    boundaries['ZCTA5CE20'] = boundaries['ZCTA5CE20'].astype(str)
    return boundaries.merge(hhi_data, left_on='ZCTA5CE20', right_on='ZCTA', how='inner')

# New function to create the combined layer
@st.cache_data
def create_combined_layer(layer1_path, _layer2, selected_day):
    # Read layer1 raster
    with rasterio.open(layer1_path) as src:
        layer1_raster = src.read(1)
        layer1_transform = src.transform
        layer1_crs = src.crs

    # Rasterize layer2
    layer2_raster, layer2_transform = vector_to_raster(layer2, 'OVERALL_SCORE', resolution=src.res[0])

    # Reproject and resample layer2 to match layer1
    layer2_resampled = np.zeros_like(layer1_raster)
    reproject(
        layer2_raster,
        layer2_resampled,
        src_transform=layer2_transform,
        src_crs=layer2.crs,
        dst_transform=layer1_transform,
        dst_crs=layer1_crs,
        resampling=Resampling.bilinear
    )

    # Perform map algebra
    combined_raster = map_algebra(layer1_raster, layer2_resampled, operation='multiply')

    # Create a new GeoDataFrame from the combined raster
    combined_gdf = geotiff_to_geodataframe(combined_raster)
    
    return combined_gdf

# Load data
url_list = {
    "Day 1": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_1_Mercator.tif",
    "Day 2": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_2_Mercator.tif",
    "Day 3": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_3_Mercator.tif",
    "Day 4": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_4_Mercator.tif",
    "Day 5": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_5_Mercator.tif",
    "Day 6": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_6_Mercator.tif",
    "Day 7": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_7_Mercator.tif"
}

geodataframes = load_heat_risk_data()
layer2 = prepare_layer2()

# Streamlit app

st.title("Heat Risk and Health Index Map")

# Create a base map
m = folium.Map(location=[39.8283, -98.5795], zoom_start=4)

# Create checkboxes for layer visibility
st.sidebar.header("Layer Visibility")
show_heat_risk = st.sidebar.checkbox("Show NWS Heat Risk", value=True)
show_health_index = st.sidebar.checkbox("Show CDC Health Index", value=True)
show_combined = st.sidebar.checkbox("Show Combined Analysis", value=False)

# LAYER 1: NWS Heat Risk data
selected_day = st.selectbox("Select day for Heat Risk data:", list(geodataframes.keys()))
layer1 = geodataframes[selected_day]

# Create a color map for Layer 1
min_value = layer1['raster_value'].min()
max_value = layer1['raster_value'].max()
colormap1 = cm.LinearColormap(colors=['green', 'yellow', 'orange', 'red'], 
                             vmin=min_value, vmax=max_value)

def style_function(feature):
    value = feature['properties']['raster_value']
    return {
        'fillColor': colormap1(value),
        'color': 'black',
        'weight': 0,
        'fillOpacity': 0.7
    }

if show_heat_risk:
    heat_risk_layer = folium.GeoJson(
        layer1,
        name="NWS Heat Risk",
        style_function=style_function,
        tooltip=folium.GeoJsonTooltip(fields=['raster_value'],
                                      aliases=['Heat Risk Value'],
                                      style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;"))
    ).add_to(m)

    colormap1.add_to(m)
    colormap1.caption = 'Heat Risk Value'

# LAYER 2: CDC Health Index data
if show_health_index:
    health_index_layer = folium.Choropleth(
        geo_data=layer2,
        name="CDC Health Index",
        data=layer2,
        columns=['ZCTA', 'OVERALL_SCORE'],
        key_on='feature.properties.ZCTA',
        fill_color='YlOrRd',
        fill_opacity=0.7,
        line_opacity=0,
        legend_name="Overall Health Index Score"
    ).add_to(m)

# LAYER 3: Combined Analysis
if show_combined:
    layer1_path = os.path.join(data_dir, f"{selected_day}.tif")
    combined_gdf = create_combined_layer(layer1_path, layer2, selected_day)
    
    # Create a color map for the combined layer
    combined_min = combined_gdf['raster_value'].min()
    combined_max = combined_gdf['raster_value'].max()
    combined_colormap = cm.LinearColormap(colors=['purple', 'blue', 'green', 'yellow', 'orange', 'red'], 
                                          vmin=combined_min, vmax=combined_max)

    folium.GeoJson(
        combined_gdf,
        name="Combined Analysis",
        style_function=lambda feature: {
            'fillColor': combined_colormap(feature['properties']['raster_value']),
            'color': 'black',
            'weight': 0,
            'fillOpacity': 0.7
        },
        tooltip=folium.GeoJsonTooltip(fields=['raster_value'],
                                      aliases=['Combined Value'],
                                      style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;"))
    ).add_to(m)
    
    combined_colormap.add_to(m)
    combined_colormap.caption = 'Combined Analysis Value'

# Add layer control
folium.LayerControl().add_to(m)

# Display the map
folium_static(m)

# Additional information
st.write(f"Displaying Heat Risk data for {selected_day}")
if show_heat_risk:
    st.write("Layer 1: NWS Heat Risk data (color-coded by risk level)")
if show_health_index:
    st.write("Layer 2: CDC Health Index data (Overall Score)")
if show_combined:
    st.write("Layer 3: Combined Analysis (Heat Risk * Overall Health Index Score)")