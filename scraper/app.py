#!/usr/bin/env python3
import os

from aws_cdk import (
    App,
    Stack,
    Duration,
    aws_lambda as _lambda,
    # aws_lambda_python_alpha as lambda_alpha_,
    aws_iam as iam,
)
from constructs import Construct

class HeatRiskAnalysisStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # # Create a Lambda function (only works for very simple standard library functions)
        # heat_risk_lambda = _lambda.Function(
        #     self, "HeatRiskAnalysisFunction",
        #     runtime=_lambda.Runtime.PYTHON_3_9,
        #     handler="lambda_function.lambda_handler",
        #     code=_lambda.Code.from_asset("lambda"),
        #     timeout=Duration.minutes(15),
        #     memory_size=3008,
        # )

        # # this will build and package an env using entry folder requirements.txt without need for layers
        # heat_risk_lambda = lambda_alpha_.PythonFunction(
        #     self, 
        #     "HeatRiskAnalysisFunction",
        #     entry="lambda",
        #     runtime=_lambda.Runtime.PYTHON_3_9,
        #     index="lambda_function.py",
        #     handler="handler",
        #     timeout=Duration.seconds(120),
        #     memory_size=1024,
        #     environment={
        #         "region": "us-east-1",
        #         "bucket": "heat-and-health-dashboard"
        #         },
        #     )
        
        # this will build and package a Docker contained and deploy it to ECR
        heat_risk_lambda = _lambda.DockerImageFunction(
            self, "HeatRiskAnalysisFunction",
            code=_lambda.DockerImageCode.from_image_asset("lambda"),
            timeout=Duration.minutes(15), #max is 15 minutes
            memory_size=10240, # max is 10,240Mb
        )

        # Grant the Lambda function permissions to access S3
        heat_risk_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:PutObject"],
            resources=["arn:aws:s3:::heat-and-health-dashboard/*"]
        ))

        # Grant the Lambda function permissions to access the internet
        heat_risk_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface"],
            resources=["*"]
        ))

app = App()

HeatRiskAnalysisStack(app, "HeatRiskAnalysisStack")

app.synth()