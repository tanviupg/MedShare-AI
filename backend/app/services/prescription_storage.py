from pathlib import Path
import logging
from fastapi import HTTPException, UploadFile

from app.services.donation_storage import LocalDonationStorage
from app.core.config import get_settings

logger = logging.getLogger(__name__)


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

PRESCRIPTION_CUES = ("PRESCRIPTION", "PRESCRIBER", "DOCTOR", "PHYSICIAN", "PATIENT", "DOSAGE", "RX", "TAKE", "TABLET", "CAPSULE", "SYRUP", "MG", "ML")
CLEARLY_UNRELATED_CUES = ("UTILITY BILL", "ACCOUNT BALANCE", "AMOUNT DUE", "TAX INVOICE", "PAYMENT RECEIPT", "SHIPPING LABEL")
UNRELATED_OCR_CONFIDENCE = 0.85


def _is_decodable_image(content: bytes) -> bool | None:
    try:
        import cv2
        import numpy as np
    except ImportError:
        # Missing local OCR/image dependencies leave content uncertain; they do not
        # prove the uploaded image is corrupt or unrelated.
        return None
    return cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR) is not None


def validate_prescription_image(content: bytes, content_type: str, extractor=None, classifier=None) -> None:
    """Screen image content; uploads are blocked if the required classifier cannot run."""
    if content_type == "application/pdf":
        # PDF rendering is not configured. Keep it for the existing pharmacist review.
        return
    if _is_decodable_image(content) is False:
        raise HTTPException(status_code=415, detail="This image file is damaged or could not be opened. Please upload a valid JPEG or PNG.")
    classification = None
    settings = get_settings()
    if classifier is None:
        try:
            from app.services.prescription_image_classifier import get_prescription_image_classifier
            classifier = get_prescription_image_classifier()
            if classifier is None:
                raise RuntimeError("classifier disabled by configuration")
        except Exception as exc:
            logger.exception("Prescription classifier initialization failed (enabled=%s, model_path=%s)",
                             settings.prescription_image_classifier_enabled,
                             settings.prescription_image_classifier_model_path)
            raise HTTPException(status_code=503, detail="Prescription image screening is unavailable. Contact support; the upload was not stored.") from exc
    try:
        classification = classifier.classify(content)
        logger.info("Prescription classifier inference completed (label=%s, confidence=%.4f, margin=%.4f)",
                    classification.label, classification.confidence, classification.margin)
    except Exception as exc:
        logger.exception("Prescription classifier inference failed")
        raise HTTPException(status_code=503, detail="Prescription image screening failed. The upload was not stored; please try again later.") from exc

    try:
        if extractor is None:
            from app.services.medicine_extraction import PaddleOCRExtractionProvider
            extractor = PaddleOCRExtractionProvider()
        result = extractor.extract(content, content_type)
        text = str(result.fields.get("raw_ocr_text") or "").upper()
    except Exception:
        # OCR failure is not evidence that the image is unrelated. Continue using the
        # independent classifier result, if available, and otherwise leave it for review.
        text = ""
        confidence = 0.0
        logger.warning("Prescription OCR failed; classifier result will determine image screen")
    else:
        confidence = result.fields.get("raw_ocr_confidence")
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0
    has_prescription_cue = any(cue in text for cue in PRESCRIPTION_CUES)
    unrelated_cues = sum(1 for cue in CLEARLY_UNRELATED_CUES if cue in text)
    from app.services.prescription_image_classifier import PRESCRIPTION_LABELS
    confident_prescription_image = (
        classification is not None
        and classification.label in PRESCRIPTION_LABELS
        and classification.confidence >= settings.prescription_image_classifier_min_confidence
        and classification.margin >= settings.prescription_image_classifier_min_margin
    )
    if (
        not confident_prescription_image and not has_prescription_cue
        and unrelated_cues >= 2 and confidence >= UNRELATED_OCR_CONFIDENCE
    ):
        logger.info("Prescription image validation rejected (reason=unrelated_ocr)")
        raise HTTPException(status_code=422, detail="This image appears to show an unrelated document. Please upload a doctor's prescription.")

    if classification is not None:
        from app.services.prescription_image_classifier import UNRELATED_LABELS

        if (
            classification.label in UNRELATED_LABELS
            and classification.confidence >= settings.prescription_image_classifier_min_confidence
            and classification.margin >= settings.prescription_image_classifier_min_margin
        ):
            logger.info("Prescription image validation rejected (reason=classifier, label=%s, confidence=%.4f, margin=%.4f)", classification.label, classification.confidence, classification.margin)
            raise HTTPException(status_code=422, detail="This image does not appear to be a prescription. Please upload a valid doctor's prescription.")
    logger.info("Prescription image validation accepted for pharmacist review (label=%s, confidence=%.4f, margin=%.4f, prescription_cue=%s)",
                classification.label, classification.confidence, classification.margin, has_prescription_cue)


async def store_upload(file: UploadFile) -> tuple[str, str, str, int]:
    content = await file.read(MAX_PRESCRIPTION_BYTES + 1)
    if len(content) > MAX_PRESCRIPTION_BYTES:
        raise HTTPException(status_code=413, detail="Prescription file must be 10 MB or smaller")
    detected = next((mime for mime, (_, valid) in FILE_TYPES.items() if valid(content)), None)
    if not detected or detected != file.content_type:
        raise HTTPException(status_code=415, detail="Only valid PDF, JPEG, and PNG prescription files are accepted")
    validate_prescription_image(content, detected)
    key = storage.save(content, FILE_TYPES[detected][0])
    filename = Path(file.filename or "prescription").name[:255]
    return key, filename, detected, len(content)
