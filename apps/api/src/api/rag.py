"""RAG chain: embed question → retrieve chunks → stream LLM answer.

Follows the same pattern as the reference personal-ai project:
  - Groq (primary) for fast chat inference
  - OpenRouter for embeddings (text-embedding-3-small, 768 dims)
  - LangChain for the prompt/chain abstraction and async streaming
"""

from __future__ import annotations

import uuid
from functools import lru_cache

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from openai import OpenAI
from sqlalchemy.orm import Session

from common.config import MODEL_REGISTRY, settings
from common.retrieval import retrieve_chunks

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

EMBEDDING_DIMENSIONS = 768

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_RAG_SYSTEM = """\
You are a precise tutor assistant that answers questions strictly from the \
provided document context.

Rules:
1. Base your answer ONLY on the context below — do not use prior knowledge.
2. Be clear, concise, and educational.
3. If the context does not contain enough information to answer, say \
"I don't have enough context in this document to answer that."

Context:
{context}"""

_RAG_HUMAN = "Question: {question}"

# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


@lru_cache(maxsize=4)
def _get_llm(use_case: str = "rag", temperature: float = 0.0) -> ChatOpenAI:
    """Return a cached, streaming-capable LLM for the given use-case.

    Tries Groq first (low-latency); falls back to OpenRouter when
    GROQ_API_KEY is not configured.
    """
    provider = settings.llm_provider
    model = MODEL_REGISTRY[use_case][provider]

    if provider == "groq" and settings.groq_api_key:
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=settings.groq_api_key,
            base_url=GROQ_BASE_URL,
            streaming=True,
        )

    # Fallback to OpenRouter
    return ChatOpenAI(
        model=MODEL_REGISTRY[use_case]["openrouter"],
        temperature=temperature,
        api_key=settings.openrouter_api_key,
        base_url=OPENROUTER_BASE_URL,
        streaming=True,
    )


# ---------------------------------------------------------------------------
# Embeddings (OpenRouter, same as the ingestion worker)
# ---------------------------------------------------------------------------


def _embed_query(question: str) -> list[float]:
    """Embed a single query string using the same model/dimensions as ingestion."""
    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=settings.openrouter_api_key,
    )
    model = MODEL_REGISTRY["embeddings"]["openrouter"]
    response = client.embeddings.create(
        model=model,
        input=[question],
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return response.data[0].embedding


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------


def _format_chunks(chunks) -> str:
    """Format retrieved chunks into a numbered context block."""
    if not chunks:
        return "(No relevant content found in the document.)"
    return "\n\n".join(f"[{i + 1}] {c.content}" for i, c in enumerate(chunks))


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def retrieve_context(
    question: str,
    doc_id: uuid.UUID,
    db: Session,
    k: int = 5,
) -> str:
    """Embed the question and retrieve the top-k chunks from the document.

    This is synchronous (blocking) and should be called via run_in_executor
    from an async FastAPI handler.

    Returns a formatted context string ready for the prompt.
    """
    query_embedding = _embed_query(question)
    chunks = retrieve_chunks(doc_id, query_embedding, k=k, db=db)
    return _format_chunks(chunks)


def build_rag_chain() -> Runnable:
    """Build the reusable RAG chain: prompt | llm | parser."""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _RAG_SYSTEM),
            ("human", _RAG_HUMAN),
        ]
    )
    llm = _get_llm("rag", temperature=0.0)
    return prompt | llm | StrOutputParser()
