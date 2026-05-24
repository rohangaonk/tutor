"""LangGraph nodes for the quiz engine.

Node flow (interrupted before evaluate_answer):

    retrieve_context → generate_question
                            ↓ too similar (retry < 3)
                            └──────────────── retrieve_context
                            ↓ unique / max retries
                       [INTERRUPT BEFORE evaluate_answer]
                       evaluate_answer → adapt_difficulty → persist_attempt
                                                                  ↓
                                           questions_asked < max? → retrieve_context
                                           else                  → END
"""

from __future__ import annotations

import json
import logging
import random
import re
import uuid

import numpy as np

from common.db import SessionLocal
from common.models import Chunk, Progress, QuizAttempt, QuizSession
from api.rag import _embed_query, _get_llm
from api.quiz.state import QuizState

logger = logging.getLogger(__name__)

# ── Thresholds ───────────────────────────────────────────────────────────────

SIMILARITY_THRESHOLD = 0.92     # reject question if cosine sim > this
MAX_RETRIES = 3                 # max MMR retries per question cycle

DIFFICULTY_UP_THRESHOLD = 0.75  # promote difficulty when score exceeds this
DIFFICULTY_DOWN_THRESHOLD = 0.40  # demote difficulty when score is below this

DIFFICULTY_LADDER = ["easy", "medium", "hard"]

# ── Prompt templates ─────────────────────────────────────────────────────────

_GENERATE_PROMPT = """\
You are a quiz question generator for a tutoring system.

Document context:
{context}

Difficulty: {difficulty}
Already covered concepts (do NOT generate a question on any of these): {asked_concepts}

Generate ONE {difficulty}-level question that:
1. Can be answered from the context above only.
2. Tests a DIFFERENT concept from the already-covered list.
3. Has a clear, unambiguous answer.
4. Explores a unique angle — vary the style (definition, application, comparison, cause-effect, example).

Respond with valid JSON only — no markdown fences:
{{"question": "<your question>", "concept": "<short topic tag, 1-4 words>"}}"""

_EVALUATE_PROMPT = """\
You are evaluating a student's answer to a quiz question.

Question: {question}
Reference context: {context}
Student's answer: {user_answer}

Respond with valid JSON only — no markdown fences:
{{"feedback": "<2-4 sentences evaluating the student's response>", "correct_answer": "<the correct answer extracted from the context, 1-3 sentences>", "confidence_score": <0.0-1.0>, "is_correct": <true|false>}}

confidence_score guide: 1.0 = perfect, 0.7 = mostly correct, 0.4 = partial, 0.0 = wrong."""

# ── Helpers ───────────────────────────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom > 1e-8 else 0.0


def _is_too_similar(
    candidate: list[float],
    past: list[list[float]],
    threshold: float = SIMILARITY_THRESHOLD,
) -> bool:
    return any(_cosine_similarity(candidate, p) > threshold for p in past)


def _parse_json(text: str) -> dict:
    """Extract the first JSON object from an LLM response."""
    text = text.strip()
    # Strip markdown fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in LLM response: {text[:200]}")
    return json.loads(match.group())


def _call_llm_generate(prompt: str) -> str:
    """High temperature for creative, varied question generation."""
    llm = _get_llm("rag", temperature=0.9)
    return llm.invoke(prompt).content


def _call_llm_evaluate(prompt: str) -> str:
    """Low temperature for consistent, factual answer evaluation."""
    llm = _get_llm("rag", temperature=0.1)
    return llm.invoke(prompt).content


# ── Nodes ─────────────────────────────────────────────────────────────────────

def retrieve_context(state: QuizState) -> dict:
    """Random-seeded chunk selection + MMR re-ranking for diversity across sessions.

    Uses the session_id + questions_asked as an RNG seed so:
    - Different sessions → different chunk pools → different questions
    - Within a session, each round picks a fresh random slice
    """
    doc_id = uuid.UUID(state["doc_id"])

    db = SessionLocal()
    try:
        all_chunks = (
            db.query(Chunk)
            .filter(Chunk.doc_id == doc_id)
            .filter(Chunk.embedding.isnot(None))
            .all()
        )

        if not all_chunks:
            return {"retrieved_context": "", "retry_count": 0}

        # Seed with session_id + round so every quiz + every question gets a
        # different starting pool while remaining deterministic for retries.
        rng = random.Random(state["session_id"] + str(state["questions_asked"]))
        fetch_k = min(20, len(all_chunks))
        candidates = rng.sample(all_chunks, fetch_k)

        # MMR re-rank the random pool for intra-session diversity.
        # Use a generic embedding so we're not biased toward any topic.
        seed = "key facts and concepts"
        query_embedding = _embed_query(seed)

        # Run MMR directly on the in-memory candidates.
        k = min(5, len(candidates))
        if len(candidates) <= k:
            selected = candidates
        else:
            selected_chunks = []
            remaining = list(candidates)
            while len(selected_chunks) < k and remaining:
                if not selected_chunks:
                    selected_chunks.append(remaining.pop(0))
                    continue
                best_score = -float("inf")
                best_idx = 0
                for i, chunk in enumerate(remaining):
                    relevance = _cosine_similarity(chunk.embedding, query_embedding)
                    max_sim = max(
                        _cosine_similarity(chunk.embedding, s.embedding)
                        for s in selected_chunks
                    )
                    score = 0.6 * relevance - 0.4 * max_sim
                    if score > best_score:
                        best_score = score
                        best_idx = i
                selected_chunks.append(remaining.pop(best_idx))
            selected = selected_chunks

        context = "\n\n".join(f"[{i+1}] {c.content}" for i, c in enumerate(selected))
    finally:
        db.close()

    return {"retrieved_context": context, "retry_count": 0}


def generate_question(state: QuizState) -> dict:
    """LLM generates a question + concept tag; embeds the question for dedup check."""
    prompt = _GENERATE_PROMPT.format(
        context=state["retrieved_context"],
        difficulty=state["difficulty"],
        asked_concepts=", ".join(state["asked_concepts"]) or "none",
    )

    raw = ""
    try:
        raw = _call_llm_generate(prompt)
        parsed = _parse_json(raw)
        question = parsed["question"]
        concept = parsed["concept"]
    except Exception as exc:
        logger.warning("generate_question: LLM call/parse failed (%s) — using raw output", exc)
        question = raw.strip() or "What is the main concept covered in this document?"
        concept = "general"

    embedding = _embed_query(question)

    return {
        "current_question": question,
        "current_concept": concept,
        "current_question_embedding": embedding,
        "retry_count": state["retry_count"] + 1,
    }


def route_after_generate(state: QuizState) -> str:
    """Conditional edge: retry if question is too similar to past questions."""
    too_similar = _is_too_similar(
        state["current_question_embedding"],
        state["asked_question_embeddings"],
    )
    if too_similar and state["retry_count"] < MAX_RETRIES:
        logger.info(
            "route_after_generate: question too similar (retry %d)", state["retry_count"]
        )
        return "retry"
    return "proceed"


def evaluate_answer(state: QuizState) -> dict:
    """LLM scores the user's answer and returns structured feedback."""
    prompt = _EVALUATE_PROMPT.format(
        question=state["current_question"],
        context=state["retrieved_context"],
        user_answer=state["user_answer"],
    )

    try:
        raw = _call_llm_evaluate(prompt)
        parsed = _parse_json(raw)
        feedback = parsed["feedback"]
        correct_answer = parsed.get("correct_answer", "")
        confidence_score = float(parsed["confidence_score"])
        is_correct = bool(parsed["is_correct"])
    except Exception as exc:
        logger.warning("evaluate_answer: LLM parse failed (%s)", exc)
        feedback = raw.strip()
        correct_answer = ""
        confidence_score = 0.5
        is_correct = False

    return {
        "ai_feedback": feedback,
        "correct_answer": correct_answer,
        "confidence_score": confidence_score,
        "is_correct": is_correct,
    }


def adapt_difficulty(state: QuizState) -> dict:
    """Adjust difficulty and update weak_areas based on the latest score."""
    score = state["confidence_score"]
    current = state["difficulty"]
    idx = DIFFICULTY_LADDER.index(current)

    if score > DIFFICULTY_UP_THRESHOLD and idx < len(DIFFICULTY_LADDER) - 1:
        new_difficulty = DIFFICULTY_LADDER[idx + 1]
    elif score < DIFFICULTY_DOWN_THRESHOLD and idx > 0:
        new_difficulty = DIFFICULTY_LADDER[idx - 1]
    else:
        new_difficulty = current

    weak_areas = list(state["weak_areas"])
    if not state["is_correct"] and state["current_concept"] not in weak_areas:
        weak_areas.append(state["current_concept"])

    return {"difficulty": new_difficulty, "weak_areas": weak_areas}


def persist_attempt(state: QuizState) -> dict:
    """Write the completed Q&A pair to quiz_attempts and update the session score."""
    db = SessionLocal()
    try:
        attempt = QuizAttempt(
            session_id=uuid.UUID(state["session_id"]),
            question=state["current_question"],
            answer=state["user_answer"],
            correct=state["is_correct"],
            concept=state["current_concept"],
            ai_feedback=state["ai_feedback"],
            confidence_score=state["confidence_score"],
            difficulty_level=state["difficulty"],
        )
        db.add(attempt)
        db.commit()
    finally:
        db.close()

    new_questions_asked = state["questions_asked"] + 1
    new_total_score = state["total_score"] + state["confidence_score"]
    new_asked_concepts = state["asked_concepts"] + [state["current_concept"]]
    new_asked_embeddings = state["asked_question_embeddings"] + [
        state["current_question_embedding"]
    ]

    return {
        "questions_asked": new_questions_asked,
        "total_score": new_total_score,
        "asked_concepts": new_asked_concepts,
        "asked_question_embeddings": new_asked_embeddings,
        "user_answer": "",
        "ai_feedback": "",
    }


def route_after_persist(state: QuizState) -> str:
    """Decide whether to generate another question or end the session."""
    if state["questions_asked"] >= state["max_questions"]:
        return "end"
    return "continue"


def finalize_session(state: QuizState) -> dict:
    """Write a lightweight summary to QuizSession.state_json on completion and upsert Progress rows."""
    db = SessionLocal()
    try:
        session = db.get(QuizSession, uuid.UUID(state["session_id"]))
        if session:
            avg_score = (
                state["total_score"] / state["questions_asked"]
                if state["questions_asked"] > 0
                else 0.0
            )
            session.score = avg_score
            session.state_json = {
                "completed": True,
                "questions_asked": state["questions_asked"],
                "avg_score": avg_score,
                "weak_areas": state["weak_areas"],
            }
            db.flush()

            # Aggregate per-concept confidence from this session's attempts
            attempts = (
                db.query(QuizAttempt)
                .filter(QuizAttempt.session_id == session.id)
                .all()
            )
            concept_scores: dict[str, list[float]] = {}
            for attempt in attempts:
                topic = attempt.concept or "general"
                concept_scores.setdefault(topic, []).append(attempt.confidence_score or 0.0)

            # Upsert Progress rows (query-then-update because no unique DB constraint)
            for topic, scores in concept_scores.items():
                strength = round(sum(scores) / len(scores), 4)
                existing = (
                    db.query(Progress)
                    .filter(
                        Progress.user_id == session.user_id,
                        Progress.doc_id == session.doc_id,
                        Progress.topic == topic,
                    )
                    .first()
                )
                if existing:
                    # Simple exponential moving average: blend old and new equally
                    existing.strength_score = round((existing.strength_score + strength) / 2, 4)
                else:
                    db.add(
                        Progress(
                            user_id=session.user_id,
                            doc_id=session.doc_id,
                            topic=topic,
                            strength_score=strength,
                        )
                    )

            db.commit()
    finally:
        db.close()

    return {"is_completed": True}
