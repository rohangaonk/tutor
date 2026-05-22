# RAG — Quiz Question Deduplication Design

**Scope:** Current session only  
**Project:** AI Tutor App  
**Status:** Finalised for Phase 1

---

## Problem

RAG retrieval ranks chunks by vector similarity. When two chunks cover the same concept with different wording, both score high and the question generator produces near-identical questions in the same session. The user gets asked the same concept twice.

---

## Solution — Three Layers

### Layer 1 — MMR at retrieval (Maximal Marginal Relevance)

Replaces standard similarity search. Balances relevance to the query against diversity from already-selected chunks.

**Formula:**  
`score = λ × similarity(chunk, query) − (1−λ) × max_similarity(chunk, already_selected)`

The second term is the negative scoring — it penalises chunks that are too close to what was already retrieved.

**LangChain config:**
```python
retriever = vectorstore.as_retriever(
    search_type="mmr",
    search_kwargs={"k": 5, "fetch_k": 20, "lambda_mult": 0.6}
)
```

- `fetch_k=20` — pull 20 candidates first
- `k=5` — MMR re-ranks down to 5 diverse chunks
- `lambda_mult=0.6` — leans slightly toward relevance over diversity

**What it solves:** Prevents similar chunks from being retrieved in the same call.  
**What it does not solve:** Doesn't know what questions were already asked.

---

### Layer 2 — Embedding similarity check before generation

Before the LLM generates a new question, compute its embedding and compare against all questions already asked in this session. If cosine similarity exceeds threshold, reject and retry.

```python
async def is_too_similar(candidate_embedding, session_id, threshold=0.92):
    past_embeddings = await get_session_question_embeddings(session_id)
    for past in past_embeddings:
        if cosine_similarity(candidate_embedding, past) > threshold:
            return True
    return False
```

**Threshold:** 0.92 — high enough to catch rephrased duplicates, low enough to allow related but distinct questions.

**What it solves:** Catches semantically duplicate questions even when retrieved from different chunks.

---

### Layer 3 — Concept set tracking in LangGraph state

Track which concepts have been covered as a running list in session state. Pass it to the LLM as a negative constraint in the prompt.

**State schema:**
```python
class QuizState(TypedDict):
    session_id: str
    asked_concepts: list[str]        # e.g. ["goroutines", "channels", "defer"]
    asked_question_embeddings: list[list[float]]
    weak_areas: list[str]
    current_question: str
    ...
```

**Prompt instruction:**
> "Do not generate a question about any of these concepts: `{asked_concepts}`. Pick a different concept from the retrieved chunks."

**What it solves:** LLM-level guard — prevents the model from generating a new-wording question on an already-covered concept.

---

## LangGraph Node Flow

```
retrieve_context  (MMR retrieval)
       ↓
generate_question
       ↓
similarity_check
       ↓ too similar (retry, max 3)
       └──────────────→ retrieve_context (new seed)
       ↓ unique
  ask_user
```

The retry is a conditional edge in LangGraph. Cap retries at 3 — after that, accept the best available question to avoid infinite loops.

---

## What Gets Stored Per Question

| Field | Type | Notes |
|---|---|---|
| `session_id` | UUID | Links to session |
| `concept` | string | LLM-extracted tag |
| `question` | text | Question asked |
| `user_answer` | text | Raw user input |
| `ai_feedback` | text | LLM evaluation |
| `is_correct` | boolean | |
| `confidence_score` | float | 0–1 |
| `difficulty_level` | string | easy / medium / hard |
| `created_at` | timestamp | |

No vectorisation of Q&A pairs needed for report generation. Report is a SQL aggregation query fed into a summarisation chain.

---

## Report Generation (end of session)

1. SQL aggregation — accuracy by concept, score trend, hardest questions
2. Feed structured result to a LangChain progress analysis chain
3. LLM generates natural language summary

No RAG involved in report generation. Plain analytical SQL + LLM summarisation.

---

## Future Work (out of scope for Phase 1)

- **Cross-session deduplication** — on session start, load last N question embeddings from `quiz_questions` table and seed `asked_question_embeddings` in state
- **Follow-up questions** — if `is_correct = false`, orchestrator routes to a follow-up sub-agent that asks a simpler question on the same concept before moving on