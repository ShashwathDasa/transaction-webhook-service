from fastapi.testclient import TestClient

from app.main import app
from app.routes.transactions import get_db
from app.queue import transaction_queue


def test_webhook_returns_202_without_waiting_for_processing(test_db, monkeypatch):
    def override_get_db():
        with test_db() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Keep this test independent of Redis and the worker.
    monkeypatch.setattr(transaction_queue, "enqueue", lambda *args, **kwargs: None)

    payload = {
        "transaction_id": "txn_response_test",
        "source_account": "acc_source",
        "destination_account": "acc_destination",
        "amount": "100.00",
        "currency": "INR",
    }

    try:
        with TestClient(app) as client:
            response = client.post("/v1/webhooks/transactions", json=payload)

        assert response.status_code == 202

    finally:
        app.dependency_overrides.pop(get_db, None)
