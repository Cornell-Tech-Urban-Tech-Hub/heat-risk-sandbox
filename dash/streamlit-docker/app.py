import time
import streamlit as st
from streamlit_folium import st_folium
import pandas as pd
from datetime import datetime, timedelta
import utils
import pytz

# Set up the Streamlit app
st.set_page_config(layout="wide")

# Sidebar
st.sidebar.title("SANDBOX EDITION")
st.sidebar.title("Heat Risk and Health Index Dashboard")
st.sidebar.markdown("This is an experimental prototype provided for informational purposes only by the [Jacobs Urban Tech Hub](https://urbantech.cornell.edu/) as part of the [Cornell Initiative on Aging and Adaptation to Extreme Heat](https://agingandadaptation.cornell.edu/).")

st.sidebar.markdown("This sandbox allows you to view past data sequences. For the most recent data, please visit the [Heat Risk and Health Index Dashboard](https://heatmap.urbantech.info/).")

st.sidebar.markdown("Please fill out a [survey](https://cornell.ca1.qualtrics.com/jfe/form/SV_4TTfOiGyOZJNVP0) to provide feedback. Bug reports [here](mailto:urbantech@cornell.edu)")

# Day selection
tz = pytz.timezone('America/New_York')
# today = datetime.now(tz)

# pick the start date
start_date_options=utils.scan_archive_dates()
start_date_options = [date.strftime("%m/%d/%Y") for date in start_date_options]
start_date_label = st.sidebar.selectbox("Select Start Date", start_date_options)
selected_date = start_date_label

# pick a day in the series
# Convert selected_date to a datetime object
selected_date_dt = datetime.strptime(selected_date, "%m/%d/%Y")


# Generate date options starting from the selected_date
date_options = [(selected_date_dt + timedelta(days=i)).strftime("%m/%d/%Y") for i in range(7)]

day_options = [f"Day {i+1} - {date_options[i]}" for i in range(7)]
selected_day_label = st.sidebar.selectbox("Select Heat Risk Day", day_options)


# Filtering options
heat_threshold = st.sidebar.multiselect("Select Heat Risk Levels", [0, 1, 2, 3, 4], default=[2, 3, 4])

# Expander for learning more about heat risk levels
with st.sidebar.expander('Learn more about heat risk levels'):
    st.markdown(utils.get_heat_risk_levels_description())


# Load the heat risk data
try:
    selected_day = selected_day_label.split(' - ')[0]
    selected_date = selected_day_label.split(' - ')[1]

    layer1_with_weighted_values = utils.load_data(selected_day, selected_date)
    if layer1_with_weighted_values is None or layer1_with_weighted_values.empty:
        st.error("Data could not be loaded. Please check the data source or network connection.")
except Exception as e:
    st.error(f"An error occurred while loading the data: {e}")
    layer1_with_weighted_values = None

# Check if data is loaded successfully
if layer1_with_weighted_values is None:
    st.error("Failed to load data. Please try again later.")
else:
    # Load geographic data using the utility function
    states, counties, selected_state, selected_county, zipcode_boundary = utils.load_geographic_data()

# Generate the column mappings dynamically based on consistent formatting
hhi_column_mapping = utils.generate_column_mapping(layer1_with_weighted_values.columns)

# Get the list of available columns for HHI indicators
hhi_columns = list(hhi_column_mapping.keys())
hhi_columns = utils.move_column_to_front(hhi_columns, "weighted_OVERALL_SCORE")

# Create a list of display names
display_names = [hhi_column_mapping[col] for col in hhi_columns]

# Use the display names in the selectbox
selected_display_name = st.sidebar.selectbox(
    "Select CDC Heat and Health Index Indicator", 
    display_names,
    index=0
)

# Map the selected display name back to the actual column name
selected_hhi_indicator = hhi_columns[display_names.index(selected_display_name)]

# Load the HHI description data
hhi_desc_df = utils.load_hhi_description()

# Get the description for the selected HHI indicator
description_text = utils.get_hhi_indicator_description(hhi_desc_df, selected_hhi_indicator)

# Display the description in the expander
with st.sidebar.expander('Learn more about this HHI Indicator'):
    # make sure description text is on a new line
    st.markdown(f"""
        **{selected_hhi_indicator}**:

        {description_text}
        """)

heat_health_index_threshold = st.sidebar.slider("Heat Health Index Percentile Threshold", 0, 100, 80, step=10)

# Initialize filtered_data as an empty DataFrame
filtered_data = pd.DataFrame()

st.sidebar.write("Please click the button below to download the filtered data as a CSV file.")
st.sidebar.download_button(label="Download", data=filtered_data.to_csv(), mime='text/csv')

# Data source information
st.sidebar.markdown("""
**Data Sources:**
- [NWS Heat Risk](https://www.wpc.ncep.noaa.gov/heatrisk/)
- [CDC Heat and Health Index](https://ephtracking.cdc.gov/Applications/heatTracker/)
""")

# Main dashboard
start_time = time.time()
m = utils.create_map(layer1_with_weighted_values, selected_hhi_indicator, heat_threshold, heat_health_index_threshold, selected_state, selected_county, states, counties, zipcode_boundary)
end_time = time.time()
map_creation_time = end_time - start_time

# Set map size
map_width, map_height = 1000, 700

# Use st_folium to display the map
st_folium(m, width=map_width, height=map_height, returned_objects=["last_active_drawing", "last_clicked"])

# Default to select "New York" state
selected_state = "New York"

if selected_state != "Select a State" or selected_county != "Select a County":
    if selected_county != "Select a County" and selected_state != "Select a State":
        selected_county_geom = counties[(counties['STATE_NAME'] == selected_state) & (counties['NAME'] == selected_county)].geometry.values
        if selected_county_geom.size > 0:
            filtered_data = layer1_with_weighted_values[layer1_with_weighted_values.intersects(selected_county_geom[0])]
            title_suffix = f" - {selected_state}, {selected_county}"
        else:
            st.warning("Could not find the geometry for the selected county.")
            filtered_data = pd.DataFrame()
    elif selected_state != "Select a State":
        selected_state_geom = states[states['NAME'] == selected_state].geometry.values
        if selected_state_geom.size > 0:
            filtered_data = layer1_with_weighted_values[layer1_with_weighted_values.intersects(selected_state_geom[0])]
            title_suffix = f" - {selected_state}"
        else:
            st.warning("Could not find the geometry for the selected state.")
            filtered_data = pd.DataFrame()
    else:
        filtered_data = layer1_with_weighted_values
        title_suffix = ""
    
    if not filtered_data.empty:
        st.subheader(f"Key Summary {title_suffix}")
        st.markdown("**Sociodemographic**")
        st.markdown(f"Affected population: {filtered_data['weighted_POP'].sum()}")

        with st.expander("See detailed plot for affected population"):
            # Prepare the data for the stacked bar chart
            population_by_risk_level = filtered_data.groupby('raster_value')['weighted_POP'].sum().reset_index()
            population_by_risk_level['raster_value'] = population_by_risk_level['raster_value'].astype(str)

            # Create the chart using the helper function
            fig_population = utils.create_plot(population_by_risk_level, 
                                         y_column='raster_value', 
                                         x_column='weighted_POP', 
                                         color_column='raster_value',
                                         title="Population Affected by Heat Risk Level",
                                         y_label='Heat Risk Level', 
                                         x_label='Affected Population')
            st.plotly_chart(fig_population)

        st.markdown(f"Percentage of persons aged 65 and older estimate: {filtered_data['weighted_P_AGE65'].mean():.2f}%")

        with st.expander("See detailed plot for affected population aged 65 and older"):
            age65_by_risk_level = filtered_data.groupby('raster_value')['weighted_P_AGE65'].mean().reset_index()
            age65_by_risk_level['raster_value'] = age65_by_risk_level['raster_value'].astype(str)

            fig_age65 = utils.create_plot(age65_by_risk_level,
                                    y_column='raster_value',
                                    x_column='weighted_P_AGE65',
                                    color_column='raster_value',
                                    title="Percentage of Persons Aged 65 and Older by Heat Risk Level",
                                    y_label='Heat Risk Level',
                                    x_label='Percentage of Persons Aged 65 and Older')
            st.plotly_chart(fig_age65)
    else:
        st.warning('No data available for the selected state or county.')
else:
    st.write('Select a State or County to get key summaries')