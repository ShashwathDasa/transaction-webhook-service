from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now():
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


class Transaction(Base):
    """Represent a transaction and its asynchronous processing state."""
    __tablename__ = "transactions"
    transaction_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source_account: Mapped[str] = mapped_column(String(128), nullable=False)
    destination_account: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RECEIVED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    processing_token: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
