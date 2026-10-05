from pathlib import Path
from fastapi import HTTPException, UploadFile

from app.services.donation_storage import LocalDonationStorage
from app.core.config import get_settings


# Separate root from donor package images so prescription documents never share
# the static/public image namespace. Reads are only exposed through authorized routes.
class LocalPrescriptionStorage(LocalDonationStorage):
    def __init__(self):
        super().__init__(get_settings().upload_dir / "prescriptions")


storage = LocalPrescriptionStorage()

MAX_PRESCRIPTION_BYTES = 10 * 1024 * 1024
FILE_TYPES = {
    "application/pdf": (".pdf", lambda data: data.startswith(b"%PDF-")),
    "image/jpeg": (".jpg", lambda data: data.startswith(b"\xff\xd8\xff")),
    "image/png": (".png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
}


async def store_upload(file: UploadFile) -> tuple[str, str, str, int]:
    content = await file.read(MAX_PRESCRIPTION_BYTES + 1)
    if len(content) > MAX_PRESCRIPTION_BYTES:
        raise HTTPException(status_code=413, detail="Prescription file must be 10 MB or smaller")
    detected = next((mime for mime, (_, valid) in FILE_TYPES.items() if valid(content)), None)
    if not detected or detected != file.content_type:
        raise HTTPException(status_code=415, detail="Only valid PDF, JPEG, and PNG prescription files are accepted")
    key = storage.save(content, FILE_TYPES[detected][0])
    filename = Path(file.filename or "prescription").name[:255]
    return key, filename, detected, len(content)
