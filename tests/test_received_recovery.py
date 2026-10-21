from datetime import datetime, timedelta, timezone

from app.models import Transaction
from worker.tasks import get_stale_received_transaction_ids


def test_finds_old_received_transaction(test_db, monkeypatch):
    """Old RECEIVED transactions should be candidates for recovery."""
    monkeypatch.setattr("worker.tasks.SessionLocal", test_db)

    old_time = datetime.now(timezone.utc) - timedelta(minutes=5)

    with test_db() as session:
        session.add(
            Transaction(
                transaction_id="old_received_test",
                source_account="account_a",
                destination_account="account_b",
                amount="100.00",
                currency="INR",
                status="RECEIVED",
                created_at=old_time,
            )
        )
        session.commit()

    transaction_ids = get_stale_received_transaction_ids(stale_after_seconds=120)

    assert "old_received_test" in transaction_ids


def test_ignores_recent_received_transaction(test_db, monkeypatch):
    """Recently received transactions should not be requeued prematurely."""
    monkeypatch.setattr("worker.tasks.SessionLocal", test_db)

    with test_db() as session:
        session.add(
            Transaction(
                transaction_id="recent_received_test",
                source_account="account_a",
                destination_account="account_b",
                amount="100.00",
                currency="INR",
                status="RECEIVED",
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    transaction_ids = get_stale_received_transaction_ids(stale_after_seconds=120)

    assert "recent_received_test" not in transaction_ids
