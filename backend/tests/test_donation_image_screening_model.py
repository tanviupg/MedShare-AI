import importlib.util
from io import BytesIO
from pathlib import Path
import unittest

from fastapi import HTTPException
from PIL import Image, ImageDraw

from app.services.donation_image_screening import (
    AMBIGUOUS_IMAGE_MESSAGE,
    UNRELATED_IMAGE_MESSAGE,
    screen_medicine_photo,
)
from app.services.prescription_image_classifier import LocalClipPrescriptionClassifier


MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "clip-vit-base-patch32"
LOCAL_UPLOADS = Path(__file__).resolve().parents[1] / "uploads"
MODEL_AVAILABLE = (
    MODEL_PATH.joinpath("config.json").is_file()
    and MODEL_PATH.joinpath("pytorch_model.bin").is_file()
    and importlib.util.find_spec("torch") is not None
    and importlib.util.find_spec("transformers") is not None
)


@unittest.skipUnless(MODEL_AVAILABLE, "Local CLIP weights or optional inference dependencies are unavailable")
class LocalDonationImageModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classifier = LocalClipPrescriptionClassifier(str(MODEL_PATH))

    @staticmethod
    def medicine_carton_fixture() -> Image.Image:
        image = Image.new("RGB", (640, 420), (235, 235, 230))
        draw = ImageDraw.Draw(image)
        draw.polygon([(130, 110), (455, 80), (520, 310), (160, 350)], fill=(250, 250, 247), outline=(30, 80, 90), width=8)
        draw.polygon([(455, 80), (520, 310), (570, 270), (500, 48)], fill=(205, 220, 216), outline=(30, 80, 90), width=5)
        draw.polygon([(130, 110), (455, 80), (500, 48), (175, 78)], fill=(220, 234, 231), outline=(30, 80, 90), width=5)
        draw.rectangle((150, 210, 495, 245), fill=(35, 105, 93))
        draw.text((185, 154), "MEDICINE TABLETS", fill=(20, 45, 42))
        draw.text((190, 265), "PHARMACEUTICAL PACKAGE", fill=(20, 45, 42))
        return image

    def test_medicine_carton_content_passes_as_jpeg_png_and_webp(self):
        image = self.medicine_carton_fixture()
        for image_format in ("JPEG", "PNG", "WEBP"):
            with self.subTest(image_format=image_format):
                output = BytesIO()
                image.save(output, format=image_format)
                screen_medicine_photo(output.getvalue(), self.classifier)

    def test_clear_local_dog_jpeg_is_rejected_when_fixture_is_available(self):
        dog_content = None
        for path in LOCAL_UPLOADS.iterdir() if LOCAL_UPLOADS.is_dir() else ():
            if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg"}:
                continue
            content = path.read_bytes()
            result = self.classifier.classify(content)
            if result.label == "dog" and result.confidence >= 0.75 and result.margin >= 0.20:
                dog_content = content
                break
        if dog_content is None:
            self.skipTest("No local real dog JPEG fixture is available; none is committed to the repository")
        with self.assertRaises(HTTPException) as raised:
            screen_medicine_photo(dog_content, self.classifier)
        self.assertEqual(raised.exception.status_code, 415)
        self.assertEqual(raised.exception.detail, UNRELATED_IMAGE_MESSAGE)

    def test_local_webp_packaging_photo_is_accepted_when_fixture_is_available(self):
        for path in LOCAL_UPLOADS.iterdir() if LOCAL_UPLOADS.is_dir() else ():
            if not path.is_file() or path.suffix.lower() != ".webp":
                continue
            content = path.read_bytes()
            result = self.classifier.classify_medicine_photo(content)
            if result.label == "medicine_packaging" and result.confidence >= 0.75 and result.margin >= 0.20:
                screen_medicine_photo(content, self.classifier)
                return
        self.skipTest("No local real WebP medicine-packaging fixture is available")

    def test_ambiguous_image_requires_a_clearer_photo(self):
        image = Image.new("RGB", (640, 420), (128, 128, 128))
        output = BytesIO()
        image.save(output, format="JPEG")
        with self.assertRaises(HTTPException) as raised:
            screen_medicine_photo(output.getvalue(), self.classifier)
        self.assertEqual(raised.exception.status_code, 415)
        self.assertEqual(raised.exception.detail, AMBIGUOUS_IMAGE_MESSAGE)


if __name__ == "__main__":
    unittest.main()
