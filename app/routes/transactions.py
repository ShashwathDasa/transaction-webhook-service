import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Response, status
from rq import Worker
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Transaction
from app.queue import transaction_queue
from app.schemas import TransactionWebhook
from app.services.transaction_service import create_transaction
from worker.tasks import process_transaction

router = APIRouter()
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
    logger.info("webhook_db_ms=%.3f transaction_id=%s created=%s status=%s", db_ms, transaction.transaction_id, created,
                transaction.status)

    try:
        if created and transaction.status != "PROCESSED":
            queue_started = time.perf_counter()

            transaction_queue.enqueue(process_transaction, transaction.transaction_id,
                                      job_id=f"transaction-{transaction.transaction_id}")

            queue_ms = (time.perf_counter() - queue_started) * 1000

            logger.info("webhook_queue_ms=%.3f transaction_id=%s", queue_ms, transaction.transaction_id)
        else:
            logger.info("webhook_enqueue_skipped transaction_id=%s created=%s status=%s", transaction.transaction_id,
                        created, transaction.status)

    except Exception as exc:
        logger.exception("webhook_enqueue_failed transaction_id=%s", transaction.transaction_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Transaction saved, but job scheduling failed. Retry later.",
        ) from exc

    response.headers["X-Transaction-Created"] = str(created).lower()

    return {
        "message": "Transaction webhook received",
        "transaction_id": transaction.transaction_id,
        "status": transaction.status,
    }


@router.get("/queue")
def get_queue_status():
    """Report how many jobs are waiting and how many workers are busy."""
    try:
        workers = Worker.all(queue=transaction_queue)
        return {
            "queue": transaction_queue.name,
            "queued_jobs": transaction_queue.count,
            "started_jobs": transaction_queue.started_job_registry.count,
            "workers": len(workers),
            "busy_workers": sum(worker.get_state() == "busy" for worker in workers),
        }
    except Exception as exc:
        logger.exception("queue_status_failed")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Queue status is unavailable.") from exc


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
