import os
import requests
import geopandas as gpd
from datetime import datetime


def load_data(selected_day, data_dir, today):
    """
    Load NWS Heat Risk x CDC Heat and Health Index data for the selected day

    Args:
        selected_day(str): The selected day (e.g., 'Day 1')
        data_dir (str): Directory to store the data files
        today (datetime): The current date

    Returns:
        GeoDataFrame: the loaded dataset
    """