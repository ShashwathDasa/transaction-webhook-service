"""Background transaction processing and stale-job recovery."""
import logging
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, update

from app.config import settings
from app.database import SessionLocal
from app.models import Transaction

logger = logging.getLogger(__name__)


def process_transaction(transaction_id: str) -> None:
    """Claim, process, and complete a transaction if the claim remains valid.

    A unique token identifies each processing attempt. This prevents an
    outdated attempt from completing a transaction after its claim has
    been recovered by another worker.
    """
    processing_token = str(uuid4())

    logger.info("worker_started transaction_id=%s", transaction_id)

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
                select(Transaction.transaction_id).where(Transaction.transaction_id == transaction_id))
            if exists is None:
                logger.error("worker_transaction_not_found transaction_id=%s", transaction_id)
                raise ValueError(f"Transaction {transaction_id} not found")

            logger.warning("worker_claim_failed transaction_id=%s", transaction_id)
            return

        logger.info("worker_claimed transaction_id=%s", transaction_id)

    # Step 2: Simulate the external operation.
    time.sleep(settings.processing_delay_seconds)

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
        updated_rows = result.rowcount
        session.commit()

        logger.info("worker_completion transaction_id=%s updated_rows=%s", transaction_id, updated_rows)

        # If no row was updated, this attempt lost ownership.
        if updated_rows == 0:
            logger.warning("worker_lost_claim transaction_id=%s", transaction_id)
            return


def recover_stale_transaction_ids(stale_after_seconds: int = 120) -> list[str]:
    """Reset stale transactions and return their IDs for requeueing."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)

    with SessionLocal() as session:
        statement = (
            update(Transaction)
            .where(Transaction.status == "PROCESSING", Transaction.processing_started_at < cutoff)
            .values(status="RECEIVED", processing_started_at=None, processing_token=None)
            .returning(Transaction.transaction_id)
        )

        transaction_ids = list(session.scalars(statement).all())
        session.commit()

        return transaction_ids


def recover_stale_transactions(stale_after_seconds: int = 120) -> int:
    """Reset stale transactions and return the number recovered."""
    return len(recover_stale_transaction_ids(stale_after_seconds))


def get_stale_received_transaction_ids(stale_after_seconds: int = 120) -> list[str]:
    """Find old RECEIVED transactions that may have missed queue scheduling."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)

    with SessionLocal() as session:
        statement = (
            select(Transaction.transaction_id)
            .where(Transaction.status == "RECEIVED", Transaction.created_at < cutoff)
        )
        return list(session.scalars(statement).all())
