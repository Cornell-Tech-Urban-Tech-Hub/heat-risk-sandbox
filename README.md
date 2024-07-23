# NWS Heat Risk x CDC Heat and Health Index Dashboard

This application combines two valuable new indices published by federal agencies to help understand the health impacts of extreme heat — the NWS Heat Risk and the CDC Heat and Health Index.

The majority of this code was composed with the help of Claude Sonnet.

## WIP

### `scraper.py` 

Lambda function packaged for deployment as an AWS CDK stack. Runs 1x daily to download and combine all the files into 7 geoparquets, one for each day, saved to a public S3 bucket.

1. test it locally 
2. deploy and check it works

### `streamlit-app`

Streamlit app packaged for deployment on Streamlit Community Cloud.

Allows users to select which day and indicator, and threshholds for filters for both.

1. add tooltips that show the HHI values for all columns on click/mouseover of each cell (plus some geographic info like the ZIPcode and lookup municipality name)
2. refactor (using Claude) to use the data stored in S3


### `dev-notebook`

Initial prototyping and debugging of data pipelines and map.
