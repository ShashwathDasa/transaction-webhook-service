from fastapi.testclient import TestClient
from rq import Queue

from app.main import app
from app.queue import redis_connection
from app.routes import transactions


def test_queue_status_reports_queue_and_worker_counts(monkeypatch):
    # Use a separate queue so running workers don't consume the test job.
    test_queue = Queue("transactions-queue-status-test", connection=redis_connection)
    test_queue.empty()
    monkeypatch.setattr(transactions, "transaction_queue", test_queue)

    test_queue.enqueue("worker.tasks.process_transaction", "txn_queue_status_test")

    try:
        with TestClient(app) as client:
            response = client.get("/v1/queue")

        assert response.status_code == 200
        assert response.json() == {
            "queue": "transactions-queue-status-test",
            "queued_jobs": 1,
            "started_jobs": 0,
            "workers": 0,
            "busy_workers": 0,
        }

    finally:
        test_queue.empty()


def test_queue_status_returns_503_when_redis_is_unavailable(monkeypatch):
    def fail(*args, **kwargs):
        raise ConnectionError("Redis is down")

    monkeypatch.setattr(transactions.Worker, "all", fail)

    with TestClient(app) as client:
        response = client.get("/v1/queue")

    assert response.status_code == 503
