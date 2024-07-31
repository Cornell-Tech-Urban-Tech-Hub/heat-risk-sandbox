from aws_cdk import (
    aws_ec2 as ec2, 
    aws_batch as batch,
    aws_ecs as ecs,
    aws_iam as iam,
    App, Stack, CfnOutput, Size
)
from constructs import Construct

class BatchFargateStack(Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # VPC setup
        vpc = ec2.Vpc(self, "VPC")

        # Batch Job Queue
        self.batch_queue = batch.JobQueue(self, "JobQueue")

        # Create Batch Compute Environments
        for i in range(3):
            name = f"MyFargateEnv{i}"
            fargate_spot_environment = batch.FargateComputeEnvironment(self, name,
                vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_NAT),
                vpc=vpc
            )
            self.batch_queue.add_compute_environment(fargate_spot_environment, i)

        # Task execution IAM role for Fargate
        task_execution_role = iam.Role(self, "TaskExecutionRole",
                                  assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
                                  managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonECSTaskExecutionRolePolicy")])

        # Build Docker image from local Dockerfile
        docker_image = ecs.ContainerImage.from_asset("build")

        # Create Job Definition
        batch_jobDef = batch.EcsJobDefinition(self, "MyJobDef",
            container=batch.EcsFargateContainerDefinition(self, "FargateCDKJobDef",
                image=docker_image,
                command=["python", "/app/batch_script.py"],  # Adjust the path as needed
                memory=Size.mebibytes(512),
                cpu=0.25,
                execution_role=task_execution_role
            )
        )

        # Outputs
        CfnOutput(self, "BatchJobQueue", value=self.batch_queue.job_queue_name)
        CfnOutput(self, "JobDefinition", value=batch_jobDef.job_definition_name)

app = App()
BatchFargateStack(app, "BatchFargateStack-HeatmapProcessor")
app.synth()
