from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Transaction
from app.schemas import TransactionWebhook


def create_transaction(session: Session, payload: TransactionWebhook) -> tuple[Transaction, bool]:
    """Create a transaction if its ID has not been stored already.

        Uses PostgreSQL conflict handling to prevent duplicate transaction
        records when the same transaction ID is submitted multiple times.

        Args:
            session: SQLAlchemy session used for database operations.
            payload: Validated transaction webhook data.

        Returns:
            A tuple containing the stored transaction and a boolean indicating
            whether this call inserted a new record.
        """
    statement = (
        insert(Transaction)
        .values(
            transaction_id=payload.transaction_id,
            source_account=payload.source_account,
            destination_account=payload.destination_account,
            amount=payload.amount,
            currency=payload.currency.upper(),
            status="RECEIVED",
        )
        .on_conflict_do_nothing(index_elements=[Transaction.transaction_id]).returning(Transaction)
    )

    # Returning the full row avoids a second query for new transactions.
    transaction = session.scalars(statement).one_or_none()
    session.commit()

    if transaction is not None:
        return transaction, True

    existing = session.scalar(select(Transaction).where(Transaction.transaction_id == payload.transaction_id))

    return existing, False
