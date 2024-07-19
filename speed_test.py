import pandas as pd
import time
import os

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

excel_file = 'data/HHI Data 2024 United States.xlsx'
parquet_file = 'data/HHI Data 2024 United States.parquet'
convert_excel_to_parquet(excel_file, parquet_file)

# Read Parquet file
start_time = time.time()
df_parquet = pd.read_parquet(parquet_file)
parquet_read_time = time.time() - start_time

# Read Excel file
start_time = time.time()
df_excel = pd.read_excel(excel_file)
excel_read_time = time.time() - start_time

print(f"Parquet read time: {parquet_read_time} seconds")
print(f"Excel read time: {excel_read_time} seconds")
