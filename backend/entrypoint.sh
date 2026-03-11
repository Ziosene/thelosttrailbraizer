#!/bin/sh
set -e

echo "Waiting for postgres..."
until python -c "import psycopg2; psycopg2.connect('$DATABASE_URL')" 2>/dev/null; do
  sleep 1
done
echo "Postgres is up."

echo "Running migrations..."
alembic upgrade head

echo "Seeding cards..."
python scripts/seed_cards.py

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
