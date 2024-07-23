# NWS Heat Risk x CDC Heat and Health Index Dashboard

This application combines two valuable new indices published by federal agencies to help understand the health impacts of extreme heat — the NWS Heat Risk and the CDC Heat and Health Index.

The majority of this code was composed with the help of Claude Sonnet.

[https://claude.ai/chat/9b0de591-0e95-4c91-8e9a-61f233c81716](https://claude.ai/chat/9b0de591-0e95-4c91-8e9a-61f233c81716) <-- chat with most of the current code


## `streamlit-app`

Streamlit app packaged for deployment on Streamlit Community Cloud.

Allows users to select which day and indicator, and threshholds for filters for both.

1. change data source
    - can remove all the data processing code
    - replace with simple `requests` to get the 7 files from (use Claude to scaffold the code), or get it on the fly when the user changes the Day selection
        - URL format `https://heat-and-health-dashboard.s3.amazonaws.com/heat_risk_analysis_Day+1_20240723.geoparquet`
        - date format is `strftime("%Y%m%d")`
2. add tooltips that show the HHI values for all columns on click/mouseover of each cell (plus some geographic info like the ZIPcode and lookup municipality name)
3. make map bigger


## `scraper`

Goal is to create Lambda function packaged for deployment as an AWS CDK stack, and have it runs 1x daily to download and combine all the files into 7 geoparquets, one for each day, saved to a public S3 bucket.

**Current status:** Running as intended as local Python script.
- `scraper/scraper.py` works as a standalone script when logged into AWS via CLI, writing files to `s3://heat-and-health-dashboard`
- run manually with `cd scraper & python sraper.py`

**To do:** Lambda-ize and deploy with CDK.
1. test access to public S3 bucket [https://heat-and-health-dashboard.s3.amazonaws.com/heat_risk_analysis_Day+1_20240723.geoparquet](https://heat-and-health-dashboard.s3.amazonaws.com/heat_risk_analysis_Day+1_20240723.geoparquet)
2. download and test one of the output files for accuracy/integrity (load and plot in streamlit app) https://heat-and-health-dashboard.s3.amazonaws.com/heat_risk_analysis_Day+1_20240723.geoparquet
1. init an AWS CDK project + stack in a new folder `scraper-stack`
2. Configure the stack
3. Lambda-ize the scraper script
4. test the lambda locally
5. deploy and debug

## `dev-notebook`

Initial prototyping and debugging of data pipelines and map.
