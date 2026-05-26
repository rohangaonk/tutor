.PHONY: up down api worker web install sync init-localstack init-cognito seed-db

up:
	docker compose up -d

down:
	docker compose down

init-localstack:
	AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566 s3 mb s3://tutor-uploads-local --region us-east-1 || true
	AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566 sqs create-queue --queue-name tutor-ingestion-local --region us-east-1 || true

init-cognito:
	@echo "Creating Cognito User Pool and Client in cognito-local..."
	@uv run --package common python3 -c "\
import boto3; \
c = boto3.client('cognito-idp', endpoint_url='http://localhost:9229', region_name='us-east-1', aws_access_key_id='local', aws_secret_access_key='local'); \
pool = c.create_user_pool(PoolName='tutor-local', Policies={'PasswordPolicy':{'MinimumLength':8,'RequireUppercase':False,'RequireLowercase':False,'RequireNumbers':False,'RequireSymbols':False}}); \
pool_id = pool['UserPool']['Id']; \
cl = c.create_user_pool_client(UserPoolId=pool_id, ClientName='tutor-local-client', ExplicitAuthFlows=['ALLOW_USER_PASSWORD_AUTH','ALLOW_REFRESH_TOKEN_AUTH'], GenerateSecret=False); \
client_id = cl['UserPoolClient']['ClientId']; \
print(); \
print('Add these to your .env file:'); \
print(f'COGNITO_USER_POOL_ID={pool_id}'); \
print(f'COGNITO_CLIENT_ID={client_id}'); \
print('COGNITO_REGION=us-east-1'); \
print('COGNITO_ENDPOINT_URL=http://localhost:9229'); \
"

seed-db:
	PGPASSWORD=tutor psql -h localhost -p 5434 -U tutor -d tutor -c \
		"INSERT INTO users (id, email, created_at) VALUES ('550e8400-e29b-41d4-a716-446655440000', 'test@example.com', now()) ON CONFLICT DO NOTHING;"

api:
	uv run --package api uvicorn api.main:app --reload --port 8000

worker:
	uv run --package worker python -m worker

web:
	cd apps/web && npm run dev

install:
	npm install

sync:
	uv sync --all-packages
