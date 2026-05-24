"""GET /progress/{user_id} — learner progress across all documents."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from common.db import get_db
from common.models import Document, Progress, QuizSession

router = APIRouter(prefix="/progress", tags=["progress"])


class TopicStrength(BaseModel):
    topic: str
    strength_score: float
    updated_at: datetime


class DocumentProgress(BaseModel):
    doc_id: uuid.UUID
    doc_name: str
    sessions_completed: int
    avg_session_score: float
    topics: list[TopicStrength]


class ProgressResponse(BaseModel):
    user_id: uuid.UUID
    documents: list[DocumentProgress]
    overall_strength: float


@router.get("/{user_id}", response_model=ProgressResponse)
def get_progress(user_id: uuid.UUID, db: Session = Depends(get_db)):
    progress_rows = (
        db.query(Progress)
        .filter(Progress.user_id == user_id)
        .order_by(Progress.doc_id, Progress.topic)
        .all()
    )

    # Group by doc_id
    doc_map: dict[uuid.UUID, list[Progress]] = {}
    for row in progress_rows:
        doc_map.setdefault(row.doc_id, []).append(row)

    # Fetch completed sessions grouped by doc
    sessions = (
        db.query(QuizSession)
        .filter(
            QuizSession.user_id == user_id,
            QuizSession.state_json["completed"].as_boolean() == True,  # noqa: E712
        )
        .all()
    )
    session_counts: dict[uuid.UUID, list[float]] = {}
    for s in sessions:
        session_counts.setdefault(s.doc_id, []).append(s.score)

    documents: list[DocumentProgress] = []
    all_strengths: list[float] = []

    for doc_id, rows in doc_map.items():
        doc = db.get(Document, doc_id)
        if doc is None:
            continue

        topics = [
            TopicStrength(topic=r.topic, strength_score=r.strength_score, updated_at=r.updated_at)
            for r in rows
        ]
        scores = session_counts.get(doc_id, [])
        avg_score = round(sum(scores) / len(scores), 4) if scores else 0.0
        all_strengths.extend(r.strength_score for r in rows)

        documents.append(
            DocumentProgress(
                doc_id=doc_id,
                doc_name=doc.name,
                sessions_completed=len(scores),
                avg_session_score=avg_score,
                topics=topics,
            )
        )

    overall = round(sum(all_strengths) / len(all_strengths), 4) if all_strengths else 0.0

    return ProgressResponse(user_id=user_id, documents=documents, overall_strength=overall)
