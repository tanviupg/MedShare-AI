"""Extract visible medicine package text; pharmacists remain responsible for verification."""
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from typing import Protocol

from app.core.config import get_settings

FIELDS = ("medicine_name", "strength", "dosage_form", "manufacturer", "batch_number", "expiry_date", "quantity", "packaging_type")
MIN_FIELD_CONFIDENCE = 0.6
MIN_NAME_CONFIDENCE = 0.85

GEMINI_EXTRACTION_PROMPT = """You are extracting information visible in a medicine package/strip image.
ONLY return information that is actually visible/readable in the supplied image.
Do NOT guess. Do NOT infer missing information. Do NOT use medical knowledge to fill gaps.
Do NOT invent medicine names, strengths, manufacturers, batches, expiry dates, or quantities.
If a field cannot be confidently read from the image, return null.
Do not diagnose a disease or recommend treatment.
Return only the requested structured JSON."""

GEMINI_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "medicine_name": {"type": "STRING", "nullable": True},
        "strength": {"type": "STRING", "nullable": True},
        "dosage_form": {"type": "STRING", "nullable": True},
        "manufacturer": {"type": "STRING", "nullable": True},
        "batch_number": {"type": "STRING", "nullable": True},
        "expiry_date": {"type": "STRING", "nullable": True},
        "quantity": {"type": "INTEGER", "nullable": True},
        "packaging_type": {"type": "STRING", "nullable": True},
    },
    "required": list(FIELDS),
}


class ExtractionConfigurationError(RuntimeError):
    pass


@dataclass
class ExtractionResult:
    fields: dict
    confidence: dict
    overall_confidence: float | None
    provider: str
    version: str | None = None


class MedicineExtractionProvider(Protocol):
    name: str
    version: str | None

    def extract(self, image: bytes, content_type: str) -> ExtractionResult: ...


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"


@lru_cache(maxsize=1)
def _paddle_ocr():
    from paddleocr import PaddleOCR

    return PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False, show_log=False)


class PaddleOCRExtractionProvider:
    name = "paddleocr"
    version = f"paddleocr-{_package_version('paddleocr')}/paddlepaddle-{_package_version('paddlepaddle')}"

    def extract(self, image: bytes, content_type: str) -> ExtractionResult:
        import cv2
        import numpy as np

        if not image or content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise RuntimeError("Unsupported or empty image")
        decoded = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None:
            raise RuntimeError("Image could not be decoded")
        prepared = _preprocess(decoded)
        raw = _paddle_ocr().ocr(prepared, cls=True)
        lines = _recognized_lines(raw)
        fields, confidence = _map_visible_fields(lines)
        raw_text = "\n".join(text for text, _ in lines)
        recognized_confidence = [score for _, score in lines if score > 0]
        extracted_confidence = [confidence[name] for name in FIELDS if fields[name] is not None]
        overall = round(sum(extracted_confidence) / len(extracted_confidence), 3) if extracted_confidence else 0.0
        if recognized_confidence and overall > 0:
            overall = round(min(overall, sum(recognized_confidence) / len(recognized_confidence)), 3)
        fields["raw_ocr_text"] = raw_text
        return ExtractionResult(fields, confidence, overall, self.name, self.version)


class GeminiExtractionProvider:
    name = "gemini"
    version = None

    def __init__(self, api_key: str, model: str, client=None):
        self._api_key = api_key
        self.model = model
        self._client = client

    def extract(self, image: bytes, content_type: str) -> ExtractionResult:
        if not self._api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        if not image or content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise RuntimeError("Unsupported or empty image")

        try:
            from google import genai
            from google.genai import types

            if self._client is None:
                self._client = genai.Client(
                    api_key=self._api_key,
                    http_options=types.HttpOptions(timeout=45_000),
                )
            response = self._client.models.generate_content(
                model=self.model,
                contents=[
                    GEMINI_EXTRACTION_PROMPT,
                    types.Part.from_bytes(data=image, mime_type=content_type),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GEMINI_RESPONSE_SCHEMA,
                ),
            )
            response_text = response.text
            if not isinstance(response_text, str) or not response_text.strip():
                raise ValueError("Empty structured response")
            fields = _parse_gemini_fields(response_text)
        except Exception as exc:
            raise RuntimeError("Gemini could not extract this image") from exc

        fields["raw_ocr_text"] = None
        # Gemini does not expose calibrated OCR-character confidence scores.
        confidence = {field: None for field in FIELDS}
        return ExtractionResult(fields, confidence, None, self.name, self.model)


def _parse_gemini_fields(response_text: str) -> dict:
    text = response_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Malformed structured response") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Structured response must be an object")

    fields = {field: None for field in FIELDS}
    for field in FIELDS:
        value = parsed.get(field)
        if field == "quantity":
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                fields[field] = value
        elif isinstance(value, str) and value.strip():
            fields[field] = value.strip()
    return fields


def _preprocess(image):
    import cv2

    height, width = image.shape[:2]
    largest = max(height, width)
    if largest > 2400:
        scale = 2400 / largest
        image = cv2.resize(image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    elif largest < 1200:
        scale = min(2.0, 1200 / largest)
        image = cv2.resize(image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)


def _recognized_lines(result) -> list[tuple[str, float]]:
    if not result or not isinstance(result, list):
        return []
    page = result[0]
    if not page or not isinstance(page, list):
        return []
    lines = []
    for row in page:
        try:
            text, score = row[1]
            text = text.strip()
            score = float(score)
        except (IndexError, TypeError, ValueError):
            continue
        if text and 0.0 <= score <= 1.0:
            lines.append((text, score))
    return lines


def _put(fields: dict, confidence: dict, name: str, value, score: float) -> None:
    if value is not None and score >= MIN_FIELD_CONFIDENCE:
        fields[name] = value
        confidence[name] = round(score, 3)


def _map_visible_fields(lines: list[tuple[str, float]]) -> tuple[dict, dict]:
    fields = {name: None for name in FIELDS}
    confidence = {name: 0.0 for name in FIELDS}
    if not lines:
        return fields, confidence

    normalized = [(text, score, re.sub(r"\s+", " ", text).strip().upper()) for text, score in lines]
    for text, score, upper in normalized:
        strength = re.search(
            r"(?<![A-Z0-9])\d+(?:\.\d+)?\s*(?:MCG|UG|MG|G|KG|ML|L|IU|%)(?![A-Z])",
            text,
            re.IGNORECASE,
        )
        if strength and fields["strength"] is None:
            _put(fields, confidence, "strength", strength.group(0).strip(), score)

        form = re.search(r"(?<![A-Z])(?:TABLETS?|TABS?|CAPSULES?|CAPS?|SYRUP|SUSPENSION|DROPS?|INJECTION|CREAM|OINTMENT|GEL|SPRAY|POWDER)(?![A-Z])", upper)
        if form and fields["dosage_form"] is None:
            _put(fields, confidence, "dosage_form", form.group(0), score)

        batch = re.search(r"\b(?:BATCH|BATCH\s*(?:NO|NUMBER)|LOT|LOT\s*(?:NO|NUMBER))\s*[:#.-]?\s*([A-Z0-9][A-Z0-9/-]{2,})\b", upper)
        if batch and fields["batch_number"] is None:
            _put(fields, confidence, "batch_number", batch.group(1), score)

        expiry = re.search(r"\bEXP(?:IRY|IRATION)?\.?\s*[:#.-]?\s*(\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2})\b", upper)
        if expiry and fields["expiry_date"] is None and _valid_expiry_token(expiry.group(1)):
            _put(fields, confidence, "expiry_date", expiry.group(1), score)

        quantity = re.search(r"\b(\d{1,4})\s*(?:TABLETS?|TABS?|CAPSULES?|CAPS?|SACHETS?|AMPOULES?|VIALS?|ML)\b", upper)
        if quantity and fields["quantity"] is None:
            _put(fields, confidence, "quantity", int(quantity.group(1)), score)

        package = re.search(r"\b(BLISTER|STRIP|BOTTLE|BOX|CARTON|SACHET|TUBE|VIAL|AMPOULE)\b", upper)
        if package and fields["packaging_type"] is None:
            _put(fields, confidence, "packaging_type", package.group(1).lower(), score)

        manufacturer = re.search(r"\b(?:MANUFACTURER|MFR\.?|MFG\.?\s*BY|MANUFACTURED\s*BY|MARKETED\s*BY)\s*[:#.-]?\s*(.+)$", upper)
        if manufacturer and fields["manufacturer"] is None:
            _put(fields, confidence, "manufacturer", manufacturer.group(1).strip(), score)

    name_labels = (
        re.compile(r"\b(?:MEDICINE|MEDICINAL|PRODUCT|BRAND)\s+NAME\s*[:#.-]?\s*(.+)$"),
        re.compile(r"\bNAME\s*[:#.-]\s*(.+)$"),
    )
    candidates: list[tuple[str, float, int]] = []
    for index, (text, score, upper) in enumerate(normalized):
        for pattern in name_labels:
            match = pattern.search(upper)
            if match:
                candidates.append((text[match.start(1):match.end(1)].strip(), score, index))
                break
    if not candidates:
        non_name_words = {
            "AND", "BEFORE", "CHILDREN", "DAILY", "DOCTOR", "FOR", "KEEP", "OF", "OR",
            "STORE", "TAKE", "THE", "USE", "WATER", "WITH",
        }
        for index, (text, score, upper) in enumerate(normalized):
            letters = re.sub(r"[^A-Z]", "", upper)
            words = re.findall(r"[A-Z]+", upper)
            if (score < MIN_NAME_CONFIDENCE or len(letters) < 8
                    or re.search(r"\d", upper)
                    or len(words) > 3
                    or any(word in non_name_words for word in words)
                    or not (text.isupper() or all(word[:1].isupper() for word in text.split()))
                    or re.search(r"\b(?:TABLETS?|TABS?|CAPSULES?|CAPS?|SYRUP|SUSPENSION|DROPS?|INJECTION|CREAM|OINTMENT|GEL|SPRAY|POWDER|BATCH|LOT|EXP|MFG|MFR|MANUFACTURER|MARKETED)\b", upper)
                    or re.search(r"\b(?:MG|MCG|UG|KG|ML|IU)\b", upper)):
                continue
            candidates.append((text.strip(), score, index))
    if candidates:
        name, score, index = candidates[0]
        # An unlabelled name is accepted only when a clear strength/form line is nearby.
        nearby_product_detail = any(
            other != index and abs(other - index) <= 2
            and (re.search(r"\b\d+(?:\.\d+)?\s*(?:MCG|UG|MG|G|KG|ML|L|IU)\b", normalized[other][2])
                 or re.search(r"\b(?:TABLETS?|TABS?|CAPSULES?|CAPS?)\b", normalized[other][2]))
            for other in range(len(normalized))
        )
        labelled = any(pattern.search(normalized[index][2]) for pattern in name_labels)
        if labelled or nearby_product_detail:
            _put(fields, confidence, "medicine_name", name, score)
    return fields, confidence


def _valid_expiry_token(value: str) -> bool:
    parts = re.split(r"[/-]", value)
    try:
        first, second = int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return False
    if len(parts[0]) == 4:
        return first >= 2000 and 1 <= second <= 12
    return 1 <= first <= 12 and (0 <= second <= 99 or 2000 <= second <= 2100)


def get_extraction_provider() -> MedicineExtractionProvider:
    settings = get_settings()
    provider = settings.medicine_extraction_provider.strip().lower()
    if provider == "gemini":
        return GeminiExtractionProvider(settings.gemini_api_key, settings.gemini_model)
    if provider == "paddleocr":
        return PaddleOCRExtractionProvider()
    raise ExtractionConfigurationError("MEDICINE_EXTRACTION_PROVIDER must be set to 'gemini' or 'paddleocr'.")
