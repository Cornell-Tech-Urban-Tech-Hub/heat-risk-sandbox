import os
import requests
import zipfile
import geopandas as gpd

def download_and_extract_zip(url, extract_to='data'):
    os.makedirs(extract_to, exist_ok=True)
    local_zip_file = os.path.join(extract_to, os.path.basename(url))
    
    if not os.path.exists(local_zip_file):
        print(f"Downloading {url}...")
        response = requests.get(url)
        response.raise_for_status()
        with open(local_zip_file, 'wb') as file:
            file.write(response.content)
        print(f"Saved to {local_zip_file}")
    
    with zipfile.ZipFile(local_zip_file, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    print(f"Extracted to {extract_to}")

county_url = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_county_500k.zip"
state_url = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_state_500k.zip"

download_and_extract_zip(county_url)
download_and_extract_zip(state_url)

# Load the shapefiles
county_shapefile = "data/cb_2020_us_county_500k.shp"
state_shapefile = "data/cb_2020_us_state_500k.shp"

counties = gpd.read_file(county_shapefile)
states = gpd.read_file(state_shapefile)

# Save as GeoParquet
counties.to_parquet("data/us_counties.parquet")
states.to_parquet("data/us_states.parquet")

print("GeoParquet files saved.")
