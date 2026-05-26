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

SIMILARITY_THRESHOLD = 0.82     # reject question if cosine sim > this (was 0.92 — too permissive)
MAX_RETRIES = 3                 # max MMR retries per question cycle (was 3)

DIFFICULTY_UP_THRESHOLD = 0.75  # promote difficulty when score exceeds this
DIFFICULTY_DOWN_THRESHOLD = 0.40  # demote difficulty when score is below this

DIFFICULTY_LADDER = ["easy", "medium", "hard"]

# ── Prompt templates ─────────────────────────────────────────────────────────

_GENERATE_PROMPT = """\
You are a quiz question generator for a tutoring system.

Document context:
{context}

Topic to assess: {topic}
Difficulty: {difficulty}
Already covered questions on this topic (avoid repetition): {asked_on_topic}

Generate ONE {difficulty}-level question that:
1. Can be answered from the context above only.
2. Is specifically about the topic: "{topic}".
3. Has a clear, unambiguous answer.
4. Explores a unique angle — vary the style (definition, application, comparison, cause-effect, example).

Respond with valid JSON only — no markdown fences:
{{"question": "<your question>", "concept": "{topic}"}}"""

_EVALUATE_PROMPT = """\
You are evaluating a student's answer to a quiz question.

Question: {question}
Reference context: {context}
Student's answer: {user_answer}

Respond with valid JSON only — no markdown fences:
{{"feedback": "<2-4 sentences evaluating the student's response>", "correct_answer": "<the correct answer extracted from the context, 1-3 sentences>", "confidence_score": <0.0-1.0>, "is_correct": <true|false>}}

confidence_score must represent how correct the student's answer is (not evaluator certainty).
Scoring guide: 1.0 = perfect, 0.7 = mostly correct, 0.4 = partial, 0.0 = wrong.
If is_correct is false, confidence_score must be <= 0.49."""

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


def _coerce_bool(value: object) -> bool:
    """Parse booleans robustly from JSON values that may be strings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    raise ValueError(f"Could not parse boolean value: {value!r}")


def _normalize_confidence_score(score: float, is_correct: bool) -> float:
    """Keep confidence in expected range and consistent with correctness flag."""
    bounded = max(0.0, min(1.0, score))
    if not is_correct:
        return min(bounded, 0.49)
    return bounded


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
    """Select the current predefined topic, retrieve the most relevant chunks for it.

    Topic selection cycles round-robin through document_topics based on
    questions_asked, ensuring every topic gets covered evenly across a session.
    Uses MMR to keep retrieved context chunks diverse and reduce duplication.
    Falls back to a generic retrieval seed when no predefined topics exist (legacy docs).
    """
    doc_id = uuid.UUID(state["doc_id"])
    document_topics = state.get("document_topics") or []

    # Pick the topic for this question cycle
    if document_topics:
        # Advance topic index by total questions attempted (including skips),
        # so skipping still moves to the next topic in the cycle.
        questions_attempted = len(state.get("asked_concepts", []))
        topic = document_topics[questions_attempted % len(document_topics)]
        query_seed = topic
    else:
        topic = ""
        query_seed = "key facts and concepts"

    db = SessionLocal()
    try:
        all_chunks = (
            db.query(Chunk)
            .filter(Chunk.doc_id == doc_id)
            .filter(Chunk.embedding.isnot(None))
            .all()
        )

        if not all_chunks:
            return {"retrieved_context": "", "current_topic": topic}

        # Embed the topic (or fallback seed) to retrieve relevant chunks
        query_embedding = _embed_query(query_seed)

        # MMR: retrieve k diverse chunks most relevant to the topic
        k = min(5, len(all_chunks))
        if len(all_chunks) <= k:
            selected = all_chunks
        else:
            selected_chunks: list[Chunk] = []
            remaining = list(all_chunks)
            while len(selected_chunks) < k and remaining:
                if not selected_chunks:
                    # Seed with the highest-relevance chunk
                    best_idx = max(
                        range(len(remaining)),
                        key=lambda i: _cosine_similarity(remaining[i].embedding, query_embedding),
                    )
                    selected_chunks.append(remaining.pop(best_idx))
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

    return {"retrieved_context": context, "current_topic": topic}


def generate_question(state: QuizState) -> dict:
    """LLM generates a question constrained to the current predefined topic."""
    current_topic = state.get("current_topic") or "general"
    # Collect the actual questions already asked on this topic so the LLM can
    # actively avoid repeating them (not just a count).
    prior_questions_on_topic = [
        q for q, c in zip(
            state.get("_asked_questions", []),
            state.get("asked_concepts", []),
        )
        if c == current_topic
    ]
    if prior_questions_on_topic:
        asked_on_topic = "Avoid these questions: " + " | ".join(f'"{q}"' for q in prior_questions_on_topic)
    else:
        asked_on_topic = "none"
    prompt = _GENERATE_PROMPT.format(
        context=state["retrieved_context"],
        topic=current_topic,
        difficulty=state["difficulty"],
        asked_on_topic=asked_on_topic,
    )

    raw = ""
    try:
        raw = _call_llm_generate(prompt)
        parsed = _parse_json(raw)
        question = parsed["question"]
        # Always use the predefined topic as the concept for consistent grouping
        concept = current_topic
    except Exception as exc:
        logger.warning("generate_question: LLM call/parse failed (%s) — using raw output", exc)
        question = raw.strip() or "What is the main concept covered in this document?"
        concept = current_topic

    embedding = _embed_query(question)

    return {
        "current_question": question,
        "current_concept": concept,
        "current_question_embedding": embedding,
        "retry_count": state["retry_count"] + 1,
    }


def route_after_generate(state: QuizState) -> str:
    """Conditional edge: retry if question is too similar to past questions."""
    past = state["asked_question_embeddings"]
    candidate = state["current_question_embedding"]
    if past:
        max_sim = max(_cosine_similarity(candidate, p) for p in past)
    else:
        max_sim = 0.0
    too_similar = max_sim > SIMILARITY_THRESHOLD
    logger.info(
        "route_after_generate: max_sim=%.3f threshold=%.2f too_similar=%s retry=%d",
        max_sim, SIMILARITY_THRESHOLD, too_similar, state["retry_count"],
    )
    if too_similar and state["retry_count"] < MAX_RETRIES:
        logger.info(
            "route_after_generate: question too similar (retry %d)", state["retry_count"]
        )
        return "retry"
    return "proceed"


def evaluate_answer(state: QuizState) -> dict:
    """LLM scores the user's answer and returns structured feedback."""
    logger.info(
        "[evaluate_answer] is_skipped=%s user_answer=%r",
        state.get("is_skipped"), state.get("user_answer", "")[:40],
    )
    if state.get("is_skipped"):
        logger.info("[evaluate_answer] skipping LLM call")
        return {
            "ai_feedback": "Question skipped.",
            "correct_answer": "",
            "confidence_score": 0.0,
            "is_correct": False,
        }

    prompt = _EVALUATE_PROMPT.format(
        question=state["current_question"],
        context=state["retrieved_context"],
        user_answer=state["user_answer"],
    )

    raw = ""
    try:
        raw = _call_llm_evaluate(prompt)
        parsed = _parse_json(raw)
        feedback = parsed["feedback"]
        correct_answer = parsed.get("correct_answer", "")
        is_correct = _coerce_bool(parsed["is_correct"])
        confidence_score = _normalize_confidence_score(float(parsed["confidence_score"]), is_correct)
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
    if state.get("is_skipped"):
        return {}  # no difficulty change for skipped questions

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
    is_skipped = state.get("is_skipped", False)
    logger.info("[persist_attempt] is_skipped=%s concept=%r questions_asked_before=%d", is_skipped, state.get("current_concept"), state["questions_asked"])
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
            is_skipped=is_skipped,
        )
        db.add(attempt)
        db.commit()
    finally:
        db.close()

    # Skipped questions do NOT count toward the answered-question counter,
    # so the session still produces `max_questions` real answers.
    new_questions_asked = state["questions_asked"] + (0 if is_skipped else 1)
    # Skipped questions don't count toward the session score
    new_total_score = state["total_score"] + (0.0 if is_skipped else state["confidence_score"])
    # Always track which concepts/questions were attempted so we cycle topics
    # and avoid repeating the same question even after a skip.
    new_asked_concepts = state["asked_concepts"] + [state["current_concept"]]
    new_asked_questions = state.get("_asked_questions", []) + [state["current_question"]]
    new_asked_embeddings = state["asked_question_embeddings"] + [
        state["current_question_embedding"]
    ]

    logger.info("[persist_attempt] new questions_asked=%d (skipped=%s)", new_questions_asked, is_skipped)

    return {
        "questions_asked": new_questions_asked,
        "total_score": new_total_score,
        "asked_concepts": new_asked_concepts,
        "_asked_questions": new_asked_questions,
        "asked_question_embeddings": new_asked_embeddings,
        "user_answer": "",
        "ai_feedback": "",
        "retry_count": 0,
        "is_skipped": False,
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

            # Aggregate per-concept confidence from this session's attempts (skipped excluded)
            attempts = (
                db.query(QuizAttempt)
                .filter(QuizAttempt.session_id == session.id)
                .filter(QuizAttempt.is_skipped.is_(False))
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
