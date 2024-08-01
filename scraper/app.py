#!/usr/bin/env python3
import os
from aws_cdk import (
    App,
    Stack,
    aws_ec2 as ec2,
    aws_ecr as ecr,
    aws_ecs as ecs,
    aws_iam as iam,
    CfnOutput
)
import aws_cdk.aws_batch_alpha as batch
from constructs import Construct

class BatchDockerStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create a VPC
        vpc = ec2.Vpc(self, "BatchVPC", max_azs=2)

        # Create an ECR repository
        repository = ecr.Repository(self, "DockerRepository")

        # Create a Batch compute environment
        compute_environment = batch.ComputeEnvironment(self, "BatchComputeEnv",
            compute_resources={
                "type": batch.ComputeResourceType.FARGATE,
                "vpc": vpc,
            },
            compute_environment_name="MyBatchComputeEnv"
        )

        # Create a Batch job queue
        job_queue = batch.JobQueue(self, "BatchJobQueue",
            compute_environments=[
                batch.JobQueueComputeEnvironment(
                    compute_environment=compute_environment,
                    order=1
                )
            ],
            priority=1
        )

        # Create an IAM role for the Batch job
        job_role = iam.Role(self, "BatchJobRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com")
        )

        # Grant the job role permission to pull from the ECR repository
        repository.grant_pull(job_role)

        # Create a Batch job definition
        job_definition = batch.JobDefinition(self, "BatchJobDefinition",
            container=batch.JobDefinitionContainer(
                image=ecs.ContainerImage.from_asset(os.path.join(os.path.dirname(__file__), "build")),
                vcpus=1,
                memory_limit_mib=2048,
                job_role=job_role,
                execution_role=job_role
            ),
            platform_capabilities=[batch.PlatformCapabilities.FARGATE]
        )

        # Output the job queue and job definition ARNs
        CfnOutput(self, "JobQueueArn", value=job_queue.job_queue_arn)
        CfnOutput(self, "JobDefinitionArn", value=job_definition.job_definition_arn)

# Create the app and the stack
app = App()
BatchDockerStack(app, "BatchDockerStack")
app.synth()