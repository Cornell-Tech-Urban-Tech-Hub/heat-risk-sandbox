
import streamlit as st
import folium
from streamlit_folium import folium_static
import geopandas as gpd
import pandas as pd
import os
import requests
import zipfile
import rasterio
from rasterio.features import shapes
import numpy as np
import branca.colormap as cm
data_dir = "data"

#setup and helper functions
if not os.path.exists(data_dir):
    os.makedirs(data_dir, exist_ok=True)

def download_file(url, local_filename):
    if not os.path.exists(local_filename):
        print(f"Downloading {url}...")
        response = requests.get(url)
        response.raise_for_status()  # Check if the request was successful
        with open(local_filename, 'wb') as file:
            file.write(response.content)
        print(f"Saved to {local_filename}")
    else:
        print(f"{local_filename} already exists.")

# Modified geotiff_to_geodataframe function
def geotiff_to_geodataframe(file_path):
    with rasterio.open(file_path) as src:
        image = src.read(1)  # Read the first band
        mask = image != src.nodata
        results = (
            {'properties': {'raster_value': v}, 'geometry': s}
            for i, (s, v) 
            in enumerate(shapes(image, mask=mask, transform=src.transform))
        )
        geoms = list(results)
    
    gdf = gpd.GeoDataFrame.from_features(geoms, crs=src.crs)
    return gdf.to_crs(epsg=4326)  # Convert to WGS84

# Set up data directory

if not os.path.exists(data_dir):
    os.makedirs(data_dir, exist_ok=True)

# Download and process NWS Heat Risk data (Layer 1)
url_list = {
    "Day 1": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_1_Mercator.tif",
    "Day 2": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_2_Mercator.tif",
    "Day 3": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_3_Mercator.tif",
    "Day 4": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_4_Mercator.tif",
    "Day 5": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_5_Mercator.tif",
    "Day 6": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_6_Mercator.tif",
    "Day 7": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_7_Mercator.tif"
}


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

# Load Layer 1 data
geodataframes = load_heat_risk_data()

# Download and process Layer 2 (CDC data)
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

hhi_data = load_cdc_data()

# Download and process ZCTA boundaries
@st.cache_data
def load_zcta_boundaries():
    boundaries_url = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip"
    boundaries_zip = f"{data_dir}/cb_2020_us_zcta520_500k.zip"
    if not os.path.exists(boundaries_zip):
        download_file(boundaries_url, boundaries_zip)
        with zipfile.ZipFile(boundaries_zip, 'r') as zip_ref:
            zip_ref.extractall(data_dir)
    boundaries_file = f"{data_dir}/cb_2020_us_zcta520_500k.shp"
    return gpd.read_file(boundaries_file).to_crs(epsg=4326)  # Convert to WGS84

boundaries = load_zcta_boundaries()

# Prepare Layer 2
@st.cache_data
def prepare_layer2():
    hhi_data['ZCTA'] = hhi_data['ZCTA'].astype(str)
    boundaries['ZCTA5CE20'] = boundaries['ZCTA5CE20'].astype(str)
    return boundaries.merge(hhi_data, left_on='ZCTA5CE20', right_on='ZCTA', how='inner')

layer2 = prepare_layer2()

# Streamlit app
st.title("Heat Risk and Health Index Map")

# Create a base map
m = folium.Map(location=[39.8283, -98.5795], zoom_start=4)


# User-selectable dialog for Layer 1
selected_day = st.selectbox("Select day for Heat Risk data:", list(geodataframes.keys()))

# Add Layer 1 (NWS Heat Risk data)
layer1 = geodataframes[selected_day]

# Create a base map
m = folium.Map(location=[39.8283, -98.5795], zoom_start=4)

# Prepare Layer 1 (NWS Heat Risk data)
layer1 = geodataframes[selected_day]

# Create a color map
min_value = layer1['raster_value'].min()
max_value = layer1['raster_value'].max()
colormap = cm.LinearColormap(colors=['green', 'yellow', 'orange', 'red'], 
                             vmin=min_value, vmax=max_value)

# Function to assign color based on value
def style_function(feature):
    value = feature['properties']['raster_value']
    return {
        'fillColor': colormap(value),
        'color': 'black',
        'weight': 0,
        'fillOpacity': 0.7
    }

# Add Layer 1 with color coding
folium.GeoJson(
    layer1,
    name="NWS Heat Risk",
    style_function=style_function,
    tooltip=folium.GeoJsonTooltip(fields=['raster_value'],
                                  aliases=['Heat Risk Value'],
                                  style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;"))
).add_to(m)

# Add the colormap to the map
colormap.add_to(m)
colormap.caption = 'Heat Risk Value'

# # Add Layer 2 (CDC Health Index data)
# folium.Choropleth(
#     geo_data=layer2,
#     name="CDC Health Index",
#     data=layer2,
#     # columns=['ZCTA', 'HHI'],
#     columns=['ZCTA'],
#     key_on='feature.properties.ZCTA',
#     fill_color='YlOrRd',
#     fill_opacity=0.7,
#     line_opacity=0.2,
#     legend_name="Health Index"
# ).add_to(m)

# Add layer control
folium.LayerControl().add_to(m)

# Display the map
folium_static(m)

# Additional information
st.write(f"Displaying Heat Risk data for {selected_day}")
st.write("Layer 1: NWS Heat Risk data")
st.write("Layer 2: CDC Health Index data")






# another GIS question while i have you — whats the right way to “merge” a vector and a raster layer in python? im trying to create a dashboard that is basically the product of this NWS heat risk layer and this CDC social vulnerability layer. and by right i mean, what is this kind of problem even called… my first approach was going to be to rasterize the CDC vector layer on the same grid and then just smush them together

# hmmm yeah i'd go vector to raster probably. it sounds like a clip operation, sort of? if you let the vector be vector

# otherwise if you get everything to raster it's https://en.wikipedia.org/wiki/Map_algebra
# or
# https://pro.arcgis.com/en/pro-app/latest/tool-reference/spatial-analyst/raster-calculator.htm

# and you can do those operations with python in GDAL, or just numpy if you're not worried about georeferences being off. Rasterio is a nice wrapper for GDAL that mapbox made (i think)


