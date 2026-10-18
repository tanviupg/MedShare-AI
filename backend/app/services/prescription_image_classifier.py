"""Local CLIP image screening. This classifies image content, not prescription authenticity."""
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
import logging
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)


PROMPTS = {
    "printed_prescription": "a photo of a printed doctor's prescription on paper",
    "handwritten_prescription": "a photo of a handwritten doctor's prescription on paper",
    "dog": "a photo of a dog",
    "cat": "a photo of a cat",
    "person": "a photo of a person",
    "unrelated_document": "a photo of an unrelated document such as a bill or receipt",
    "unrelated_object": "a photo of an unrelated object, not a document",
}

PRESCRIPTION_LABELS = {"printed_prescription", "handwritten_prescription"}
UNRELATED_LABELS = {"dog", "cat", "person", "unrelated_document", "unrelated_object"}

MEDICINE_PHOTO_PROMPTS = {
    "medicine_packaging": (
        "a photo of a pharmaceutical medicine box",
        "a photo of medicine packaging",
        "a photo of a medicine blister pack with tablets sealed in foil cavities",
        "a close-up photo of medicine in its original package",
        "a photo of a pharmacy medicine carton or packet",
        "a photo of labeled medicine bottle packaging",
        "a package of pharmaceutical tablets",
        "a photo of packaged medication ready for a patient",
    ),
    "unrelated": (
        "a photo of a dog",
        "a close-up photo of a pet dog",
        "a photo of a dog outdoors",
        "a photo of a cat",
        "a photo of a pet cat",
        "a photo of a person or people",
        "a photo of a landscape, scenery, or nature",
        "a photo of an unrelated everyday object or document",
    ),
    "ambiguous": (
        "a blurry unclear photo where the subject cannot be identified",
        "a photograph of an object too small or indistinct to classify",
        "a close-up photo with no recognizable context",
        "an image where the main subject is unclear",
        "an out of focus photo",
        "a dark photo that is difficult to identify",
        "a low quality unclear photograph",
        "a cropped photo with no recognizable subject",
    ),
}


@dataclass(frozen=True)
class ImageClassification:
    label: str
    confidence: float
    margin: float


class LocalClipPrescriptionClassifier:
    def __init__(self, model_path: str):
        logger.info("Initializing local prescription classifier (model_path=%s, exists=%s)",
                    model_path, Path(model_path).exists())
        from transformers import CLIPModel, CLIPProcessor

        # local_files_only prevents an upload request from fetching model weights.
        self.processor = CLIPProcessor.from_pretrained(model_path, local_files_only=True)
        self.model = CLIPModel.from_pretrained(model_path, local_files_only=True)
        self.model.eval()
        self.device = "cpu"

    def classify(self, image_bytes: bytes) -> ImageClassification:
        import torch
        from PIL import Image, ImageOps

        with Image.open(BytesIO(image_bytes)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
        inputs = self.processor(
            text=list(PROMPTS.values()), images=image, return_tensors="pt", padding=True
        )
        with torch.inference_mode():
            scores = self.model(**inputs).logits_per_image.softmax(dim=1)[0]
        ranked = sorted(enumerate(scores.tolist()), key=lambda item: item[1], reverse=True)
        best_index, confidence = ranked[0]
        margin = confidence - ranked[1][1] if len(ranked) > 1 else confidence
        return ImageClassification(list(PROMPTS)[best_index], float(confidence), float(margin))

    def classify_medicine_photo(self, image_bytes: bytes) -> ImageClassification:
        """Classify medicine packaging or clearly unrelated content without identifying medicine."""
        import torch
        from PIL import Image, ImageOps

        with Image.open(BytesIO(image_bytes)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
        texts = [prompt for prompts in MEDICINE_PHOTO_PROMPTS.values() for prompt in prompts]
        inputs = self.processor(text=texts, images=image, return_tensors="pt", padding=True)
        with torch.inference_mode():
            prompt_scores = self.model(**inputs).logits_per_image[0]
        class_scores = []
        offset = 0
        for prompts in MEDICINE_PHOTO_PROMPTS.values():
            class_scores.append(prompt_scores[offset:offset + len(prompts)].max())
            offset += len(prompts)
        probabilities = torch.stack(class_scores).softmax(dim=0).tolist()
        ranked = sorted(enumerate(probabilities), key=lambda item: item[1], reverse=True)
        best_index, confidence = ranked[0]
        margin = confidence - ranked[1][1]
        return ImageClassification(list(MEDICINE_PHOTO_PROMPTS)[best_index], float(confidence), float(margin))


@lru_cache(maxsize=2)
def _load_classifier(model_path: str):
    return LocalClipPrescriptionClassifier(model_path)


def get_prescription_image_classifier():
    settings = get_settings()
    if not settings.prescription_image_classifier_enabled:
        logger.error("Prescription classifier is disabled by configuration")
        return None
    try:
        classifier = _load_classifier(str(settings.prescription_image_classifier_model_path))
    except Exception:
        logger.exception("Local prescription classifier initialization failed (model_path=%s)",
                         settings.prescription_image_classifier_model_path)
        raise
    logger.info("Local prescription classifier is ready (model_path=%s)", settings.prescription_image_classifier_model_path)
    return classifier
