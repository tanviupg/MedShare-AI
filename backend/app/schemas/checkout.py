from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.models import PaymentStatus


class CheckoutResponse(BaseModel):
    id: UUID
    request_id: UUID
    medicine_name: str
    quantity: int
    unit: str
    clinic_name: str
    original_price: Decimal
    discount_percentage: Decimal
    patient_price: Decimal
    amount: Decimal
    currency: str
    payment_status: PaymentStatus
    payment_method: str | None
    created_at: datetime
    paid_at: datetime | None
    is_free: bool
    demo_payment: bool = True
