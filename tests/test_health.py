from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check_returns_healthy():
    response = client.get("/")

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "HEALTHY"

    # Confirm that current_time is a valid ISO-format timestamp.
    datetime.fromisoformat(body["current_time"])
