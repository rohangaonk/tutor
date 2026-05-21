FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy workspace definition and package manifests
COPY pyproject.toml uv.lock ./
COPY packages/common ./packages/common
COPY apps/worker ./apps/worker

# Install dependencies (no dev, frozen lockfile)
RUN uv sync --frozen --package worker --no-dev

ENV PATH="/app/.venv/bin:$PATH"

CMD ["celery", "-A", "worker.celery_app:app", "worker", "--loglevel=info"]
