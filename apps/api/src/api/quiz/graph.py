"""Build the quiz LangGraph state machine."""

from __future__ import annotations

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver  # noqa: F401 – kept for type hints

from api.quiz.state import QuizState
from api.quiz.nodes import (
    retrieve_context,
    generate_question,
    route_after_generate,
    evaluate_answer,
    adapt_difficulty,
    persist_attempt,
    route_after_persist,
    finalize_session,
)


def build_quiz_graph(checkpointer: BaseCheckpointSaver):
    """Compile the quiz state machine with the given persistence checkpointer."""

    builder = StateGraph(QuizState)

    # ── Nodes ─────────────────────────────────────────────────────────────
    builder.add_node("retrieve_context", retrieve_context)
    builder.add_node("generate_question", generate_question)
    builder.add_node("evaluate_answer", evaluate_answer)
    builder.add_node("adapt_difficulty", adapt_difficulty)
    builder.add_node("persist_attempt", persist_attempt)
    builder.add_node("finalize_session", finalize_session)

    # ── Entry ─────────────────────────────────────────────────────────────
    builder.set_entry_point("retrieve_context")

    # ── Edges ─────────────────────────────────────────────────────────────
    builder.add_edge("retrieve_context", "generate_question")

    builder.add_conditional_edges(
        "generate_question",
        route_after_generate,
        {
            "retry": "retrieve_context",   # too similar — fetch fresh chunks
            "proceed": "evaluate_answer",  # unique enough — wait for user
        },
    )

    # The graph is interrupted BEFORE evaluate_answer so the router can
    # return the question to the client and resume once the answer arrives.
    builder.add_edge("evaluate_answer", "adapt_difficulty")
    builder.add_edge("adapt_difficulty", "persist_attempt")

    builder.add_conditional_edges(
        "persist_attempt",
        route_after_persist,
        {
            "continue": "retrieve_context",
            "end": "finalize_session",
        },
    )

    builder.add_edge("finalize_session", END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["evaluate_answer"],
    )
