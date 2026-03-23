#!/bin/bash
set -e

echo "=== DB Migration ==="

if alembic upgrade head; then
    echo "Migration complete."
else
    echo "Migration failed — existing schema detected. Stamping as head..."
    alembic stamp head
    alembic upgrade head
    echo "Stamp complete."
fi

echo "=== Starting server ==="
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
