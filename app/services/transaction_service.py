from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Transaction
from app.schemas import TransactionWebhook


def create_transaction(session: Session, payload: TransactionWebhook) -> tuple[Transaction, bool]:
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
        .on_conflict_do_nothing(
            index_elements=[Transaction.transaction_id]
        )
        .returning(Transaction.transaction_id)
    )

    inserted_id = session.execute(statement).scalar_one_or_none()
    session.commit()

    transaction = session.scalar(select(Transaction).where(Transaction.transaction_id == payload.transaction_id))

    return transaction, inserted_id is not None
