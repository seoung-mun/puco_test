#!/bin/bash
set -e

echo "=== DB Migration ==="
alembic upgrade head
echo "Migration complete."

echo "=== Starting server ==="
PORT_VALUE="${PORT:-8000}"
if [ "${DEBUG:-false}" = "true" ]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT_VALUE}" --reload
else
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT_VALUE}" --workers 1 --timeout-graceful-shutdown 30
fi
