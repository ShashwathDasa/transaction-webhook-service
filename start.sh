#!/bin/sh
set -eu

# SERVICE_ROLE selects which processes this container runs:
#   api    - the FastAPI app only
#   worker - the RQ workers and recovery service only
#   all    - everything in one container (single-service deployments)
SERVICE_ROLE="${SERVICE_ROLE:-all}"
WORKER_COUNT="${WORKER_COUNT:-2}"
PIDS=""

case "$SERVICE_ROLE" in
    api|worker|all) ;;
    *)
        echo "Unknown SERVICE_ROLE: $SERVICE_ROLE (expected api, worker, or all)" >&2
        exit 2
        ;;
esac

if [ "$SERVICE_ROLE" != "api" ]; then
    python -m worker.recovery &
    PIDS="$!"

    # Each RQ worker handles one job at a time, so run several to avoid backlogs.
    i=0
    while [ "$i" -lt "$WORKER_COUNT" ]; do
        rq worker --url "$REDIS_URL" "$TRANSACTION_QUEUE_NAME" &
        PIDS="$PIDS $!"
        i=$((i + 1))
    done
fi

if [ "$SERVICE_ROLE" != "worker" ]; then
    uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" &
    PIDS="$PIDS $!"
fi

cleanup() {
    trap - INT TERM EXIT
    # shellcheck disable=SC2086
    kill $PIDS 2>/dev/null || true
    # shellcheck disable=SC2086
    wait $PIDS 2>/dev/null || true
}

trap cleanup EXIT
trap 'exit 143' INT TERM

# A dead child stays a zombie until reaped, and kill -0 still succeeds on
# zombies, so also check the process state in /proc.
is_running() {
    kill -0 "$1" 2>/dev/null || return 1
    if [ -r "/proc/$1/stat" ]; then
        state=$(sed 's/^.*) //' "/proc/$1/stat" | cut -d ' ' -f 1)
        [ "$state" != "Z" ] || return 1
    fi
    return 0
}

# POSIX-compatible polling: exit if any child process dies.
while :; do
    for pid in $PIDS; do
        if ! is_running "$pid"; then
            echo "Process $pid exited; shutting down" >&2
            exit 1
        fi
    done
    sleep 2
done
