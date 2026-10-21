from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_webhook_rejects_missing_transaction_id():
    response = client.post("/v1/webhooks/transactions",
                           json={
                               "source_account": "acc_user_789",
                               "destination_account": "acc_merchant_456",
                               "amount": 1500,
                               "currency": "INR",
                           })

    assert response.status_code == 422


def test_webhook_rejects_negative_amount():
    response = client.post("/v1/webhooks/transactions",
                           json={
                               "transaction_id": "txn_invalid_amount",
                               "source_account": "acc_user_789",
                               "destination_account": "acc_merchant_456",
                               "amount": -100,
                               "currency": "INR",
                           })

    assert response.status_code == 422


def test_webhook_rejects_invalid_currency():
    response = client.post("/v1/webhooks/transactions",
                           json={
                               "transaction_id": "txn_invalid_currency",
                               "source_account": "acc_user_789",
                               "destination_account": "acc_merchant_456",
                               "amount": 100,
                               "currency": "INDIA",
                           })

    assert response.status_code == 422
