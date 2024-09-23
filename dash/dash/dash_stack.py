from aws_cdk import (
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_route53 as route53,
    aws_route53_targets as targets,
    aws_certificatemanager as acm,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_logs as logs,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cloudwatch_actions,
    Stack,
    Duration,
    CfnOutput,
    RemovalPolicy
)
from constructs import Construct

class DashStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Define the domain name
        domain_name = "urbantech.info"
        subdomain = "heatmap-sandbox"
        fqdn = f"{subdomain}.{domain_name}"

        # Create VPC and ECS Cluster with Container Insights enabled
        vpc = ec2.Vpc(self, "HeatDashStreamlitVPC", max_azs=2)
        cluster = ecs.Cluster(self, "HeatDashStreamlitCluster", 
            vpc=vpc,
            container_insights=True  # Enable Container Insights
        )

        # Load the Docker image
        image = ecs.ContainerImage.from_asset('streamlit-docker')

        # Look up the hosted zone
        hosted_zone = route53.HostedZone.from_lookup(self, "HostedZone", domain_name=domain_name)

        # Create a certificate
        certificate = acm.Certificate(self, "Certificate",
            domain_name=fqdn,
            validation=acm.CertificateValidation.from_dns(hosted_zone)
        )

        # Reference or create S3 bucket for heat risk data
        bucket_name = "heat-risk-dashboard"
        heat_risk_bucket = s3.Bucket.from_bucket_name(self, "HeatRiskBucket", bucket_name)

        # Create CloudFront distribution
        distribution = cloudfront.Distribution(self, "HeatRiskDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(heat_risk_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD
            ),
            certificate=certificate,
            domain_names=[fqdn]
        )

        # Create a log group for the Fargate service
        log_group = logs.LogGroup(self, "HeatDashLogGroup",
            log_group_name="/ecs/heat-dash-streamlit-sandbox",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_WEEK
        )

        # Create the Fargate service with ALB
        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "HeatDashFargateService",
            cluster=cluster,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=image,
                container_port=8501,
                environment={
                    "CLOUDFRONT_URL": f"https://{distribution.distribution_domain_name}"
                },
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="HeatDashStreamlit",
                    log_group=log_group
                ),
            ),
            desired_count=2,
            # cpu=4096,
            # memory_limit_mib=8192,
            cpu=16384,  # This corresponds to 16 vCPU (maximum)
            memory_limit_mib=122880,
            public_load_balancer=True,
            certificate=certificate,
            domain_name=fqdn,
            domain_zone=hosted_zone,
        )

        # Configure the health check for the target group
        service.target_group.configure_health_check(
            path="/",
            healthy_http_codes="200",
            interval=Duration.seconds(30),
            timeout=Duration.seconds(10),
            healthy_threshold_count=2,
            unhealthy_threshold_count=2,
        )

        # Set up auto-scaling
        scaling = service.service.auto_scale_task_count(max_capacity=24)
        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=50,
            scale_in_cooldown=Duration.seconds(300),
            scale_out_cooldown=Duration.seconds(300),
        )

        # Add memory utilization scaling
        scaling.scale_on_memory_utilization(
            "MemoryScaling",
            target_utilization_percent=50,
            scale_in_cooldown=Duration.seconds(300),
            scale_out_cooldown=Duration.seconds(300),
        )

        # Create a CloudWatch dashboard
        dashboard = cloudwatch.Dashboard(self, "HeatDashDashboard",
            dashboard_name="HeatDashStreamlitDashboard-Sandbox"
        )

        # Create a metric for cluster-level RunningTaskCount using Container Insights
        cluster_running_task_count_metric = cloudwatch.Metric(
            namespace="ECS/ContainerInsights",
            metric_name="TaskCount",
            dimensions_map={
                "ClusterName": cluster.cluster_name
            },
            statistic="Average",
            period=Duration.minutes(1)
        )

        # Add widgets to the dashboard
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="CPU Utilization",
                left=[service.service.metric_cpu_utilization()]
            ),
            cloudwatch.GraphWidget(
                title="Memory Utilization",
                left=[service.service.metric_memory_utilization()]
            ),
            cloudwatch.GraphWidget(
                title="Cluster Running Task Count",
                left=[cluster_running_task_count_metric]
            ),
            cloudwatch.LogQueryWidget(
                title="Application Logs",
                log_group_names=[log_group.log_group_name],
                query_lines=[
                    "fields @timestamp, @message",
                    "sort @timestamp desc",
                    "limit 100"
                ],
                width=24
            )
        )

        # Create CloudWatch alarms for CPU and Memory utilization
        cpu_alarm = cloudwatch.Alarm(self, "CPUUtilizationAlarm",
            metric=service.service.metric_cpu_utilization(),
            threshold=70,
            evaluation_periods=3,
            datapoints_to_alarm=2,
        )

        memory_alarm = cloudwatch.Alarm(self, "MemoryUtilizationAlarm",
            metric=service.service.metric_memory_utilization(),
            threshold=70,
            evaluation_periods=3,
            datapoints_to_alarm=2,
        )

        # Add alarms to dashboard
        dashboard.add_widgets(
            cloudwatch.AlarmWidget(
                title="CPU Utilization Alarm",
                alarm=cpu_alarm
            ),
            cloudwatch.AlarmWidget(
                title="Memory Utilization Alarm",
                alarm=memory_alarm
            )
        )

        # Output the DNS name of the load balancer
        CfnOutput(self, "LoadBalancerDNS", value=service.load_balancer.load_balancer_dns_name)
        # Output the CloudFront distribution URL
        CfnOutput(self, "CloudFrontURL", value=distribution.distribution_domain_name)
        # Output the CloudWatch Dashboard URL
        CfnOutput(self, "DashboardURL", 
                  value=f"https://{self.region}.console.aws.amazon.com/cloudwatch/home?region={self.region}#dashboards:name=HeatDashStreamlitDashboard")
