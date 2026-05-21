# Tutor MVP Roadmap

This roadmap turns the architecture into phased execution. The order is deliberate: build the backend and local infrastructure first, then bring in the frontend once the API contract is stable.

## Principles

- Build the backend before the frontend.
- Keep the repo as a monorepo.
- Use `npm` for the frontend workspace.
- Use `uv` for Python dependency management and reproducible Docker builds.
- Use a `Makefile` for common workflows.
- Deploy infrastructure with AWS CDK, except the frontend, which goes to Vercel.

## Phase 0 - Foundation

Goal: create a runnable local development skeleton with no business logic yet.

Steps:

1. Create the monorepo layout: `apps/`, `packages/`, `infra/`, `ops/`.
2. Initialize the root npm workspace for the frontend package.
3. Initialize the Python workspace with `uv` for backend and shared code.
4. Add a shared Python package for common models, config, and domain logic.
5. Scaffold the FastAPI app with a `/health` endpoint.
6. Scaffold the Celery worker entrypoint.
7. Scaffold the Next.js app under the frontend workspace.
8. Add `docker-compose` for local Postgres, Redis, and LocalStack.
9. Add a root `Makefile` for local dev commands.
10. Add Dockerfiles for the API and worker.

Definition of done:

- `make up` starts the local stack.
- `make api`, `make worker`, and `make web` each start the relevant service.
- The API responds to `/health`.

## Phase 1 - Data Model and Backend Core

Goal: establish the database schema, migrations, and shared backend foundations.

Steps:

1. Add SQLAlchemy models for users, documents, chunks, quiz sessions, quiz attempts, and progress.
2. Add Alembic migrations.
3. Enable `pgvector` in local and deployed Postgres environments.
4. Add the vector index for chunk similarity search.
5. Add a shared DB session and repository layer in the Python package.
6. Add config and secrets handling for local, staging, and production.

Definition of done:

- Schema can be created from migrations.
- The backend can connect to Postgres from local Docker.
- The shared package is used by both the API and worker.

## Phase 2 - Ingestion Pipeline

Goal: upload a document, process it asynchronously, and store searchable chunks.

Steps:

1. Implement `POST /upload/presign` for S3 pre-signed uploads.
2. Implement `POST /upload/confirm` to register the document and enqueue ingestion.
3. Wire LocalStack S3 and queue behavior for local testing.
4. Implement worker download, parsing, and text extraction for PDF and DOCX.
5. Implement chunking and embeddings.
6. Persist chunks and vectors to Postgres.
7. Update document status during the ingestion lifecycle.
8. Add failure handling and retry behavior.

Definition of done:

- A document uploaded through the API becomes available in Postgres as chunked, embedded content.
- Failed jobs are visible and recoverable.

## Phase 3 - RAG Chat

Goal: answer questions against uploaded documents with streaming responses.

Steps:

1. Implement document-scoped vector retrieval.
2. Build the RAG chain in the backend.
3. Implement `POST /chat` with streaming SSE output.
4. Add prompt structure and context assembly.
5. Validate the flow with local command-line requests before touching the UI.

Definition of done:

- Chat responses are grounded in the uploaded document.
- Streaming works end to end from API to client.

## Phase 4 - Quiz Engine

Goal: start a quiz session, adapt the next question, and persist session state.

Steps:

1. Define the quiz session state model.
2. Implement LangGraph quiz flow nodes.
3. Persist quiz state in Postgres.
4. Implement `POST /quiz/start`.
5. Implement `POST /quiz/answer`.
6. Add scoring and difficulty adaptation logic.

Definition of done:

- Quiz sessions survive restarts.
- The backend can generate a question, evaluate an answer, and continue the session.

## Phase 5 - Progress Tracking

Goal: make learner progress queryable and visible in the API.

Steps:

1. Update progress data after quiz attempts.
2. Implement `GET /progress/{user_id}`.
3. Add summary and topic strength calculations.

Definition of done:

- Progress is derived from real quiz interactions.
- The API returns meaningful per-topic state.

## Phase 6 - Frontend

Goal: build the user-facing experience once the backend contract is stable.

Steps:

1. Add authentication and session handling.
2. Build the upload page.
3. Build the chat page with streaming UI.
4. Build the quiz page.
5. Build the progress dashboard.
6. Connect the frontend to the API endpoints.
7. Add loading and error states.

Definition of done:

- Users can upload, chat, quiz, and review progress from the browser.
- The frontend works against the local backend stack.

## Phase 7 - Infrastructure and Deployment

Goal: deploy the system to AWS and Vercel with repeatable infrastructure.

Steps:

1. Initialize the AWS CDK project for infrastructure.
2. Define stacks for data, API, and worker services.
3. Provision S3, SQS, RDS, and Redis.
4. Build ECS Fargate services for the API and worker.
5. Configure secrets and environment variables.
6. Set up image builds and deployments.
7. Deploy the frontend to Vercel.
8. Validate the full production-like flow in staging.

Definition of done:

- The backend and worker deploy through AWS CDK.
- The frontend deploys independently to Vercel.

## Phase 8 - Polish and Hardening

Goal: tighten reliability before production use.

Steps:

1. Add better error handling and structured API responses.
2. Add rate limiting to chat endpoints.
3. Add monitoring and alarms for queue depth and service health.
4. Add smoke tests for the main user journeys.
5. Review storage, retention, and lifecycle policies.

Definition of done:

- The app is stable enough for early users.
- The main flows can be monitored and exercised automatically.

## Recommended Build Order

1. Phase 0
2. Phase 1
3. Phase 2
4. Phase 3
5. Phase 4
6. Phase 5
7. Phase 6
8. Phase 7
9. Phase 8

The main rule is to keep the frontend out of the critical path until the backend API is already usable from the command line.