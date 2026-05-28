import aws_cdk as cdk
from aws_cdk import (
    aws_cognito as cognito,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_s3 as s3,
    aws_secretsmanager as sm,
    aws_sqs as sqs,
)
from constructs import Construct


class DataStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, stage: str, vpc: ec2.Vpc, **kwargs):
        super().__init__(scope, id, **kwargs)

        is_prod = stage == "production"

        # ── Security Groups ──────────────────────────────────────────────────
        # RDS SG allows VPC-internal traffic only (isolated subnet + CIDR rule).
        # This avoids cross-stack SG reference cycles.

        self.rds_sg = ec2.SecurityGroup(
            self,
            "RdsSG",
            vpc=vpc,
            security_group_name=f"tutor-rds-{stage}",
            description="RDS Postgres - allows VPC-internal traffic on 5432",
            allow_all_outbound=False,
        )
        self.rds_sg.add_ingress_rule(
            ec2.Peer.ipv4(vpc.vpc_cidr_block),
            ec2.Port.tcp(5432),
            "VPC-internal to Postgres",
        )

        # ── S3 ───────────────────────────────────────────────────────────────

        self.bucket = s3.Bucket(
            self,
            "UploadsBucket",
            bucket_name=f"tutor-uploads-{stage}",
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=cdk.RemovalPolicy.RETAIN if is_prod else cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=not is_prod,
            lifecycle_rules=[
                s3.LifecycleRule(
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=cdk.Duration.days(90),
                        )
                    ]
                )
            ],
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.PUT],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    max_age=3000,
                )
            ],
        )

        # ── SQS ──────────────────────────────────────────────────────────────

        self.dlq = sqs.Queue(
            self,
            "IngestionDLQ",
            queue_name=f"tutor-ingestion-dlq-{stage}",
            retention_period=cdk.Duration.days(14),
        )

        self.queue = sqs.Queue(
            self,
            "IngestionQueue",
            queue_name=f"tutor-ingestion-{stage}",
            visibility_timeout=cdk.Duration.seconds(300),
            retention_period=cdk.Duration.days(14),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=self.dlq,
            ),
        )

        # ── RDS Postgres ──────────────────────────────────────────────────────

        self.db_name = "tutor"

        self.db_instance = rds.DatabaseInstance(
            self,
            "Database",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16,
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3,
                ec2.InstanceSize.MEDIUM if is_prod else ec2.InstanceSize.MICRO,
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[self.rds_sg],
            database_name=self.db_name,
            credentials=rds.Credentials.from_generated_secret("tutor"),
            multi_az=is_prod,
            allocated_storage=20,
            max_allocated_storage=100,
            backup_retention=cdk.Duration.days(0) if not is_prod else cdk.Duration.days(7),
            deletion_protection=is_prod,
            removal_policy=cdk.RemovalPolicy.RETAIN if is_prod else cdk.RemovalPolicy.DESTROY,
            storage_encrypted=True,
            instance_identifier=f"tutor-db-{stage}",
        )
        # The generated secret contains: host, port, username, password, dbname
        self.db_secret = self.db_instance.secret

        # ── Cognito User Pool ─────────────────────────────────────────────────

        self.user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name=f"tutor-{stage}",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_uppercase=False,
                require_digits=False,
                require_symbols=False,
            ),
            removal_policy=cdk.RemovalPolicy.RETAIN if is_prod else cdk.RemovalPolicy.DESTROY,
        )

        self.user_pool_client = self.user_pool.add_client(
            "AppClient",
            user_pool_client_name=f"tutor-{stage}-client",
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True,
            ),
            generate_secret=False,
        )

        # ── LLM API Key Secrets (placeholder — update after first deploy) ──────

        self.groq_secret = sm.Secret(
            self,
            "GroqApiKey",
            secret_name=f"tutor/{stage}/groq-api-key",
            description="Groq API key for LLM inference",
            secret_string_value=cdk.SecretValue.unsafe_plain_text("REPLACE_ME"),
        )

        self.openrouter_secret = sm.Secret(
            self,
            "OpenRouterApiKey",
            secret_name=f"tutor/{stage}/openrouter-api-key",
            description="OpenRouter API key for LLM inference",
            secret_string_value=cdk.SecretValue.unsafe_plain_text("REPLACE_ME"),
        )

        # ── Outputs ───────────────────────────────────────────────────────────

        cdk.CfnOutput(self, "S3BucketName", value=self.bucket.bucket_name)
        cdk.CfnOutput(self, "SqsQueueUrl", value=self.queue.queue_url)
        cdk.CfnOutput(self, "DlqUrl", value=self.dlq.queue_url)
        cdk.CfnOutput(self, "RdsEndpoint", value=self.db_instance.db_instance_endpoint_address)
        cdk.CfnOutput(self, "RdsPort", value=self.db_instance.db_instance_endpoint_port)
        cdk.CfnOutput(self, "CognitoUserPoolId", value=self.user_pool.user_pool_id)
        cdk.CfnOutput(
            self,
            "CognitoClientId",
            value=self.user_pool_client.user_pool_client_id,
        )
        if self.db_secret:
            cdk.CfnOutput(self, "DbSecretArn", value=self.db_secret.secret_arn)
