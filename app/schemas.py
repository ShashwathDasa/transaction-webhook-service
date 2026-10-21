from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

TransactionId = Annotated[str, StringConstraints(min_length=1, max_length=128, strip_whitespace=True)]


class TransactionWebhook(BaseModel):
    """Validate the payload received by the transaction webhook."""
    transaction_id: TransactionId
    source_account: str = Field(min_length=1, max_length=128)
    destination_account: str = Field(min_length=1, max_length=128)
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
