.PHONY: up down api worker web install sync init-localstack seed-db

up:
	docker compose up -d

down:
	docker compose down

init-localstack:
	AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566 s3 mb s3://tutor-uploads-local --region us-east-1 || true
	AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566 sqs create-queue --queue-name tutor-ingestion-local --region us-east-1 || true

seed-db:
	PGPASSWORD=tutor psql -h localhost -p 5434 -U tutor -d tutor -c \
		"INSERT INTO users (id, email, created_at) VALUES ('550e8400-e29b-41d4-a716-446655440000', 'test@example.com', now()) ON CONFLICT DO NOTHING;"

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
