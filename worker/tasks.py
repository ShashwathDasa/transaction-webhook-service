import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, update

from app.database import SessionLocal
from app.models import Transaction


def process_transaction(transaction_id: str):
    # Each attempt gets a unique ownership token.
    processing_token = str(uuid4())

    # Step 1: Atomically claim a RECEIVED transaction.
    with SessionLocal() as session:
        statement = (
            update(Transaction)
            .where(Transaction.transaction_id == transaction_id, Transaction.status == "RECEIVED")
            .values(status="PROCESSING", processing_started_at=datetime.now(timezone.utc),
                    processing_token=processing_token)
            .returning(Transaction.transaction_id)
        )

        claimed_id = session.execute(statement).scalar_one_or_none()
        session.commit()

        if claimed_id is None:
            exists = session.scalar(
                select(Transaction.transaction_id).where(Transaction.transaction_id == transaction_id)
            )
            if exists is None:
                raise ValueError(f"Transaction {transaction_id} not found")
            return

    # Step 2: Simulate the external operation.
    time.sleep(30)

    # Step 3: Complete only if this attempt still owns the claim.
    with SessionLocal() as session:
        statement = (
            update(Transaction)
            .where(Transaction.transaction_id == transaction_id, Transaction.status == "PROCESSING",
                   Transaction.processing_token == processing_token)
            .values(status="PROCESSED", processed_at=datetime.now(timezone.utc), processing_started_at=None,
                    processing_token=None)
        )

        result = session.execute(statement)
        session.commit()

        # If no row was updated, this attempt lost ownership.
        if result.rowcount == 0:
            return


def recover_stale_transactions(stale_after_seconds: int = 120) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)

    with SessionLocal() as session:
        statement = (
            update(Transaction)
            .where(Transaction.status == "PROCESSING", Transaction.processing_started_at < cutoff)
            .values(status="RECEIVED", processing_started_at=None, processing_token=None)
        )

        result = session.execute(statement)
        session.commit()

        return result.rowcount or 0
