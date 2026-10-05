from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DispensingResponse(BaseModel):
    medicine_name: str
    strength: str | None
    dosage_form: str | None
    clinic_name: str
    quantity: int
    unit: str
    pickup_code: str
    status: str
    requested_at: datetime
    dispensed_at: datetime | None


class PatientDispensingResponse(DispensingResponse):
    pass


class PharmacistDispensingResponse(DispensingResponse):
    request_id: UUID
    patient_name: str
    patient_city: str | None
    patient_phone: str | None
    prescription_required: bool | None
    prescription_status: str | None
