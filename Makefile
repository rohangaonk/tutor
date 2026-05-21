.PHONY: up down api worker web install sync

up:
	docker compose up -d

down:
	docker compose down

api:
	uv run --package api uvicorn api.main:app --reload --port 8000

worker:
	uv run --package worker celery -A worker.celery_app:app worker --loglevel=info

web:
	cd apps/web && npm run dev

install:
	npm install

sync:
	uv sync --all-packages
