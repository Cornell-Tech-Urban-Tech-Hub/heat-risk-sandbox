# NWS Heat Risk x CDC Heat and Health Index Dashboard

This application combines two valuable new indices published by federal agencies to help understand the health impacts of extreme heat — the NWS Heat Risk and the CDC Heat and Health Index.

The majority of this code was composed with the help of Claude Sonnet.

## development plan

### `app.py`

The streamlit app that allows users to select which day and indicator, and threshholds for filters for both.

1. add tooltips that show the HHI values for all columns on click/mouseover of each cell (plus some geographic info like the ZIPcode and lookup municipality name)
2. refactor (using Claude) to use the data stored in S3

### `scraper.py` - standalone data downloader 

Can be run daily, produces a geoparquet for each day of the NWS forecast, with the area-weighted CDC HHI data joined to it.

1. test locally
2. package in an AWS CDK stack that includes the public bucket construct used for storage
