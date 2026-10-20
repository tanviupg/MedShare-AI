import logging

from fastapi import HTTPException

from app.core.config import get_settings

logger = logging.getLogger(__name__)

UNRELATED_IMAGE_MESSAGE = (
    "This photo does not appear to show medicine or medicine packaging. "
    "Please upload a clear photo of the medicine."
)
AMBIGUOUS_IMAGE_MESSAGE = (
    "We could not clearly identify medicine packaging in this photo. "
    "Please upload a clearer photo of the medicine or its packaging."
)


def screen_medicine_photo(content: bytes, classifier=None) -> None:
    """Require a confident local content classification before storing a donor photo."""
    settings = get_settings()

    if not settings.prescription_image_classifier_enabled:
        logger.warning(
            "Medicine photo screening is disabled; "
            "accepting upload without image classification."
       )
        return

    if classifier is None:
        try:
            from app.services.prescription_image_classifier import get_prescription_image_classifier

            classifier = get_prescription_image_classifier()
            if classifier is None:
                raise RuntimeError("local image classifier is disabled")
        except Exception as exc:
            logger.exception("Donation image classifier initialization failed")
            raise HTTPException(
                status_code=503,
                detail="Medicine photo screening is unavailable. The upload was not stored; please try again later.",
            ) from exc

    try:
        result = classifier.classify_medicine_photo(content)
    except Exception as exc:
        logger.exception("Donation image classifier inference failed")
        raise HTTPException(
            status_code=503,
            detail="Medicine photo screening failed. The upload was not stored; please try again later.",
        ) from exc

    confidence_threshold = settings.prescription_image_classifier_min_confidence
    margin_threshold = settings.prescription_image_classifier_min_margin
    confidently_unrelated = (
        result.label == "unrelated"
        and result.confidence >= confidence_threshold
        and result.margin >= margin_threshold
    )
    if confidently_unrelated:
        logger.info(
            "Donation image rejected by content screening (label=%s, confidence=%.4f, margin=%.4f)",
            result.label,
            result.confidence,
            result.margin,
        )
        raise HTTPException(status_code=415, detail=UNRELATED_IMAGE_MESSAGE)

    confidently_packaged = (
        result.label == "medicine_packaging"
        and result.confidence >= confidence_threshold
        and result.margin >= margin_threshold
    )
    if not confidently_packaged:
        logger.info(
            "Donation image requires clearer content (label=%s, confidence=%.4f, margin=%.4f)",
            result.label,
            result.confidence,
            result.margin,
        )
        raise HTTPException(status_code=415, detail=AMBIGUOUS_IMAGE_MESSAGE)
