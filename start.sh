#!/bin/sh
set -eu

python -m worker.recovery &
RECOVERY_PID=$!

rq worker --url "$REDIS_URL" "$TRANSACTION_QUEUE_NAME" &
WORKER_PID=$!

uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" &
API_PID=$!

cleanup() {
    kill "$API_PID" "$WORKER_PID" "$RECOVERY_PID" 2>/dev/null || true
    wait || true
}

trap cleanup INT TERM

wait -n "$API_PID" "$WORKER_PID" "$RECOVERY_PID"
STATUS=$?
cleanup
exit "$STATUS"
