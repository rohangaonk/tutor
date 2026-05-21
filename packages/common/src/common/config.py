from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg2://tutor:tutor@localhost:5434/tutor"

    # Redis / Celery broker
    redis_url: str = "redis://localhost:6379/0"

    # AWS / LocalStack
    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None  # set to http://localhost:4566 locally
    s3_bucket: str = "tutor-uploads-local"
    sqs_queue_url: str = "http://localhost:4566/000000000000/tutor-ingestion-local"

    # OpenAI / embeddings
    openai_api_key: str = ""

    # Anthropic
    anthropic_api_key: str = ""


settings = Settings()

