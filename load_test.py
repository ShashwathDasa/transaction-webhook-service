"""Measure webhook response times under concurrent load.

Every request creates a new transaction, which is queued for background
processing. Running this against a deployment adds TOTAL_REQUESTS jobs to
its queue, delaying other transactions until the workers catch up.

Usage:
    python load_test.py                                  # local service
    python load_test.py https://your-service.example.com # another deployment

Optional environment variables: LOAD_TEST_REQUESTS, LOAD_TEST_CONCURRENCY.
"""
import json
import os
import statistics
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
WEBHOOK_URL = f"{BASE_URL}/v1/webhooks/transactions"

TOTAL_REQUESTS = int(os.environ.get("LOAD_TEST_REQUESTS", "20"))
CONCURRENCY = int(os.environ.get("LOAD_TEST_CONCURRENCY", "10"))
TIMEOUT_SECONDS = 15
LIMIT_MS = 500


def send_webhook(index):
    payload = {
        "transaction_id": f"load-{uuid.uuid4().hex}",
        "source_account": f"account-{index}",
        "destination_account": "merchant-load-test",
        "amount": 100.00,
        "currency": "INR",
    }

    request = Request(
        WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.perf_counter()

    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            response.read()
            status = response.status
    except HTTPError as exc:
        status = exc.code
    except (URLError, TimeoutError, OSError) as exc:
        status = f"ERROR: {exc}"

    elapsed_ms = (time.perf_counter() - started) * 1000
    return status, elapsed_ms


def percentile(values, percentile_value):
    ordered = sorted(values)
    index = max(0, int((percentile_value / 100) * len(ordered) + 0.999999) - 1)
    return ordered[index]


def get_json(path):
    with urlopen(f"{BASE_URL}{path}", timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read())


if __name__ == "__main__":
    print(f"Target: {BASE_URL}")

    # Wake the service first so a cold start is not counted as webhook latency.
    try:
        get_json("/")
        print("Health check: OK")
    except Exception as exc:
        print(f"Health check failed: {exc}")
        raise SystemExit(1)

    print(
        f"\nSending {TOTAL_REQUESTS} unique webhooks "
        f"with concurrency {CONCURRENCY}..."
    )

    results = []
    started = time.perf_counter()

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = [
            executor.submit(send_webhook, i)
            for i in range(TOTAL_REQUESTS)
        ]
        for future in as_completed(futures):
            results.append(future.result())

    total_seconds = time.perf_counter() - started
    latencies = [latency for _, latency in results]
    successes = sum(status == 202 for status, _ in results)
    failures = TOTAL_REQUESTS - successes
    over_limit = sum(latency > LIMIT_MS for latency in latencies)

    print("\n--- Results ---")
    print(f"Requests:       {TOTAL_REQUESTS}")
    print(f"HTTP 202:       {successes}")
    print(f"Other/errors:   {failures}")
    print(f"Over 500 ms:    {over_limit}")
    print(f"Average:        {statistics.mean(latencies):.1f} ms")
    print(f"p95:            {percentile(latencies, 95):.1f} ms")
    print(f"Maximum:        {max(latencies):.1f} ms")
    print(f"Total duration: {total_seconds:.2f} seconds")

    try:
        queue = get_json("/v1/queue")
        print(f"\nQueue now: {queue['queued_jobs']} waiting, {queue['started_jobs']} running "
              f"on {queue['workers']} worker(s). These transactions will be processed in the background.")
    except Exception as exc:
        print(f"\nQueue status unavailable: {exc}")
