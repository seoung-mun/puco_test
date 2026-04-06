#!/bin/bash
set -e

echo "=== DB Migration ==="
alembic upgrade head
echo "Migration complete."

echo "=== Starting server ==="
if [ "${DEBUG:-false}" = "true" ]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
fi
