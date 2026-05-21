# Tutor MVP Architecture v2 (2026-05-19)

## Overview
AI-powered online tutor platform. Upload documents → ask questions → take adaptive quizzes → track progress.
Built for rapid MVP delivery. Go deferred to v2 (intentional, not forgotten).

---

## Core Stack

| Layer | Technology | Deployment |
|---|---|---|
| Frontend | Next.js (React-based, App Router) | Vercel |
| API Backend | FastAPI (Python) | ECS Fargate |
| Ingestion Worker | Python (Celery) | ECS Fargate |
| AI / RAG / Quiz | LangChain + LangGraph (Python) | via FastAPI |
| Database | Postgres (RDS) + pgvector | RDS |
| Storage | S3 | AWS |
| Queue | SQS | AWS |
| Cache / Broker | Redis (ElastiCache) | AWS |

---

## Component Responsibilities

### 1. Next.js Frontend (Vercel)
- React-based — familiar patterns, App Router adds file-based routing on top
- Pages:
  - `/upload` — PDF/DOCX upload (calls API for pre-signed S3 URL, uploads directly to S3)
  - `/chat` — RAG-powered tutor chat (streaming responses)
  - `/quiz` — Adaptive quiz interface (session-based)
  - `/progress` — Dashboard (scores, weak topics, activity)
- Auth: NextAuth.js (simple session-based for MVP)
- Calls FastAPI over HTTPS; handles streaming via `ReadableStream`

### 2. FastAPI Backend (Python, ECS Fargate)
- Core REST + streaming endpoints:
  - `POST /upload/presign` — returns S3 pre-signed URL
  - `POST /upload/confirm` — registers doc in DB, enqueues SQS job
  - `POST /chat` — RAG query, streams LLM response (SSE)
  - `POST /quiz/start` — starts LangGraph quiz session
  - `POST /quiz/answer` — submits answer, gets next question
  - `GET /progress/{user_id}` — returns progress summary
- Owns all LangChain / LangGraph logic
- Persists all structured data to Postgres
- Pushes ingestion jobs to SQS via boto3

### 3. Celery Worker (Python, ECS Fargate)
- Separate ECS task, same Python codebase as FastAPI (shared lib)
- Consumes SQS via Celery SQS broker
- Per-job flow:
  1. Download file from S3
  2. Parse PDF/DOCX (PyMuPDF / python-docx)
  3. Chunk text (LangChain `RecursiveCharacterTextSplitter`)
  4. Embed chunks (OpenAI `text-embedding-3-small` or local)
  5. Store chunks + vectors in Postgres (pgvector)
  6. Update document status in DB
- DLQ on SQS for failed jobs; CloudWatch alarm on DLQ depth

> **Note:** This is the Go worker from v1, rewritten in Python for MVP.
> Go rewrite is a clean, isolated upgrade path in v2 — no AI complexity here.

### 4. LangChain / LangGraph (AI Layer, inside FastAPI)
- **RAG chain (LangChain):**
  - Retriever: pgvector similarity search (top-k chunks)
  - Prompt: system context + retrieved chunks + user question
  - LLM: Claude claude-sonnet-4-20250514 via Anthropic API (or GPT-4o)
  - Streaming: yields tokens directly to SSE response
- **Quiz engine (LangGraph):**
  - Stateful graph: `generate_question` → `evaluate_answer` → `adapt_difficulty` → loop
  - State stored in Postgres (not in-memory) — survives restarts
  - Tracks: topic coverage, difficulty level, score per session

### 5. Postgres + pgvector (RDS)
```
users          (id, email, created_at)
documents      (id, user_id, name, s3_key, status, created_at)
chunks         (id, doc_id, content, metadata, embedding vector(1536))
quiz_sessions  (id, user_id, doc_id, state_json, score, created_at)
quiz_attempts  (id, session_id, question, answer, correct, created_at)
progress       (id, user_id, doc_id, topic, strength_score, updated_at)
```
- pgvector index: `ivfflat` on `chunks.embedding` for fast ANN search
- All LangGraph session state serialized into `quiz_sessions.state_json`

### 6. S3
- Bucket: `tutor-uploads-{env}`
- Raw file storage only — source of truth for original documents
- Pre-signed URLs for direct browser → S3 upload (no file passes through API)
- Lifecycle policy: move to Glacier after 90 days

### 7. SQS
- Queue: `tutor-ingestion-{env}`
- DLQ: `tutor-ingestion-dlq-{env}` (max 3 retries)
- CloudWatch alarm: DLQ depth > 0 → SNS notification

### 8. Redis (ElastiCache)
- Celery broker + result backend
- Optional: cache frequent RAG queries (by doc_id + question hash)
- Optional: rate limiting on chat endpoint

---

## Data Flow

### Upload Flow
```
Browser
  → POST /upload/presign (FastAPI)         # get pre-signed S3 URL
  → PUT file directly to S3               # browser uploads, no API bandwidth used
  → POST /upload/confirm (FastAPI)         # register doc, push SQS job
  → SQS → Celery Worker                   # async ingestion
      → S3 download → parse → chunk → embed → pgvector
      → update doc status = "ready"
```

### Chat (RAG) Flow
```
Browser
  → POST /chat (FastAPI, streaming)
      → pgvector similarity search (top 5 chunks)
      → LangChain RAG chain
      → LLM (Claude / GPT-4o)
      → SSE stream back to browser
```

### Quiz Flow
```
Browser
  → POST /quiz/start (FastAPI)
      → LangGraph: initialize state, generate first question
      → return question + session_id

  → POST /quiz/answer (FastAPI)
      → LangGraph: evaluate answer, adapt difficulty, generate next question
      → persist state to Postgres
      → return result + next question
```

---

## Deployment

### Infrastructure
- **Frontend:** Vercel (CI/CD on push, preview deploys per PR)
- **FastAPI + Celery:** ECS Fargate (separate task definitions, scale independently)
- **Postgres:** RDS (Multi-AZ for prod, single-AZ for dev)
- **Redis:** ElastiCache (single node for MVP)
- **S3 / SQS:** Standard AWS managed services

### Environments
- `dev` — local Docker Compose (Postgres + Redis + LocalStack for S3/SQS)
- `staging` — full AWS stack, seeded with test docs
- `prod` — same as staging + RDS Multi-AZ + CloudWatch dashboards

### Local Dev Setup
```
docker-compose up   # Postgres, Redis, LocalStack
uvicorn main:app    # FastAPI
celery -A worker    # Celery worker
npm run dev         # Next.js
```

---

## 45-Day Build Plan (~130 hours)

| Phase | Days | Focus | Deliverable |
|---|---|---|---|
| 1 | 1–10 | RAG core | Upload PDF → chunk → embed → ask a question. All local. |
| 2 | 11–18 | Ingestion pipeline | S3 + SQS + Celery worker. Doc status tracking. |
| 3 | 19–28 | Next.js frontend | Upload page, chat UI (streaming), auth (NextAuth) |
| 4 | 29–36 | Quiz engine | LangGraph quiz sessions, progress tracking in DB |
| 5 | 37–42 | Deploy | ECS tasks, RDS, Vercel, staging env end-to-end |
| 6 | 43–45 | Polish | Error handling, loading states, basic monitoring |

---

## Extensibility / Upgrade Paths

| What | How |
|---|---|
| Add Go worker | Drop-in replacement for Celery worker — same SQS contract, same DB schema |
| Hybrid retrieval | Add BM25 keyword search alongside pgvector, rerank with Cohere |
| New file types | Add parser in Celery worker (Docling, Notion API, etc.) |
| Swap LLM | Change one line in LangChain chain config |
| Multi-tenancy | Add `org_id` to all DB tables + API scoping |
| Real-time | Replace SSE with WebSockets (FastAPI supports both) |
| Analytics | Separate FastAPI router or standalone microservice |

---

## Out of Scope for MVP
- Go worker (planned v2 — clean upgrade, no rework needed)
- Notion / Docling ingestion
- Hybrid / reranked retrieval
- Multi-tenant SaaS hardening
- Fine-grained RBAC
- Real-time collaborative features

---

## Key Decisions Log

| Decision | Reason |
|---|---|
| Celery over Go worker | Ship faster; Go rewrite is isolated and clean when ready |
| SSE over WebSockets | Simpler for MVP streaming; WebSockets when needed |
| Pre-signed S3 upload | API never handles file bytes; scales for free |
| LangGraph state in Postgres | Survives restarts; queryable; no extra state store |
| Redis for Celery broker | SQS-as-broker works but Redis gives better local dev parity |
| Next.js App Router | Modern pattern; React knowledge transfers directly |
| `text-embedding-3-small` | Cost-effective; upgrade to large if retrieval quality suffers |