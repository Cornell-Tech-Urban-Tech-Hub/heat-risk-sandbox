import os
import requests
import geopandas as gpd
from datetime import datetime

def load_data(selected_day, data_dir, today):
    """
    Load NWS Heat Risk x CDC Heat and Health Index data for the selected day.

    Args:
        selected_day (str): The selected day (e.g., 'Day 1')
        data_dir (str): Directory to store the data files
        today (datetime): The current date

    Returns:
        GeoDataFrame: The loaded dataset or None if there was an error
    """
    os.makedirs(data_dir, exist_ok=True)
    formatted_day = selected_day.replace(' ', '+')
    current_date = today.strftime("%Y%m%d")
    local_file = os.path.join(data_dir, f'heat_risk_analysis_{selected_day}.geoparquet')

    # Check if the file exists and if it was created today
    if os.path.exists(local_file):
        file_mod_time = datetime.fromtimestamp(os.path.getmtime(local_file))
        if file_mod_time.date() == today.date():
            print(f"{local_file} is up to date.")
            return gpd.read_parquet(local_file)

    # Download the file if it's outdated or doesn't exist
    url = f'https://heat-risk-dashboard.s3.amazonaws.com/heat_risk_analysis_{formatted_day}_{current_date}.geoparquet'
    try:
        print(f"Downloading {url}...")
        response = requests.get(url)
        response.raise_for_status()
        with open(local_file, 'wb') as file:
            file.write(response.content)
        print(f"Saved to {local_file}")
    except requests.exceptions.RequestException as e:
        print(f"Failed to download data: {e}")
        return None

    # Load and return the GeoDataFrame
    return gpd.read_parquet(local_file)

def load_state_county_data():
    """
    Load state and county boundary data from pre-downloaded Parquet files.

    Returns:
        tuple: A tuple containing two GeoDataFrames: states and counties.
    """
    states_file = "data/us_states.parquet"
    counties_file = "data/us_counties.parquet"

    # Load the GeoDataFrames
    states = gpd.read_parquet(states_file)
    counties = gpd.read_parquet(counties_file)

    # Ensure the GeoDataFrames are in a geographic CRS (WGS84)
    if not states.crs.is_geographic:
        states = states.to_crs(epsg=4326)
    if not counties.crs.is_geographic:
        counties = counties.to_crs(epsg=4326)

    return states, counties
