# Quiz Engine Knowledge

This note captures how the quiz engine currently works internally, with emphasis on duplicate-question handling and report generation.

## High-level Flow

The quiz engine is implemented as a LangGraph state machine in [apps/api/src/api/quiz/graph.py](apps/api/src/api/quiz/graph.py) and the node logic lives in [apps/api/src/api/quiz/nodes.py](apps/api/src/api/quiz/nodes.py).

The API starts a quiz with `POST /quiz/start`, pauses before answer evaluation, then resumes with `POST /quiz/answer`.

The main execution cycle is:

1. Retrieve document context.
2. Generate a question from that context.
3. Check whether the question is too similar to earlier questions.
4. Pause and return the question to the client.
5. Resume after the user answers.
6. Evaluate the answer, adjust difficulty, and persist the attempt.
7. Either generate another question or finalize the session.

## Duplicate-Question Prevention

The engine uses three layers of duplicate prevention.

### 1. Context diversity via MMR

The `retrieve_context` node first loads document chunks, then samples a subset and re-ranks them with a Maximal Marginal Relevance style selection.

That selection is designed to balance:

- relevance to a generic embedding query
- diversity relative to chunks already selected in the same round

The practical effect is that the question generator sees a more varied set of supporting chunks, which reduces repeated questions caused by nearly identical context.

The implementation uses an in-memory MMR pass over already loaded chunks rather than relying on a separate database query for the final re-ranking step.

### 2. Prompt-level concept exclusion

The question generation prompt includes a list of `asked_concepts` and explicitly tells the LLM not to generate a question on any of them.

This is a soft constraint only. It helps, but it is not enough by itself because the model can still repeat a concept in a different wording.

### 3. Embedding similarity check on the generated question

After the model produces a question, the engine embeds that question and compares it against all previously asked question embeddings stored in quiz state.

If cosine similarity is greater than the configured threshold, the graph routes back to `retrieve_context` and tries again.

This is the hard duplicate guard.

### Retry behavior

The retry path is bounded by `MAX_RETRIES`.

Flow:

- generate question
- compare embedding against prior question embeddings
- if too similar and retry budget remains, go back to context retrieval
- otherwise proceed to the answer phase

So duplicate prevention is not a single mechanism; it is a combination of context diversity, prompt constraints, and explicit question-level similarity rejection.

## Report Generation

The session report endpoint is implemented in [apps/api/src/api/routers/quiz.py](apps/api/src/api/routers/quiz.py).

It is a pure SQL aggregation over `QuizAttempt` rows.

### Data source

Each answered question is persisted by `persist_attempt` in [apps/api/src/api/quiz/nodes.py](apps/api/src/api/quiz/nodes.py).

That row stores:

- question text
- user answer
- correctness
- concept tag
- feedback
- confidence score
- difficulty level

The report endpoint does not inspect LangGraph state directly. It reads the persisted attempts table.

### Aggregation logic

The endpoint filters attempts by `session_id`, groups rows by `concept`, and computes:

- total attempts
- correct attempts
- average confidence score
- accuracy ratio

The current output is a per-concept summary for a single quiz session.

### What the report means

This report is best understood as:

- “Which concepts were asked in this session?”
- “How often did the user answer them correctly?”
- “How confident was the model while evaluating those answers?”

It is not yet a broader learner profile, and it does not aggregate across sessions or documents.

## Operational Notes

### Database access

The quiz nodes open short-lived SQLAlchemy sessions through `SessionLocal`. Those sessions are backed by the shared engine in [packages/common/src/common/db.py](packages/common/src/common/db.py), which uses pooled connections.

So the code uses multiple connections over time, but they are managed through pooling rather than creating a fresh database connection each time.

### State growth

The quiz state keeps a growing list of prior question embeddings and concept tags.

That is useful for duplicate detection, but it also means quiz state grows as the session continues. For long sessions, that is the main area to watch for memory and checkpoint size.

## Likely Optimization Targets

If this area needs tuning later, the most useful targets are:

1. Reduce state growth by storing a smaller dedupe history or compact fingerprint.
2. Push more of the candidate chunk selection into the database if retrieval latency becomes a problem.
3. Expand the report to include difficulty and/or document-level grouping if the UI needs richer progress analytics.
4. Consider caching or precomputing embeddings for repeated duplicate checks if session length grows significantly.

## Current Mental Model

In practice, the engine works like this:

- MMR makes the context less repetitive.
- The prompt discourages the model from repeating covered concepts.
- The question embedding check rejects near-duplicates before the user ever sees them.
- Persisted attempts become the source of truth for reporting.

That separation is important: generation is controlled by graph state, while reporting is driven by stored quiz attempts.
