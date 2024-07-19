import streamlit as st
import folium
from streamlit_folium import folium_static
import geopandas as gpd
import pandas as pd
import os
import requests
import zipfile
import rasterio
import branca.colormap as cm
from rasterio.features import shapes
from shapely.geometry import Polygon, shape
import h3
import numpy as np

st.set_page_config(layout="wide")

data_dir = "data"
if not os.path.exists(data_dir):
    os.makedirs(data_dir, exist_ok=True)

url_list = {
    "Day 1": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_1_Mercator.tif",
    "Day 2": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_2_Mercator.tif",
    "Day 3": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_3_Mercator.tif",
    "Day 4": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_4_Mercator.tif",
    "Day 5": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_5_Mercator.tif",
    "Day 6": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_6_Mercator.tif",
    "Day 7": "https://www.wpc.ncep.noaa.gov/heatrisk/data/HeatRisk_7_Mercator.tif"
}

def convert_excel_to_parquet(excel_file_path, parquet_file_path):
    # Check if the Parquet file already exists
    if not os.path.exists(parquet_file_path):
        # Read the Excel file into a DataFrame
        df = pd.read_excel(excel_file_path)
        
        # Convert the DataFrame to a Parquet file
        df.to_parquet(parquet_file_path, index=False)
        print(f"Converted {excel_file_path} to {parquet_file_path}")
    else:
        print(f"Parquet file {parquet_file_path} already exists.")

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

@st.cache_data
def prepare_layer1():
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
def prepare_layer2():

    @st.cache_data
    def load_cdc_data():
        excel_url = "https://gis.cdc.gov/HHI/Documents/HHI_Data.zip"
        excel_zip = f"{data_dir}/HHI_Data.zip"
        excel_file = f"{data_dir}/HHI Data 2024 United States.xlsx"
        parquet_file = f"{data_dir}/HHI Data 2024 United States.parquet"
        if not os.path.exists(excel_zip):
            download_file(excel_url, excel_zip)
            with zipfile.ZipFile(excel_zip, 'r') as zip_ref:
                zip_ref.extractall(data_dir)
            convert_excel_to_parquet(excel_file, parquet_file)
        return pd.read_parquet(parquet_file)

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

    hhi_data = load_cdc_data()
    boundaries = load_zcta_boundaries()
    hhi_data['ZCTA'] = hhi_data['ZCTA'].astype(str)
    boundaries['ZCTA5CE20'] = boundaries['ZCTA5CE20'].astype(str)
    return boundaries.merge(hhi_data, left_on='ZCTA5CE20', right_on='ZCTA', how='inner')

def hexgrid_from_bounds(bounds, resolution):
    minx, miny, maxx, maxy = bounds
    hexagons = []
    for lat in np.arange(miny, maxy, resolution):
        for lon in np.arange(minx, maxx, resolution):
            hex_id = h3.geo_to_h3(lat, lon, resolution)
            hex_coords = h3.h3_to_geo_boundary(hex_id, geo_json=True)
            hexagon = Polygon(hex_coords)
            hexagons.append(hexagon)
    return gpd.GeoDataFrame(geometry=hexagons, crs="EPSG:4326")

def compute_hexagon_values(layer1_gdf, layer2_gdf, hexgrid):
    hexgrid["h3_index"] = [h3.geo_to_h3(g.y, g.x, 9) for g in hexgrid.geometry.centroid]
    layer1_gdf = layer1_gdf.to_crs(epsg=4326)
    layer2_gdf = layer2_gdf.to_crs(epsg=4326)
    
    hex_values = {}
    for index, hexagon in hexgrid.iterrows():
        hex_id = hexagon["h3_index"]
        intersect_layer1 = layer1_gdf[layer1_gdf.intersects(hexagon.geometry)]
        intersect_layer2 = layer2_gdf[layer2_gdf.intersects(hexagon.geometry)]
        
        if not intersect_layer1.empty and not intersect_layer2.empty:
            avg_layer1 = intersect_layer1["raster_value"].mean()
            avg_layer2 = intersect_layer2["OVERALL_SCORE"].mean()
            hex_values[hex_id] = avg_layer1 * avg_layer2

    hexgrid["product"] = hexgrid["h3_index"].map(hex_values).fillna(0)
    return hexgrid

#####################################################################
# Streamlit app
#####################################################################
st.title("Heat Risk and Health Index Map")

# Create a base map
m = folium.Map(location=[39.8283, -98.5795], zoom_start=4)

# Create checkboxes for layer visibility
st.sidebar.header("Layer Visibility")
show_heat_risk = st.sidebar.checkbox("Show NWS Heat Risk", value=False)
show_health_index = st.sidebar.checkbox("Show CDC Health Index", value=False)
show_combined_layer = st.sidebar.checkbox("Show Combined Layer", value=False)

# LAYER 1: NWS Heat Risk data
geodataframes = prepare_layer1()
selected_day = st.selectbox("Select day for Heat Risk data:", list(geodataframes.keys()))
layer1_vector = geodataframes[selected_day]
layer1_raster = rasterio.open(os.path.join(data_dir, f"{selected_day}.tif"))

# Create a color map for Layer 1
min_value = layer1_vector['raster_value'].min()
max_value = layer1_vector['raster_value'].max()
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
        layer1_vector,
        name="NWS Heat Risk",
        style_function=style_function
    ).add_to(m)
    colormap1.add_to(m)
    colormap1.caption = 'Heat Risk Value'

# LAYER 2: CDC Health Index data
layer2_vector = prepare_layer2()
if show_health_index:
    health_index_layer = folium.Choropleth(
        geo_data=layer2_vector,
        name="CDC Health Index",
        data=layer2_vector,
        columns=['ZCTA', 'OVERALL_SCORE'],
        key_on='feature.properties.ZCTA',
        fill_color='YlOrRd',
        fill_opacity=0.7,
        line_opacity=0,
        legend_name="Overall Health Index Score"
    ).add_to(m)

# LAYER 3: Combined Layer
bounds = layer1_vector.geometry.total_bounds
hexgrid = hexgrid_from_bounds(bounds, 0.1)  # Adjust resolution as needed
combined_values_hexgrid = compute_hexagon_values(layer1_vector, layer2_vector, hexgrid)

def style_function_combined(feature):
    value = feature['properties']['product']
    return {
        'fillColor': colormap2(value),
        'color': 'black',
        'weight': 0,
        'fillOpacity': 0.7
    }

if show_combined_layer:
    combined_layer = folium.GeoJson(
        combined_values_hexgrid,
        name="Combined Layer",
        style_function=style_function_combined
    ).add_to(m)

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
if show_combined_layer:
    st.write("Layer 3: Combined Layer (product of Heat Risk and Health Index)")
