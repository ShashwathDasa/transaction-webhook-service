import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Transaction
from app.queue import transaction_queue
from app.schemas import TransactionWebhook
from app.services.transaction_service import create_transaction
from worker.tasks import process_transaction

router = APIRouter()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db():
    """Provide a database session for the duration of a request."""
    with SessionLocal() as session:
        yield session


@router.post("/webhooks/transactions", status_code=status.HTTP_202_ACCEPTED)
def receive_transaction(payload: TransactionWebhook, response: Response, session: Session = Depends(get_db)):
    """Accept a transaction webhook and schedule asynchronous processing.

       The transaction is saved before its background job is enqueued.
       Repeated transaction IDs reuse the existing transaction record.
    """
    started = time.perf_counter()

    transaction, created = create_transaction(session, payload)

    db_ms = (time.perf_counter() - started) * 1000
    logger.info("webhook_db_ms=%.2f", db_ms)

    queue_started = time.perf_counter()

    # Keep your existing queue-enqueue logic here unchanged.

    queue_ms = (time.perf_counter() - queue_started) * 1000
    logger.info("webhook_queue_ms=%.2f", queue_ms)

    try:
        if created and transaction.status != "PROCESSED":
            transaction_queue.enqueue(process_transaction, transaction.transaction_id,
                                      job_id=f"transaction-{transaction.transaction_id}")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Transaction saved, but job scheduling failed. Retry later.", ) from exc

    response.headers["X-Transaction-Created"] = str(created).lower()
    return {
        "message": "Transaction webhook received",
        "transaction_id": transaction.transaction_id,
        "status": transaction.status,
    }


@router.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: str, session: Session = Depends(get_db)):
    """Retrieve a transaction by ID or return 404 if it does not exist."""
    transaction = session.scalar(
        select(Transaction).where(Transaction.transaction_id == transaction_id))

    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return {
        "transaction_id": transaction.transaction_id,
        "source_account": transaction.source_account,
        "destination_account": transaction.destination_account,
        "amount": transaction.amount,
        "currency": transaction.currency,
        "status": transaction.status,
        "created_at": transaction.created_at,
        "processed_at": transaction.processed_at,
    }
