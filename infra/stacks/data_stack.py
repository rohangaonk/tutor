import aws_cdk as cdk
from aws_cdk import (
    aws_cognito as cognito,
    aws_s3 as s3,
    aws_secretsmanager as sm,
    aws_sqs as sqs,
)
from constructs import Construct


class DataStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, stage: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        is_prod = stage == "production"

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

        # ── Supabase Database URL ──────────────────────────────────────────
        # Store the Supabase connection string in Secrets Manager.
        # After first deploy, update with the real URL from the Supabase dashboard:
        #   aws secretsmanager put-secret-value \
        #     --secret-id tutor/{stage}/supabase-database-url \
        #     --secret-string 'postgresql+psycopg2://...' \
        #     --profile tutor-deploy

        self.supabase_db_secret = sm.Secret(
            self,
            "SupabaseDbUrl",
            secret_name=f"tutor/{stage}/supabase-database-url",
            description="Supabase PostgreSQL connection URL",
            secret_string_value=cdk.SecretValue.unsafe_plain_text("REPLACE_ME"),
        )

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
        cdk.CfnOutput(self, "SupabaseDbSecretArn", value=self.supabase_db_secret.secret_arn)
        cdk.CfnOutput(self, "CognitoUserPoolId", value=self.user_pool.user_pool_id)
        cdk.CfnOutput(
            self,
            "CognitoClientId",
            value=self.user_pool_client.user_pool_client_id,
        )
