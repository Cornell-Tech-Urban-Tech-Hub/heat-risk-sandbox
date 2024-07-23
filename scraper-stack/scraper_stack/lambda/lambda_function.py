import os
import json
import urllib.request
import zipfile
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.features import shapes
from pyproj import CRS
import boto3
from datetime import datetime

# Helper functions (download_file, geotiff_to_geodataframe, convert_excel_to_parquet remain the same)

def load_heat_risk_data(data_dir):
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
        file_path = f"/tmp/{day}.tif"
        urllib.request.urlretrieve(url, file_path)
        gdf = geotiff_to_geodataframe(file_path)
        geodataframes[day] = gdf
        os.remove(file_path)  # Clean up after processing
    
    return geodataframes

def load_cdc_data(data_dir):
    # Load CDC Heat and Health Index Data
    boundaries_url = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip"
    boundaries_zip = "/tmp/cb_2020_us_zcta520_500k.zip"
    urllib.request.urlretrieve(boundaries_url, boundaries_zip)
    with zipfile.ZipFile(boundaries_zip, 'r') as zip_ref:
        zip_ref.extractall("/tmp")
    boundaries_file = "/tmp/cb_2020_us_zcta520_500k.shp"
    zcta_boundaries = gpd.read_file(boundaries_file).to_crs(epsg=4326)
    
    excel_url = "https://gis.cdc.gov/HHI/Documents/HHI_Data.zip"
    excel_zip = "/tmp/HHI_Data.zip"
    urllib.request.urlretrieve(excel_url, excel_zip)
    with zipfile.ZipFile(excel_zip, 'r') as zip_ref:
        zip_ref.extractall("/tmp")
    excel_file = "/tmp/HHI Data 2024 United States.xlsx"
    hhi_data = pd.read_excel(excel_file)
    
    hhi_data['ZCTA'] = hhi_data['ZCTA'].astype(str)
    zcta_boundaries['ZCTA5CE20'] = zcta_boundaries['ZCTA5CE20'].astype(str)
    zcta_with_hhi = zcta_boundaries.merge(hhi_data, left_on='ZCTA5CE20', right_on='ZCTA', how='inner')
    
    # Clean up
    os.remove(boundaries_zip)
    os.remove(excel_zip)
    os.remove(excel_file)
    for file in os.listdir("/tmp"):
        if file.startswith("cb_2020_us_zcta520_500k"):
            os.remove(f"/tmp/{file}")
    
    return zcta_with_hhi

# create_combined_map function remains the same

def save_to_s3(data, bucket_name, file_name):
    s3 = boto3.client('s3')
    local_file = f"/tmp/{file_name}"
    data.to_parquet(local_file)
    s3.upload_file(local_file, bucket_name, file_name)
    print(f"Saved {file_name} to S3 bucket {bucket_name}")
    os.remove(local_file)  # Remove local file after uploading

def lambda_handler(event, context):
    data_dir = "/tmp"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)

    geodataframes = load_heat_risk_data(data_dir)
    zcta_with_hhi = load_cdc_data(data_dir)
    
    selected_hhi_indicator = "OVERALL_SCORE"
    heat_threshold = [2, 3, 4]
    heat_health_index_threshold = 80
    
    bucket_name = os.environ['BUCKET_NAME']
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for day, gdf in geodataframes.items():
        result = create_combined_map(gdf, zcta_with_hhi, selected_hhi_indicator, heat_threshold, heat_health_index_threshold)
        file_name = f"heat_risk_analysis_{day}_{timestamp}.geoparquet"
        save_to_s3(result, bucket_name, file_name)

    return {
        'statusCode': 200,
        'body': json.dumps('Heat risk analysis completed successfully!')
    }