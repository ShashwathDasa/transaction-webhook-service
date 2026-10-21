from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.models import Transaction
from app.routes.transactions import get_db
from app.queue import transaction_queue


def test_duplicate_transaction_is_stored_once(test_db, monkeypatch):
    def override_get_db():
        with test_db() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Do not send real jobs to Redis during this test.
    monkeypatch.setattr(transaction_queue, "enqueue", lambda *args, **kwargs: None)

    payload = {
        "transaction_id": "txn_idempotency_test",
        "source_account": "acc_source",
        "destination_account": "acc_destination",
        "amount": "100.00",
        "currency": "INR",
    }

    try:
        with TestClient(app) as client:
            first = client.post("/v1/webhooks/transactions", json=payload)
            second = client.post("/v1/webhooks/transactions", json=payload)

        assert first.status_code == 202
        assert second.status_code == 202

        with test_db() as session:
            count = session.scalar(
                select(func.count())
                .select_from(Transaction)
                .where(Transaction.transaction_id == "txn_idempotency_test")
            )

        assert count == 1

    finally:
        app.dependency_overrides.pop(get_db, None)


def test_duplicate_webhook_enqueues_only_once(test_db, monkeypatch):
    def override_get_db():
        with test_db() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    enqueue_calls = []

    def fake_enqueue(*args, **kwargs):
        enqueue_calls.append((args, kwargs))

    monkeypatch.setattr(transaction_queue, "enqueue", fake_enqueue)

    payload = {
        "transaction_id": "txn_enqueue_once",
        "source_account": "acc_source",
        "destination_account": "acc_destination",
        "amount": "100.00",
        "currency": "INR",
    }

    try:
        with TestClient(app) as client:
            first = client.post("/v1/webhooks/transactions", json=payload)
            second = client.post("/v1/webhooks/transactions", json=payload)

        assert first.status_code == 202
        assert second.status_code == 202
        assert len(enqueue_calls) == 1

    finally:
        app.dependency_overrides.pop(get_db, None)
