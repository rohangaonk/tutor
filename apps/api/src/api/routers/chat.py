"""POST /chat — document-scoped RAG with streaming SSE output."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import get_current_user
from api.rag import build_rag_chain, retrieve_context
from common.db import get_db

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

# Build the chain once at import time (LLM client is cached via lru_cache).
_rag_chain = build_rag_chain()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    question: str
    document_id: uuid.UUID


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("", summary="Ask a question against an uploaded document (streaming SSE)")
async def chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    current_user: uuid.UUID = Depends(get_current_user),
) -> StreamingResponse:
    """Answer a question grounded in the specified document.

    The response is streamed as Server-Sent Events (SSE).  Each event carries
    one token.  The final event is ``data: [DONE]``.

    Consume in Python::

        import httpx, sys
        with httpx.stream("POST", "http://localhost:8000/chat",
                          json={"question": "...", "document_id": "...", "user_id": "..."}) as r:
            for line in r.iter_lines():
                if line.startswith("data: "):
                    print(line[6:], end="", flush=True)
    """
    loop = asyncio.get_event_loop()

    # Embedding + retrieval are synchronous/blocking — run off the event loop.
    try:
        context = await loop.run_in_executor(
            None,
            lambda: retrieve_context(body.question, body.document_id, db),
        )
    except Exception as exc:
        logger.error("RAG retrieval error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve document context.",
        ) from exc

    chain_inputs = {"question": body.question, "context": context}

    async def token_generator() -> AsyncGenerator[str, None]:
        try:
            async for token in _rag_chain.astream(chain_inputs):
                if token:
                    yield f"data: {token}\n\n"
        except Exception as exc:
            logger.error("RAG stream error: %s", exc, exc_info=True)
            yield f"data: [ERROR] {exc}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        token_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
