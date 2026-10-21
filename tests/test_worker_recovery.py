from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.models import Transaction
from worker.tasks import recover_stale_transactions


def test_recovery_resets_stale_transaction(test_db, monkeypatch):
    monkeypatch.setattr("worker.tasks.SessionLocal", test_db)

    old_time = datetime.now(timezone.utc) - timedelta(minutes=5)

    with test_db() as session:
        session.add(
            Transaction(
                transaction_id="stale_txn_test",
                source_account="acc_source",
                destination_account="acc_destination",
                amount="100.00",
                currency="INR",
                status="PROCESSING",
                processing_started_at=old_time,
            )
        )
        session.commit()

    recovered = recover_stale_transactions(stale_after_seconds=120)

    assert recovered == 1

    with test_db() as session:
        transaction = session.scalar(
            select(Transaction).where(
                Transaction.transaction_id == "stale_txn_test"
            )
        )

        assert transaction.status == "RECEIVED"
        assert transaction.processing_started_at is None


def test_recovery_leaves_recent_transaction_alone(test_db, monkeypatch):
    monkeypatch.setattr("worker.tasks.SessionLocal", test_db)

    recent_time = datetime.now(timezone.utc) - timedelta(seconds=10)

    with test_db() as session:
        session.add(
            Transaction(
                transaction_id="recent_txn_test",
                source_account="acc_source",
                destination_account="acc_destination",
                amount="100.00",
                currency="INR",
                status="PROCESSING",
                processing_started_at=recent_time,
            )
        )
        session.commit()

    recovered = recover_stale_transactions(stale_after_seconds=120)

    assert recovered == 0

    with test_db() as session:
        transaction = session.scalar(
            select(Transaction).where(
                Transaction.transaction_id == "recent_txn_test"
            )
        )

        assert transaction.status == "PROCESSING"


def test_old_worker_cannot_complete_after_new_worker_claims(
        test_db, monkeypatch
):
    monkeypatch.setattr("worker.tasks.SessionLocal", test_db)

    with test_db() as session:
        session.add(
            Transaction(
                transaction_id="ownership_txn_test",
                source_account="acc_source",
                destination_account="acc_destination",
                amount="100.00",
                currency="INR",
                status="PROCESSING",
                processing_started_at=(
                        datetime.now(timezone.utc) - timedelta(minutes=5)
                ),
                processing_token="worker-a-token",
            )
        )
        session.commit()

    # Recovery releases the stale transaction.
    recovered = recover_stale_transactions(stale_after_seconds=120)
    assert recovered == 1

    # Worker B claims the transaction with a new token.
    with test_db() as session:
        transaction = session.scalar(
            select(Transaction).where(
                Transaction.transaction_id == "ownership_txn_test"
            )
        )

        assert transaction.status == "RECEIVED"
        assert transaction.processing_token is None

        transaction.status = "PROCESSING"
        transaction.processing_started_at = datetime.now(timezone.utc)
        transaction.processing_token = "worker-b-token"
        session.commit()

    # Worker A attempts to complete using its old token.
    with test_db() as session:
        result = session.execute(
            update(Transaction)
            .where(
                Transaction.transaction_id == "ownership_txn_test",
                Transaction.status == "PROCESSING",
                Transaction.processing_token == "worker-a-token",
            )
            .values(
                status="PROCESSED",
                processed_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

        assert result.rowcount == 0

    # Worker B still owns the transaction.
    with test_db() as session:
        transaction = session.scalar(
            select(Transaction).where(
                Transaction.transaction_id == "ownership_txn_test"
            )
        )

        assert transaction.status == "PROCESSING"
        assert transaction.processing_token == "worker-b-token"
        assert transaction.processed_at is None
