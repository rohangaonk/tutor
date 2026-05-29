import os

import aws_cdk as cdk
from aws_cdk import (
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ecr_assets as ecr_assets,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct

from stacks.data_stack import DataStack


class AppStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        stage: str,
        vpc: ec2.Vpc,
        data_stack: DataStack,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        is_prod = stage == "production"

        # ── Docker Image Assets ───────────────────────────────────────────────
        # CDK builds these locally during `cdk deploy` and pushes to a managed
        # ECR repository automatically. Build context is the repo root.

        repo_root = os.path.join(os.path.dirname(__file__), "..", "..")

        api_image = ecs.ContainerImage.from_asset(
            repo_root,
            file="apps/api/Dockerfile",
            platform=ecr_assets.Platform.LINUX_AMD64,
        )

        worker_image = ecs.ContainerImage.from_asset(
            repo_root,
            file="apps/worker/Dockerfile",
            platform=ecr_assets.Platform.LINUX_AMD64,
        )

        # ── ECS Task Security Group ───────────────────────────────────────────
        # Attached to API and Worker tasks. Allows all outbound (for Supabase,
        # Secrets Manager, S3, SQS, Cognito endpoints via NAT Gateway).

        ecs_task_sg = ec2.SecurityGroup(
            self,
            "EcsTaskSG",
            vpc=vpc,
            security_group_name=f"tutor-ecs-{stage}",
            description="Attached to API and Worker Fargate tasks",
            allow_all_outbound=True,
        )

        # ── ECS Cluster ───────────────────────────────────────────────────────

        cluster = ecs.Cluster(
            self,
            "Cluster",
            cluster_name=f"tutor-{stage}",
            vpc=vpc,
            container_insights_v2=ecs.ContainerInsights.ENABLED,
        )

        # ── IAM: Task Execution Role (pulls images, reads secrets) ────────────

        execution_role = iam.Role(
            self,
            "ExecutionRole",
            role_name=f"tutor-ecs-execution-{stage}",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                ),
            ],
        )
        data_stack.supabase_db_secret.grant_read(execution_role)
        data_stack.groq_secret.grant_read(execution_role)
        data_stack.openrouter_secret.grant_read(execution_role)

        # ── IAM: Task Role (application-level AWS permissions) ────────────────

        task_role = iam.Role(
            self,
            "TaskRole",
            role_name=f"tutor-ecs-task-{stage}",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        data_stack.bucket.grant_read_write(task_role)
        data_stack.queue.grant_consume_messages(task_role)
        data_stack.queue.grant_send_messages(task_role)
        data_stack.dlq.grant_consume_messages(task_role)

        # ── CloudWatch Log Groups ─────────────────────────────────────────────

        api_log_group = logs.LogGroup(
            self,
            "ApiLogGroup",
            log_group_name=f"/ecs/tutor-api-{stage}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        worker_log_group = logs.LogGroup(
            self,
            "WorkerLogGroup",
            log_group_name=f"/ecs/tutor-worker-{stage}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # ── Shared environment & secrets injected into every container ─────────
        # Non-sensitive values go as plain env vars; credentials go as ECS secrets
        # (fetched from Secrets Manager at task start, never stored in task def).

        shared_environment = {
            "AWS_REGION": self.region,
            "S3_BUCKET": data_stack.bucket.bucket_name,
            "SQS_QUEUE_URL": data_stack.queue.queue_url,
            "COGNITO_USER_POOL_ID": data_stack.user_pool.user_pool_id,
            "COGNITO_CLIENT_ID": data_stack.user_pool_client.user_pool_client_id,
            "COGNITO_REGION": self.region,
            "LLM_PROVIDER": "groq",
        }

        shared_secrets: dict[str, ecs.Secret] = {
            "DATABASE_URL": ecs.Secret.from_secrets_manager(data_stack.supabase_db_secret),
            "GROQ_API_KEY": ecs.Secret.from_secrets_manager(data_stack.groq_secret),
            "OPENROUTER_API_KEY": ecs.Secret.from_secrets_manager(data_stack.openrouter_secret),
        }

        # ── API Task Definition ───────────────────────────────────────────────

        api_task = ecs.FargateTaskDefinition(
            self,
            "ApiTask",
            family=f"tutor-api-{stage}",
            cpu=512,
            memory_limit_mib=1024,
            execution_role=execution_role,
            task_role=task_role,
        )

        api_container = api_task.add_container(
            "api",
            image=api_image,
            environment=shared_environment,
            secrets=shared_secrets,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="api",
                log_group=api_log_group,
            ),
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\" || exit 1"],
                interval=cdk.Duration.seconds(30),
                timeout=cdk.Duration.seconds(5),
                retries=3,
                start_period=cdk.Duration.seconds(60),
            ),
        )
        api_container.add_port_mappings(ecs.PortMapping(container_port=8000))

        # ── API Fargate Service (behind an ALB) ───────────────────────────────

        api_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "ApiService",
            service_name=f"tutor-api-{stage}",
            cluster=cluster,
            task_definition=api_task,
            public_load_balancer=True,
            desired_count=1,
            security_groups=[ecs_task_sg],
            task_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            listener_port=80,
            open_listener=True,
        )

        api_service.target_group.configure_health_check(
            path="/health",
            interval=cdk.Duration.seconds(30),
            healthy_threshold_count=2,
            unhealthy_threshold_count=3,
        )

        # ── Worker Task Definition ────────────────────────────────────────────

        worker_task = ecs.FargateTaskDefinition(
            self,
            "WorkerTask",
            family=f"tutor-worker-{stage}",
            cpu=512,
            memory_limit_mib=1024,
            execution_role=execution_role,
            task_role=task_role,
        )

        worker_task.add_container(
            "worker",
            image=worker_image,
            environment=shared_environment,
            secrets=shared_secrets,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="worker",
                log_group=worker_log_group,
            ),
        )

        # ── Worker Fargate Service (no public endpoint) ───────────────────────

        ecs.FargateService(
            self,
            "WorkerService",
            service_name=f"tutor-worker-{stage}",
            cluster=cluster,
            task_definition=worker_task,
            desired_count=1,
            security_groups=[ecs_task_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # ── CloudFront distribution (HTTPS termination for the ALB) ──────────

        distribution = cloudfront.Distribution(
            self,
            "ApiCdn",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.HttpOrigin(
                    api_service.load_balancer.load_balancer_dns_name,
                    protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
            ),
        )

        # ── Outputs ───────────────────────────────────────────────────────────

        cdk.CfnOutput(
            self,
            "ApiUrl",
            value=cdk.Fn.join(
                "", ["https://", distribution.distribution_domain_name]
            ),
            description="CloudFront HTTPS URL — use this as NEXT_PUBLIC_API_URL in Vercel",
        )
        cdk.CfnOutput(
            self,
            "AlbUrl",
            value=cdk.Fn.join(
                "", ["http://", api_service.load_balancer.load_balancer_dns_name]
            ),
        )
        cdk.CfnOutput(
            self,
            "EcsClusterName",
            value=cluster.cluster_name,
        )
