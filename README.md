# NWS Heat Risk x CDC Heat and Health Index Dashboard

This application is an experimental dashboard that two new indices published by federal agencies to help understand the health impacts of extreme heat — the NWS Heat Risk and the CDC Heat and Health Index.

It consists of two parts:

- A Python **scraper** script that is deployed to AWS with Terraform, and runs an AWS Batch job nightly to fetch and preprocess data from the NWS and CDC.
- A Python web **dash** streamlit app that is deployed with to AWS Fargate with AWS CDK.

#### TODO: merge the two deployments into a single stack.

## `dash`

A Streamlit app packaged for deployment on Streamlit Community Cloud. Allows users to make selections of day and indicator, and threshholds for filters for both.

### Deployment

Deployed using AWS Fargate with [this approach](https://github.com/tzaffi/streamlit-cdk-fargate)

## `scraper`

A containerized Batch script deployed to AWS with Terraform runs once nightly to fetch and preprocess and join the NWS and CDC data layers. One geoparquet is produced for each of the 7 days of the NWS Heat Risk forecast with area-weighted indicators joined from the CDC Heat and Health Index data (which is the same for all days). These data are stored in a public S3 bucket.

Goal is to create Lambda function packaged for deployment as an AWS CDK stack, and have it runs 1x daily to download and combine all the files into 7 geoparquets, one for each day, saved to a public S3 bucket and accessible using the following filename template `https://heat-risk-dashboard.s3.amazonaws.com/heat_risk_analysis_Day+1_20240801.geoparquet` where YYYYMMDD string is the date of the NWS Heat Risk forecast and Day+n is which day in the forecast the file represents.

### Development

1. Test it locally:
        
        cd ./scraper/build
        
        docker build -t urbantech/heat-risk-scraper:latest .
        
        docker run -it urbantech/heat-risk-scraper:latest # saving to S3 will fail


### Deployment

2. Build and push the docker image

        ./build_and_push.sh


3. Deploy/update the stack with Terraform

        terraform apply

4. Manually test the AWS Batch job (fastest to do in the AWS web console but can also use CLI)

        aws sso login
        
        aws batch submit-job \
                --job-name ManualTrigger-$(date +%Y%m%d-%H%M%S) \
                --job-queue <your-job-queue-arn> \
                --job-definition <your-job-definition-arn>

        aws batch describe-jobs --jobs <your-job-id>



## `notebooks`

Miscellaneous Jupyter notebooks for prototyping and debugging of data pipelines and map.