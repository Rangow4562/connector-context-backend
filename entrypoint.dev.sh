#!/bin/bash
set -e

# Wait for database to be ready
echo "Waiting for database..."
poetry run python -c "
from tenacity import retry, stop_after_attempt, wait_fixed
from sqlalchemy import create_engine
import os

@retry(stop=stop_after_attempt(5), wait=wait_fixed(2))
def check_db():
    user = os.environ['POSTGRES_USER']
    password = os.environ['POSTGRES_PASSWORD']
    host = os.getenv('POSTGRES_HOST', 'db')
    db = os.getenv('POSTGRES_DB', 'connector_context')
    port = os.getenv('POSTGRES_PORT', '5432')
    engine = create_engine(f'postgresql://{user}:{password}@{host}/{db}')
    engine.connect()

check_db()
"

# Run migrations using our existing Alembic setup
echo "Running database migrations..."
cd /app && poetry run alembic upgrade head
# cd /app #dev time to not rerun alembic on conflicting branches

# Start application with hot reloading enabled
echo "Starting application with hot reloading..."
poetry run uvicorn connector_context.main:app --host 0.0.0.0 --port 8001 --reload --reload-dir /app/connector_context
