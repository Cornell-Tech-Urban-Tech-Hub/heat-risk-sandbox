import os
import requests
import geopandas as gpd
from datetime import datetime
import pandas as pd
import streamlit as st

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
    county boundary url: "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_county_500k.zip"
    state boundary url: "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_state_500k.zip"

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

def generate_column_mapping(columns, prefix='weighted_', replacement='weighted ', title_case=True):
    """
    Generate a mapping for column names with consistent formatting.
    
    Args:
    columns (list): List of column names.
    prefix (str): The prefix to replace (default is 'weighted_').
    replacement (str): The string to replace the prefix with (default is 'weighted ').
    title_case (bool): If True, convert column names to title case (default is True).
    
    Returns:
    dict: A dictionary with original column names as keys and formatted names as values.
    """
    if title_case:
        return {col: col.replace(prefix, replacement).replace('_', ' ').title() for col in columns if col.startswith(prefix)}
    else:
        return {col: col.replace(prefix, replacement).replace('_', ' ') for col in columns if col.startswith(prefix)}

def move_column_to_front(columns, column_name):
    """
    Ensure a specific column is at the front of the list.
    
    Args:
    columns (list): List of column names.
    column_name (str): The name of the column to move to the front.
    
    Returns:
    list: The modified list of column names.
    """
    if column_name in columns:
        columns.remove(column_name)
        columns.insert(0, column_name)
    return columns

@st.cache_data
def load_hhi_description(file_path='./data/HHI_Data_Dictionary_2024.csv'):
    """
    Load the HHI data dictionary from a CSV file.
    
    Args:
    file_path (str): Path to the CSV file.
    
    Returns:
    pd.DataFrame: DataFrame containing the HHI descriptions.
    """
    return pd.read_csv(file_path)

def get_hhi_indicator_description(hhi_desc_df, indicator_name):
    """
    Fetch the description for a given HHI indicator.
    
    Args:
    hhi_desc_df (pd.DataFrame): DataFrame containing the HHI descriptions.
    indicator_name (str): The name of the HHI indicator.
    
    Returns:
    str: The description for the HHI indicator.
    """
    selected_description = hhi_desc_df.loc[hhi_desc_df['weighted_2024_VARIABLE_NAME'] == indicator_name, '2024_DESCRIPTION'].values
    if len(selected_description) > 0:
        return selected_description[0]
    else:
        return "No description available for this indicator."

def get_heat_risk_levels_description():
    """
    Return the description of heat risk levels.
    
    Returns:
    str: A formatted string containing the descriptions of heat risk levels.
    """
    return """
    **Heat Risk Levels:**
    
    - **0:** Little to no risk from expected heat.
    - **1:** Minor - This level of heat affects primarily those individuals extremely sensitive to heat, especially when outdoors without effective cooling and/or adequate hydration.
    - **2:** Moderate - This level of heat affects most individuals sensitive to heat, especially those without effective cooling and/or adequate hydration. Impacts possible in some health systems and in heat-sensitive industries.
    - **3:** Major - This level of heat affects anyone without effective cooling and/or adequate hydration. Impacts likely in some health systems, heat-sensitive industries, and infrastructure.
    - **4:** Extreme - This level of rare and/or long-duration extreme heat with little to no overnight relief affects anyone without effective cooling and/or adequate hydration. Impacts likely in most health systems, heat-sensitive industries, and infrastructure.
    """