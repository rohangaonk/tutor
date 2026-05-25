"""Quiz engine REST endpoints.

POST /quiz/start  — create session + return first question (graph runs to first interrupt)
POST /quiz/answer — resume graph with user's answer, return feedback + next question or completion
GET  /quiz/{session_id}/report — SQL-aggregated per-concept accuracy summary
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.deps import get_current_user
from common.db import get_db
from common.models import Document, QuizAttempt, QuizSession

router = APIRouter(prefix="/quiz", tags=["quiz"])

# ── Request / Response schemas ────────────────────────────────────────────────

class StartRequest(BaseModel):
    doc_id: str
    max_questions: int = 5


class StartResponse(BaseModel):
    session_id: str
    question: str
    concept: str
    difficulty: str


class AnswerRequest(BaseModel):
    session_id: str
    answer: str


class AnswerResponse(BaseModel):
    feedback: str
    correct_answer: str
    confidence_score: float
    is_correct: bool
    next_question: str | None
    next_concept: str | None
    difficulty: str
    is_completed: bool


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_graph(request: Request):
    graph = getattr(request.app.state, "quiz_graph", None)
    if graph is None:
        raise HTTPException(status_code=503, detail="Quiz graph not initialized")
    return graph


def _get_state_value(snapshot, key: str, default: Any = None) -> Any:
    """Extract a value from a LangGraph snapshot regardless of SDK version."""
    values = snapshot.values if hasattr(snapshot, "values") else {}
    return values.get(key, default)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/start", response_model=StartResponse)
def start_quiz(
    body: StartRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: uuid.UUID = Depends(get_current_user),
):
    graph = _get_graph(request)
    session_id = str(uuid.uuid4())

    # Persist the session row up-front
    session = QuizSession(
        id=uuid.UUID(session_id),
        user_id=current_user,
        doc_id=uuid.UUID(body.doc_id),
        state_json={},
    )
    db.add(session)
    db.commit()

    # Load predefined topics from the document (may be None for legacy docs)
    doc = db.get(Document, uuid.UUID(body.doc_id))
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    document_topics: list[str] = doc.topics or []

    initial_state = {
        "doc_id": body.doc_id,
        "user_id": str(current_user),
        "session_id": session_id,
        "max_questions": body.max_questions,
        "document_topics": document_topics,
        "questions_asked": 0,
        "difficulty": "medium",
        "total_score": 0.0,
        "weak_areas": [],
        "is_completed": False,
        "asked_concepts": [],
        "asked_question_embeddings": [],
        "retry_count": 0,
        "retrieved_context": "",
        "current_topic": "",
        "current_question": "",
        "current_concept": "",
        "current_question_embedding": [],
        "user_answer": "",
        "ai_feedback": "",
        "correct_answer": "",
        "confidence_score": 0.0,
        "is_correct": False,
    }

    config = {"configurable": {"thread_id": session_id}}
    # Run until the first interrupt (before evaluate_answer)
    graph.invoke(initial_state, config=config)

    snapshot = graph.get_state(config)
    question = _get_state_value(snapshot, "current_question", "")
    concept = _get_state_value(snapshot, "current_concept", "")
    difficulty = _get_state_value(snapshot, "difficulty", "medium")

    if not question:
        raise HTTPException(status_code=500, detail="Graph did not produce a question")

    return StartResponse(
        session_id=session_id,
        question=question,
        concept=concept,
        difficulty=difficulty,
    )


@router.post("/answer", response_model=AnswerResponse)
def submit_answer(
    body: AnswerRequest,
    request: Request,
):
    graph = _get_graph(request)
    config = {"configurable": {"thread_id": body.session_id}}

    # Inject the user's answer into the paused state
    graph.update_state(config, {"user_answer": body.answer})

    # Resume — runs evaluate_answer → adapt_difficulty → persist_attempt
    # then either stops at next interrupt (more questions) or reaches END
    graph.invoke(None, config=config)

    snapshot = graph.get_state(config)
    is_completed = _get_state_value(snapshot, "is_completed", False)
    feedback = _get_state_value(snapshot, "ai_feedback", "")
    correct_answer = _get_state_value(snapshot, "correct_answer", "")
    confidence = float(_get_state_value(snapshot, "confidence_score", 0.0))
    is_correct = bool(_get_state_value(snapshot, "is_correct", False))
    difficulty = _get_state_value(snapshot, "difficulty", "medium")

    if is_completed:
        return AnswerResponse(
            feedback=feedback,
            correct_answer=correct_answer,
            confidence_score=confidence,
            is_correct=is_correct,
            next_question=None,
            next_concept=None,
            difficulty=difficulty,
            is_completed=True,
        )

    next_question = _get_state_value(snapshot, "current_question")
    next_concept = _get_state_value(snapshot, "current_concept")

    return AnswerResponse(
        feedback=feedback,
        correct_answer=correct_answer,
        confidence_score=confidence,
        is_correct=is_correct,
        next_question=next_question,
        next_concept=next_concept,
        difficulty=difficulty,
        is_completed=False,
    )


@router.get("/sessions")
def list_sessions(
    db: Session = Depends(get_db),
    current_user: uuid.UUID = Depends(get_current_user),
):
    """Return completed quiz sessions for the current user, newest first."""
    sessions = (
        db.query(QuizSession)
        .filter(QuizSession.user_id == current_user)
        .order_by(QuizSession.created_at.desc())
        .all()
    )

    result = []
    for s in sessions:
        completed = bool((s.state_json or {}).get("completed", False))
        doc = db.get(Document, s.doc_id)
        result.append({
            "session_id": str(s.id),
            "doc_id": str(s.doc_id),
            "doc_name": doc.name if doc else "Unknown",
            "created_at": s.created_at.isoformat(),
            "score": round(s.score, 3),
            "questions_asked": s.state_json.get("questions_asked", 0) if s.state_json else 0,
            "completed": completed,
        })

    return result


@router.get("/{session_id}/attempts")
def get_attempts(session_id: str, db: Session = Depends(get_db)):
    """Return individual Q&A attempts for a session, in creation order."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    attempts = (
        db.query(QuizAttempt)
        .filter(QuizAttempt.session_id == sid)
        .order_by(QuizAttempt.created_at)
        .all()
    )

    return [
        {
            "id": str(a.id),
            "question": a.question,
            "user_answer": a.answer,
            "correct": a.correct,
            "concept": a.concept,
            "ai_feedback": a.ai_feedback,
            "confidence_score": a.confidence_score,
            "difficulty_level": a.difficulty_level,
        }
        for a in attempts
    ]


@router.get("/{session_id}/report")
def get_report(
    session_id: str,
    db: Session = Depends(get_db),
):
    """Return per-concept accuracy for the session (pure SQL, no vectorisation)."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    rows = (
        db.query(
            QuizAttempt.concept,
            func.count(QuizAttempt.id).label("total"),
            func.count(QuizAttempt.id).filter(QuizAttempt.correct.is_(True)).label("correct_count"),
            func.avg(QuizAttempt.confidence_score).label("avg_confidence"),
        )
        .filter(QuizAttempt.session_id == sid)
        .group_by(QuizAttempt.concept)
        .all()
    )

    return {
        "session_id": session_id,
        "concepts": [
            {
                "concept": row.concept,
                "total": row.total,
                "correct": int(row.correct_count or 0),
                "accuracy": round((row.correct_count or 0) / row.total, 2),
                "avg_confidence": round(float(row.avg_confidence or 0), 3),
            }
            for row in rows
        ],
    }
