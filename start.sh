#!/bin/sh
set -eu

python -m worker.recovery &
RECOVERY_PID=$!

rq worker --url "$REDIS_URL" "$TRANSACTION_QUEUE_NAME" &
WORKER_PID=$!

uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" &
API_PID=$!

cleanup() {
    trap - INT TERM EXIT
    kill "$API_PID" "$WORKER_PID" "$RECOVERY_PID" 2>/dev/null || true
    wait "$API_PID" "$WORKER_PID" "$RECOVERY_PID" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

# POSIX-compatible polling: exit if any child process dies.
while kill -0 "$API_PID" 2>/dev/null &&
      kill -0 "$WORKER_PID" 2>/dev/null &&
      kill -0 "$RECOVERY_PID" 2>/dev/null; do
    sleep 2
done

exit 1
