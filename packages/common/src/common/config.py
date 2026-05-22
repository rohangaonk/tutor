from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Model registry — maps task type → provider → model name
# ---------------------------------------------------------------------------
MODEL_REGISTRY: dict[str, dict[str, str | None]] = {
    # RAG / document Q&A — benefits from large context window
    "rag": {
        "groq": "meta-llama/llama-4-scout-17b-16e-instruct",
        "openrouter": "openai/gpt-3.5-turbo",
    },
    # Socratic quiz — needs reliable structured JSON-schema output
    "quiz": {
        "groq": "meta-llama/llama-4-scout-17b-16e-instruct",
        "openrouter": "openai/gpt-4o-mini",
    },
    # Progress / weakness report
    "progress": {
        "groq": "meta-llama/llama-4-scout-17b-16e-instruct",
        "openrouter": "openai/gpt-4o-mini",
    },
    # Embeddings — vector representations for RAG/vector search
    "embeddings": {
        "groq": None,  # Groq doesn't offer embeddings
        "openrouter": "text-embedding-3-small",
    },
}


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

    # LLM providers
    llm_provider: str = "groq"  # primary provider: "groq" or "openrouter"
    groq_api_key: str = ""
    openrouter_api_key: str = ""

    @property
    def pg_dsn(self) -> str:
        """psycopg3-compatible DSN (strips SQLAlchemy driver prefix)."""
        return (
            self.database_url
            .replace("postgresql+psycopg2://", "postgresql://")
            .replace("postgresql+psycopg://", "postgresql://")
        )


settings = Settings()

