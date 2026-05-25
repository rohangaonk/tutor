import io
import json
import logging
import re
import uuid
from typing import Iterator

import boto3
from docx import Document as DocxDocument
from openai import OpenAI
from pypdf import PdfReader

from common.config import MODEL_REGISTRY, settings
from common.db import SessionLocal
from common.models import Chunk, Document, DocumentStatus
from worker.celery_app import app

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1000       # characters
CHUNK_OVERLAP = 150     # characters
EMBEDDING_DIMENSIONS = 768


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------

def _s3_client():
    endpoint_url = settings.aws_endpoint_url
    if endpoint_url is None and settings.s3_bucket.endswith("-local"):
        endpoint_url = "http://localhost:4566"
    kwargs: dict = {
        "region_name": settings.aws_region,
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test",
    }
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return boto3.client("s3", **kwargs)


def _download_bytes(s3_key: str) -> bytes:
    s3 = _s3_client()
    buf = io.BytesIO()
    s3.download_fileobj(settings.s3_bucket, s3_key, buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _extract_text(data: bytes, filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if lower.endswith(".docx"):
        doc = DocxDocument(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    raise ValueError(f"Unsupported file type: {filename}")


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _chunk_text(text: str) -> Iterator[str]:
    """Yield fixed-size overlapping character chunks."""
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        yield text[start:end]
        start += CHUNK_SIZE - CHUNK_OVERLAP


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

def _embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts via OpenRouter (OpenAI-compatible)."""
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
    )
    model = MODEL_REGISTRY["embeddings"]["openrouter"]
    response = client.embeddings.create(
        model=model,
        input=texts,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return [item.embedding for item in response.data]


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

EMBED_BATCH_SIZE = 32

_TOPICS_PROMPT = """\
You are an expert educator. Given the following representative excerpts from one document,
identify exactly {topic_count} distinct, high-level topics or concepts covered in the document.

These topics will be used as fixed categories for quiz questions and progress tracking, so they must be:
- Specific enough to be meaningful (not "introduction" or "summary")
- Broad enough that multiple quiz questions can be asked about each
- Consistent and canonical (they will be reused across all quiz sessions)
- Mutually distinct (avoid near-duplicates)

Respond with valid JSON only — no markdown fences:
{{"topics": ["Topic 1", "Topic 2", "Topic 3", ...]}}

Representative document excerpts:
{excerpt}"""


def _target_topic_count(chunks: list[str]) -> int:
    """Pick topic count from document structure and lexical diversity.

    - Base count scales with chunk count.
    - A diversity adjustment nudges the count up/down for richer or narrower vocab.
    """
    if not chunks:
        return 2

    # Keep tiny documents focused so topic buckets are not artificially fragmented.
    if len(chunks) <= 3:
        return 2
    if len(chunks) <= 6:
        return 3

    base = max(4, min(14, round(len(chunks) / 6)))

    # Use a small chunk sample so this stays cheap for large documents.
    sampled = " ".join(chunks[: min(20, len(chunks))]).lower()
    tokens = re.findall(r"[a-z]{4,}", sampled)
    if not tokens:
        return base

    unique_ratio = len(set(tokens)) / len(tokens)
    if unique_ratio > 0.45:
        base += 1
    elif unique_ratio < 0.25:
        base -= 1

    return max(4, min(14, base))


def _build_representative_excerpt(chunks: list[str], max_slices: int = 10) -> str:
    """Sample chunks across the whole document to represent beginning, middle, and end."""
    if not chunks:
        return ""
    if len(chunks) <= max_slices:
        return "\n\n---\n\n".join(chunks)

    step = len(chunks) / max_slices
    sampled: list[str] = []
    for i in range(max_slices):
        idx = min(len(chunks) - 1, int(round(i * step)))
        piece = chunks[idx].strip()
        if piece:
            sampled.append(piece)
    return "\n\n---\n\n".join(sampled)


def _extract_topics(chunks: list[str]) -> list[str]:
    """Use an LLM to derive canonical topics from representative chunks."""
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
    )
    model = MODEL_REGISTRY["rag"]["openrouter"]
    topic_count = _target_topic_count(chunks)
    excerpt = _build_representative_excerpt(chunks)
    prompt = _TOPICS_PROMPT.format(topic_count=topic_count, excerpt=excerpt)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    raw = response.choices[0].message.content or ""
    raw = raw.strip()
    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("No JSON found in topics response")
    parsed = json.loads(match.group())
    topics = parsed.get("topics", [])
    cleaned: list[str] = []
    seen: set[str] = set()
    for topic in topics:
        value = str(topic).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(value)
    return cleaned


@app.task(name="worker.tasks.ingest_document", bind=True, max_retries=3, default_retry_delay=30)
def ingest_document(self, document_id: str) -> None:
    """Download, parse, chunk, embed, and persist a document."""
    doc_uuid = uuid.UUID(document_id)
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_uuid)
        if doc is None:
            logger.error("ingest_document: document %s not found", document_id)
            return

        doc.status = DocumentStatus.processing
        db.commit()
        logger.info("ingest_document: %s — downloading from S3 key %s", document_id, doc.s3_key)

        data = _download_bytes(doc.s3_key)
        text = _extract_text(data, doc.name)
        logger.info("ingest_document: %s — extracted %d chars", document_id, len(text))

        chunks = list(_chunk_text(text))
        logger.info("ingest_document: %s — %d chunks", document_id, len(chunks))

        # Derive canonical topics from representative chunks so they are stored on the document
        try:
            topics = _extract_topics(chunks)
            doc.topics = topics
            db.commit()
            logger.info("ingest_document: %s — extracted %d topics: %s", document_id, len(topics), topics)
        except Exception as topic_exc:
            logger.warning("ingest_document: %s — topic extraction failed (%s), continuing without topics", document_id, topic_exc)

        # Embed in batches
        embeddings: list[list[float]] = []
        for i in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[i : i + EMBED_BATCH_SIZE]
            embeddings.extend(_embed(batch))
            logger.info("ingest_document: %s — embedded chunks %d–%d", document_id, i, i + len(batch))
        # Persist chunks
        for content, embedding in zip(chunks, embeddings):
            db.add(Chunk(
                doc_id=doc_uuid,
                content=content,
                metadata_={},
                embedding=embedding,
            ))
        doc.status = DocumentStatus.ready
        db.commit()
        logger.info("ingest_document: %s — done, %d chunks persisted", document_id, len(chunks))

    except Exception as exc:
        db.rollback()
        doc = db.get(Document, doc_uuid)
        if doc:
            doc.status = DocumentStatus.failed
            db.commit()
        logger.exception("ingest_document: %s — failed", document_id)
        raise self.retry(exc=exc)
    finally:
        db.close()
