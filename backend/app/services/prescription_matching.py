"""Conservative prescription medicine extraction and request matching."""
import re

MATCH_RESULTS = {"MATCH", "MISMATCH", "UNCERTAIN"}
MIN_MATCH_CONFIDENCE = 0.85


def _normalize(value: str | None) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").casefold()))


def compare_prescription_medicine(extracted: dict, requested_name: str) -> str:
    name = extracted.get("medicine_name")
    confidence = (extracted.get("confidence") or {}).get("medicine_name")
    if not isinstance(name, str) or not name.strip() or not requested_name.strip():
        return "UNCERTAIN"
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        return "UNCERTAIN"
    if confidence < MIN_MATCH_CONFIDENCE:
        return "UNCERTAIN"

    # A known strength conflict is never treated as a name match.
    prescribed_strength = _normalize(extracted.get("strength"))
    requested_strength = _normalize(extracted.get("requested_strength"))
    if prescribed_strength and requested_strength and prescribed_strength != requested_strength:
        return "MISMATCH"
    return "MATCH" if _normalize(name) == _normalize(requested_name) else "MISMATCH"


def extract_and_match_prescription(image: bytes, content_type: str, requested_name: str, requested_strength: str | None = None) -> dict:
    result = {"medicine_name": None, "strength": None, "dosage_form": None,
              "confidence": None, "matching_result": "UNCERTAIN"}
    try:
        from app.services.medicine_extraction import get_extraction_provider
        extracted = get_extraction_provider().extract(image, content_type)
        result.update({"medicine_name": extracted.fields.get("medicine_name"),
                       "strength": extracted.fields.get("strength"),
                       "dosage_form": extracted.fields.get("dosage_form"),
                       "confidence": extracted.confidence.get("medicine_name")})
        result["matching_result"] = compare_prescription_medicine(
            {**result, "confidence": {"medicine_name": result["confidence"]},
             "requested_strength": requested_strength}, requested_name)
    except Exception:
        # OCR/provider failures leave the request for manual review.
        pass
    return result
