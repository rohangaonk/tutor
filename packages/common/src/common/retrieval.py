"""Document-scoped vector similarity retrieval using pgvector."""

import uuid

from sqlalchemy.orm import Session

from common.models import Chunk


def retrieve_chunks(
    doc_id: uuid.UUID,
    query_embedding: list[float],
    k: int = 5,
    db: Session = None,
) -> list[Chunk]:
    """Return the k most similar chunks for the given document.

    Uses cosine distance (<=>) against the stored 768-dim embeddings.
    Results are scoped to a single document so the answer is grounded
    in the user's uploaded content.
    """
    results = (
        db.query(Chunk)
        .filter(Chunk.doc_id == doc_id)
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(k)
        .all()
    )
    return results
