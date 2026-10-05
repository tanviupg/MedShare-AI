from datetime import date
from uuid import UUID
from decimal import Decimal

from pydantic import BaseModel

from app.models import CommonUseCategory


class PatientMedicineImage(BaseModel):
    image_url: str


class PatientMedicineOption(BaseModel):
    medicine_id: UUID
    medicine_name: str
    common_use_category: CommonUseCategory
    expiry_date: date
    availability: int
    availability_unit: str
    clinic_name: str
    clinic_city: str
    prescription_required: bool
    images: list[PatientMedicineImage]
    original_price: Decimal | None
    discount_percentage: Decimal | None
    patient_price: Decimal | None


class PatientMedicinePage(BaseModel):
    items: list[PatientMedicineOption]
    total: int
    page: int
    page_size: int
