# NWS Heat Risk x CDC Heat and Health Index Dashboard

This application combines two valuable new indices published by federal agencies to help understand the health impacts of extreme heat — the NWS Heat Risk and the CDC Heat and Health Index.

The majority of this code was composed with the help of Claude Sonnet.

[https://claude.ai/chat/9b0de591-0e95-4c91-8e9a-61f233c81716](https://claude.ai/chat/9b0de591-0e95-4c91-8e9a-61f233c81716) <-- chat with most of the current code

## WIP

### `scraper` 

Goal is to create Lambda function packaged for deployment as an AWS CDK stack. Runs 1x daily to download and combine all the files into 7 geoparquets, one for each day, saved to a public S3 bucket.

Grab the script from here -- https://claude.ai/chat/9b0de591-0e95-4c91-8e9a-61f233c81716

Having trouble getting the SAM testing environment set up, try again tomorrow to create the CDK structure from scratch.


### `streamlit-app`

Streamlit app packaged for deployment on Streamlit Community Cloud.

Allows users to select which day and indicator, and threshholds for filters for both.

1. add tooltips that show the HHI values for all columns on click/mouseover of each cell (plus some geographic info like the ZIPcode and lookup municipality name)
2. refactor (using Claude) to use the data stored in S3


### `dev-notebook`

Initial prototyping and debugging of data pipelines and map.
