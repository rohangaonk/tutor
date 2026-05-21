FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy workspace definition and package manifests
COPY pyproject.toml uv.lock ./
COPY packages/common ./packages/common
COPY apps/api ./apps/api

# Install dependencies (no dev, frozen lockfile)
RUN uv sync --frozen --package api --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
