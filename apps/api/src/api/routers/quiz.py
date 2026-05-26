"""Quiz engine REST endpoints.

POST /quiz/start  — create session + return first question (graph runs to first interrupt)
POST /quiz/answer — resume graph with user's answer, return feedback + next question or completion
GET  /quiz/{session_id}/report — SQL-aggregated per-concept accuracy summary
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.deps import get_current_user
from common.db import get_db, SessionLocal
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


class SkipRequest(BaseModel):
    session_id: str
    questions_asked: int  # client's current count, used to detect if backend already advanced


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
    # Shuffle topics so each session presents questions in a different order.
    document_topics: list[str] = list(doc.topics or [])
    random.shuffle(document_topics)

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
        "_asked_questions": [],
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
        "is_skipped": False,
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


@router.post("/skip", response_model=AnswerResponse)
async def skip_question(body: SkipRequest, request: Request):
    """Skip the current question.

    Two scenarios:
    A) Graph is paused at interrupt (user skips before/without submitting, OR backend
       already completed the previous answer cycle quickly).
    B) Graph is still running (user submitted, 7s passed, user chose to skip —
       the backend answer request is still processing in a threadpool).

    For (A) where questions_asked already advanced: the backend finished the full
    cycle and the next question is ready — mark the just-persisted attempt as
    skipped in the DB and return the already-generated question.

    For (A) where questions_asked matches the client: skip evaluation cleanly by
    injecting is_skipped=True and running the graph to the next interrupt.

    For (B): wait up to 60 s for the graph to reach the next interrupt, then
    retroactively mark the last attempt as skipped and return the question.
    """
    graph = _get_graph(request)
    config = {"configurable": {"thread_id": body.session_id}}

    snapshot = await graph.aget_state(config)
    at_interrupt = tuple(snapshot.next) == ("evaluate_answer",)
    is_done = not snapshot.next  # empty → session finished
    questions_in_state = _get_state_value(snapshot, "questions_asked", 0)

    logger.info(
        "[SKIP] session=%s client_q=%d state_q=%d snapshot.next=%s at_interrupt=%s is_done=%s",
        body.session_id, body.questions_asked, questions_in_state,
        list(snapshot.next), at_interrupt, is_done,
    )

    if is_done:
        # Session already complete
        return AnswerResponse(
            feedback="Session complete.",
            correct_answer="",
            confidence_score=0.0,
            is_correct=False,
            next_question=None,
            next_concept=None,
            difficulty=_get_state_value(snapshot, "difficulty", "medium"),
            is_completed=True,
        )

    if at_interrupt and questions_in_state > body.questions_asked:
        logger.info("[SKIP] branch=retroactive (backend already advanced)")
        # Backend already completed the full cycle (evaluated + generated next Q).
        # Retroactively mark the last persisted attempt as skipped.
        db = SessionLocal()
        try:
            last_attempt = (
                db.query(QuizAttempt)
                .filter(QuizAttempt.session_id == uuid.UUID(body.session_id))
                .order_by(QuizAttempt.created_at.desc())
                .first()
            )
            if last_attempt and not last_attempt.is_skipped:
                last_attempt.is_skipped = True
                db.commit()
        finally:
            db.close()
        # The next question is already in the snapshot
        return AnswerResponse(
            feedback="Question skipped.",
            correct_answer="",
            confidence_score=0.0,
            is_correct=False,
            next_question=_get_state_value(snapshot, "current_question"),
            next_concept=_get_state_value(snapshot, "current_concept"),
            difficulty=_get_state_value(snapshot, "difficulty", "medium"),
            is_completed=False,
        )

    if at_interrupt:
        logger.info("[SKIP] branch=clean (graph at interrupt, same question)")
        # Graph is paused at the current question's interrupt — skip cleanly.
        await graph.aupdate_state(config, {"is_skipped": True, "user_answer": "[skipped]"})
        logger.info("[SKIP] injected is_skipped=True, invoking graph...")
        await asyncio.wait_for(graph.ainvoke(None, config=config), timeout=60.0)
        logger.info("[SKIP] graph invoke complete")
    else:
        logger.info("[SKIP] branch=mid-run (waiting for graph to finish)")
        # Graph is mid-run (processing a submitted answer in a threadpool).
        # Wait for it to reach the next interrupt (up to 60 s).
        for _ in range(30):
            await asyncio.sleep(2)
            snapshot = await graph.aget_state(config)
            if tuple(snapshot.next) in (("evaluate_answer",), ()) or not snapshot.next:
                break
        # Retroactively mark the last persisted attempt as skipped.
        db = SessionLocal()
        try:
            last_attempt = (
                db.query(QuizAttempt)
                .filter(QuizAttempt.session_id == uuid.UUID(body.session_id))
                .order_by(QuizAttempt.created_at.desc())
                .first()
            )
            if last_attempt and not last_attempt.is_skipped:
                last_attempt.is_skipped = True
                db.commit()
        finally:
            db.close()

    final_snapshot = await graph.aget_state(config)
    is_completed = _get_state_value(final_snapshot, "is_completed", False)
    next_question = _get_state_value(final_snapshot, "current_question")
    next_concept = _get_state_value(final_snapshot, "current_concept")
    difficulty = _get_state_value(final_snapshot, "difficulty", "medium")

    logger.info(
        "[SKIP] final: is_completed=%s next_question=%r next_concept=%r final.next=%s",
        is_completed, next_question, next_concept, list(final_snapshot.next),
    )

    return AnswerResponse(
        feedback="Question skipped.",
        correct_answer="",
        confidence_score=0.0,
        is_correct=False,
        next_question=next_question if not is_completed else None,
        next_concept=next_concept if not is_completed else None,
        difficulty=difficulty,
        is_completed=is_completed,
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
        .filter(QuizAttempt.is_skipped.is_(False))
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
        .filter(QuizAttempt.is_skipped.is_(False))
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
