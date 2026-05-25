from __future__ import annotations

from typing import TypedDict


class QuizState(TypedDict):
    # ── Session config (set once at start, never mutated) ─────────────────
    doc_id: str
    user_id: str
    session_id: str
    max_questions: int
    document_topics: list[str]  # canonical topics extracted during ingestion

    # ── Progress ───────────────────────────────────────────────────────────
    questions_asked: int
    difficulty: str          # "easy" | "medium" | "hard"
    total_score: float       # running sum of confidence_score
    weak_areas: list[str]    # concept tags where the user struggled
    is_completed: bool

    # ── Deduplication (grows each question cycle) ──────────────────────────
    asked_concepts: list[str]
    asked_question_embeddings: list[list[float]]  # 768-dim vectors
    retry_count: int                               # MMR retries this cycle

    # ── Current question cycle ─────────────────────────────────────────────
    retrieved_context: str           # formatted MMR chunks
    current_topic: str               # predefined topic selected for this question
    current_question: str
    current_concept: str
    current_question_embedding: list[float]

    # ── Answer cycle (populated after user responds) ───────────────────────
    user_answer: str
    ai_feedback: str
    correct_answer: str
    confidence_score: float
    is_correct: bool
