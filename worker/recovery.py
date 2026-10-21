"""Periodically recover transactions that need background scheduling."""

import logging
import time
from uuid import uuid4

from app.config import settings
from app.queue import transaction_queue
from worker.tasks import get_stale_received_transaction_ids, process_transaction, recover_stale_transaction_ids

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ACTIVE_JOB_STATUSES = {"queued", "started", "deferred", "scheduled"}


def enqueue_if_not_active(transaction_id: str) -> bool:
    """Enqueue a transaction unless its original job is already active."""
    job_id = f"transaction-{transaction_id}"
    existing_job = transaction_queue.fetch_job(job_id)

    if existing_job is not None:
        job_status = existing_job.get_status(refresh=True)
        status_value = getattr(job_status, "value", job_status)

        if status_value in ACTIVE_JOB_STATUSES:
            if status_value != "started":
                return False

    transaction_queue.enqueue(process_transaction, transaction_id, job_id=job_id)
    return True


def run_recovery() -> None:
    """Continuously find and reschedule transactions needing processing."""
    logger.info("Transaction recovery service started")

    while True:
        try:
            recovered_processing_ids = recover_stale_transaction_ids(settings.stale_transaction_seconds)

            for transaction_id in recovered_processing_ids:
                # Use a fresh ID because the original job may still be running.
                transaction_queue.enqueue(process_transaction, transaction_id,
                                          job_id=f"recovery-{transaction_id}-{uuid4()}")
                logger.info("Requeued stale PROCESSING transaction: %s", transaction_id)

            stale_received_ids = get_stale_received_transaction_ids(settings.stale_transaction_seconds)

            for transaction_id in stale_received_ids:
                # Avoid scheduling the same transaction twice in this cycle.
                if transaction_id in recovered_processing_ids:
                    continue

                if enqueue_if_not_active(transaction_id):
                    logger.info("Requeued stale RECEIVED transaction: %s", transaction_id)

        except Exception:
            logger.exception("Transaction recovery cycle failed")

        time.sleep(settings.recovery_interval_seconds)


if __name__ == "__main__":
    run_recovery()
