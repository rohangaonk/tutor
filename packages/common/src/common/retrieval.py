"""Document-scoped vector similarity retrieval using pgvector."""

import uuid

import numpy as np
from sqlalchemy.orm import Session

from common.models import Chunk


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom > 1e-8 else 0.0


def retrieve_chunks(
    doc_id: uuid.UUID,
    query_embedding: list[float],
    k: int = 5,
    db: Session = None,
) -> list[Chunk]:
    """Return the k most similar chunks for the given document (cosine distance)."""
    return (
        db.query(Chunk)
        .filter(Chunk.doc_id == doc_id)
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(k)
        .all()
    )


def retrieve_chunks_mmr(
    doc_id: uuid.UUID,
    query_embedding: list[float],
    k: int = 5,
    fetch_k: int = 20,
    lambda_mult: float = 0.6,
    db: Session = None,
) -> list[Chunk]:
    """MMR (Maximal Marginal Relevance) retrieval — balances relevance and diversity.

    Fetches ``fetch_k`` candidates by cosine similarity then re-ranks them so
    successive selections are both relevant to the query AND dissimilar to each
    other.  This prevents the quiz from receiving near-duplicate chunks that
    would produce repeated questions.

    Args:
        lambda_mult: 1.0 = pure relevance, 0.0 = pure diversity. 0.6 leans
                     slightly toward relevance, as recommended in the design doc.
    """
    candidates = (
        db.query(Chunk)
        .filter(Chunk.doc_id == doc_id)
        .filter(Chunk.embedding.isnot(None))
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(fetch_k)
        .all()
    )

    if len(candidates) <= k:
        return candidates

    selected: list[Chunk] = []
    remaining = list(candidates)

    while len(selected) < k and remaining:
        if not selected:
            selected.append(remaining.pop(0))
            continue

        best_score = -float("inf")
        best_idx = 0

        for i, chunk in enumerate(remaining):
            relevance = _cosine_similarity(chunk.embedding, query_embedding)
            max_sim = max(
                _cosine_similarity(chunk.embedding, s.embedding) for s in selected
            )
            score = lambda_mult * relevance - (1 - lambda_mult) * max_sim
            if score > best_score:
                best_score = score
                best_idx = i

        selected.append(remaining.pop(best_idx))

    return selected

