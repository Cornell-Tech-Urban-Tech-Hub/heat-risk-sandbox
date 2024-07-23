from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
    Duration,
    RemovalPolicy
)
from constructs import Construct

class HeatRiskAnalysisStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create S3 bucket
        bucket = s3.Bucket(
            self, "HeatRiskAnalysisBucket",
            bucket_name="heat-risk-analysis-bucket",  # You might want to make this unique
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY  # Be cautious with this in production
        )

        # Create Lambda function
        lambda_function = _lambda.Function(
            self, "HeatRiskAnalysisFunction",
            runtime=_lambda.Runtime.PYTHON_3_8,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.minutes(15),
            memory_size=3008,
            environment={
                "BUCKET_NAME": bucket.bucket_name
            }
        )

        # Grant Lambda function write permissions to S3 bucket
        bucket.grant_write(lambda_function)

        # Create CloudWatch Event to trigger Lambda function daily
        rule = events.Rule(
            self, "DailyHeatRiskAnalysisRule",
            schedule=events.Schedule.cron(
                minute="0",
                hour="0",
                month="*",
                week_day="*",
                year="*"
            )
        )

        rule.add_target(targets.LambdaFunction(lambda_function))