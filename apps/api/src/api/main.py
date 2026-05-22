from contextlib import asynccontextmanager

import boto3
import psycopg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from api.routers import chat, documents, upload
from api.routers import quiz as quiz_router
from api.quiz.graph import build_quiz_graph
from common.config import settings


def _configure_localstack_cors() -> None:
    """Set a permissive CORS policy on the LocalStack S3 bucket for local dev.

    This allows the browser to PUT directly to presigned S3 URLs on
    localhost:4566 without being blocked by the browser's CORS check.
    Only runs when the bucket name ends with '-local' (local dev convention).
    """
    endpoint_url = settings.aws_endpoint_url
    if endpoint_url is None and settings.s3_bucket.endswith("-local"):
        endpoint_url = "http://localhost:4566"
    if not endpoint_url:
        return
    s3 = boto3.client(
        "s3",
        region_name=settings.aws_region,
        endpoint_url=endpoint_url,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    s3.put_bucket_cors(
        Bucket=settings.s3_bucket,
        CORSConfiguration={
            "CORSRules": [
                {
                    "AllowedHeaders": ["*"],
                    "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
                    "AllowedOrigins": ["*"],
                    "ExposeHeaders": ["ETag"],
                    "MaxAgeSeconds": 3000,
                }
            ]
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_localstack_cors()

    # Initialise LangGraph Postgres checkpointer for quiz state persistence
    conn = await psycopg.AsyncConnection.connect(settings.pg_dsn, autocommit=True)
    checkpointer = AsyncPostgresSaver(conn)
    await checkpointer.setup()
    app.state.quiz_graph = build_quiz_graph(checkpointer)
    app.state._quiz_conn = conn  # keep reference to close on shutdown

    yield

    await conn.close()


app = FastAPI(title="Tutor API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(quiz_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
