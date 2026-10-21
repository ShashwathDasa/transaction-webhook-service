from datetime import datetime, timezone

from sqlalchemy import select

from app.models import Transaction
from app.database import SessionLocal
from worker.tasks import process_transaction


def test_duplicate_job_does_not_process_transaction_again(
        test_db, monkeypatch
):
    transaction_id = "worker_duplicate_test"

    with test_db() as session:
        session.add(
            Transaction(
                transaction_id=transaction_id,
                source_account="acc_source",
                destination_account="acc_destination",
                amount="100.00",
                currency="INR",
                status="PROCESSING",
            )
        )
        session.commit()

    # Use the test database for the worker.
    monkeypatch.setattr(
        "worker.tasks.SessionLocal",
        test_db,
    )

    # The duplicate job must return without sleeping.
    def unexpected_sleep(_seconds):
        raise AssertionError("Duplicate job should not sleep")

    monkeypatch.setattr("worker.tasks.time.sleep", unexpected_sleep)

    process_transaction(transaction_id)

    with test_db() as session:
        transaction = session.scalar(
            select(Transaction).where(
                Transaction.transaction_id == transaction_id
            )
        )

        assert transaction.status == "PROCESSING"
        assert transaction.processed_at is None
