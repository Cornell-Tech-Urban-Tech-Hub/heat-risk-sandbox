# NWS Heat Risk x CDC Heat and Health Index Dashboard

This application combines two valuable new indices published by federal agencies to help understand the health impacts of extreme heat — the NWS Heat Risk and the CDC Heat and Health Index.

The majority of this code was composed with the help of Claude Sonnet.

[https://claude.ai/chat/9b0de591-0e95-4c91-8e9a-61f233c81716](https://claude.ai/chat/9b0de591-0e95-4c91-8e9a-61f233c81716) <-- chat with most of the current code


## `dev-notebook`

Initial prototyping and debugging of data pipelines and map.

## `streamlit-app`

Streamlit app packaged for deployment on Streamlit Community Cloud. Allows users to select which day and indicator, and threshholds for filters for both.

### overlay method

1. change data source (DONE see `app-new.py`)
4. fix map center and zoom level
2. add tooltips that show the HHI values for all columns on click/mouseover of each cell (plus some geographic info like the ZIPcode and lookup municipality name)
3. make map bigger
5. deploy to Streamlit COmmunity Cloud, test, and make public
6. see if [lonboard](https://github.com/developmentseed/lonboard) is a better option for mapping (not sure it works with Streamlit though)

### h3 method
1. see `H3 test` notebook in `dev-notebook` folder

## `scraper`

Goal is to create Lambda function packaged for deployment as an AWS CDK stack, and have it runs 1x daily to download and combine all the files into 7 geoparquets, one for each day, saved to a public S3 bucket.

### Development

1. Test it locally:
        
        cd ./scraper/build
        
        docker build -t urbantech/heat-risk-scraper:latest .
        
        docker run -it urbantech/heat-risk-scraper:latest # saving to S3 will fail


2. do the Terreform


Initial prototyping and debugging of data pipelines and map.

# This branch was contributed by Yixuan Wang and Leihao Fang
=======
        terraform apply

3. Build and push the docker image

        ./build_and_push.sh


4. Manually test the AWS Batch job (fastest to do in the AWS web console but can also use CLI)

        aws sso login
        
        aws batch submit-job \
                --job-name ManualTrigger-$(date +%Y%m%d-%H%M%S) \
                --job-queue <your-job-queue-arn> \
                --job-definition <your-job-definition-arn>

        aws batch describe-jobs --jobs <your-job-id>

