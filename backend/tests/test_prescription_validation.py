import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.services.prescription_storage import store_upload, validate_prescription_image


class FakeOCR:
    def __init__(self, text, confidence=0.99):
        self.text = text
        self.confidence = confidence

    def extract(self, image, content_type):
        return SimpleNamespace(fields={"raw_ocr_text": self.text, "raw_ocr_confidence": self.confidence})


class FakeClassifier:
    def __init__(self, label, confidence=0.94, margin=0.5):
        self.result = SimpleNamespace(label=label, confidence=confidence, margin=margin)

    def classify(self, image):
        return self.result


class PrescriptionContentValidationTests(unittest.TestCase):
    def test_handwritten_like_text_is_sent_to_pharmacist_review(self):
        with patch("app.services.prescription_storage._is_decodable_image", return_value=True):
            validate_prescription_image(
                b"image", "image/png", FakeOCR("Rx take 1 tab daily", confidence=0.31),
                FakeClassifier("handwritten_prescription"),
            )

    def test_printed_prescription_is_sent_to_pharmacist_review(self):
        with patch("app.services.prescription_storage._is_decodable_image", return_value=True):
            validate_prescription_image(
                b"image", "image/png", FakeOCR("DOCTOR PRESCRIPTION PATIENT TAKE 1 TABLET 10 MG"),
                FakeClassifier("printed_prescription"),
            )

    def test_confident_dog_cat_person_and_object_photos_are_rejected(self):
        for label in ("dog", "cat", "person", "unrelated_object"):
            with self.subTest(label=label), \
                    patch("app.services.prescription_storage._is_decodable_image", return_value=True), \
                    self.assertRaises(HTTPException) as raised:
                validate_prescription_image(
                    b"image", "image/png", FakeOCR("", confidence=0), FakeClassifier(label)
                )
            self.assertEqual(raised.exception.status_code, 422)
            self.assertIn("valid doctor's prescription", raised.exception.detail)

    def test_confident_unrelated_document_photo_is_rejected(self):
        with patch("app.services.prescription_storage._is_decodable_image", return_value=True), \
                self.assertRaises(HTTPException):
            validate_prescription_image(
                b"image", "image/png", FakeOCR("", confidence=0), FakeClassifier("unrelated_document")
            )

    def test_low_confidence_ocr_is_uncertain_and_sent_for_review(self):
        with patch("app.services.prescription_storage._is_decodable_image", return_value=True):
            validate_prescription_image(
                b"image", "image/png", FakeOCR("UTILITY BILL ACCOUNT BALANCE", confidence=0.42),
                FakeClassifier("unrelated_document", confidence=0.52, margin=0.03),
            )

    def test_empty_ocr_output_is_uncertain_and_sent_for_review(self):
        with patch("app.services.prescription_storage._is_decodable_image", return_value=True):
            validate_prescription_image(
                b"image", "image/png", FakeOCR("", confidence=0),
                FakeClassifier("unrelated_object", confidence=0.48, margin=0.02),
            )

    def test_ocr_failure_is_uncertain_and_sent_for_review(self):
        class BrokenOCR:
            def extract(self, image, content_type):
                raise RuntimeError("OCR unavailable")

        with patch("app.services.prescription_storage._is_decodable_image", return_value=True):
            validate_prescription_image(
                b"image", "image/png", BrokenOCR(), FakeClassifier("printed_prescription")
            )

    def test_ocr_failure_does_not_override_confident_unrelated_classifier(self):
        class BrokenOCR:
            def extract(self, image, content_type):
                raise RuntimeError("OCR unavailable")

        with patch("app.services.prescription_storage._is_decodable_image", return_value=True), \
                self.assertRaises(HTTPException):
            validate_prescription_image(
                b"image", "image/png", BrokenOCR(), FakeClassifier("cat")
            )

    def test_confident_unrelated_document_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            with patch("app.services.prescription_storage._is_decodable_image", return_value=True), \
                    patch("app.services.prescription_image_classifier.get_prescription_image_classifier", return_value=FakeClassifier("unrelated_document")):
                validate_prescription_image(b"image", "image/png", FakeOCR("UTILITY BILL ACCOUNT BALANCE AMOUNT DUE"))
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("unrelated document", raised.exception.detail)


class PrescriptionFileValidationTests(unittest.IsolatedAsyncioTestCase):
    async def upload(self, content, content_type):
        return await store_upload(UploadFile(
            filename="upload.bin", file=__import__("io").BytesIO(content),
            headers=Headers({"content-type": content_type}),
        ))

    async def test_corrupt_file_is_rejected(self):
        with patch("app.services.prescription_storage._is_decodable_image", return_value=False), \
                self.assertRaises(HTTPException) as raised:
            await self.upload(b"\x89PNG\r\n\x1a\nnot a decodable image", "image/png")
        self.assertEqual(raised.exception.status_code, 415)

    async def test_unsupported_file_type_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            await self.upload(b"GIF89a", "image/gif")
        self.assertEqual(raised.exception.status_code, 415)

    async def test_image_ocr_is_used_during_upload(self):
        png = b"\x89PNG\r\n\x1a\nfixture"
        with patch("app.services.prescription_storage.validate_prescription_image") as validate, \
                patch("app.services.prescription_storage.storage.save", return_value="stored-key"):
            await self.upload(png, "image/png")
        validate.assert_called_once_with(png, "image/png")

    async def test_confident_dog_classifier_result_rejects_before_file_storage(self):
        png = b"\x89PNG\r\n\x1a\nfixture"
        classifier = FakeClassifier("dog")
        with patch("app.services.prescription_storage._is_decodable_image", return_value=True), \
                patch("app.services.prescription_storage.get_settings") as settings, \
                patch("app.services.prescription_storage.storage.save") as save, \
                patch("app.services.medicine_extraction.PaddleOCRExtractionProvider", return_value=FakeOCR("", 0)):
            settings.return_value.prescription_image_classifier_min_confidence = 0.75
            settings.return_value.prescription_image_classifier_min_margin = 0.20
            with patch("app.services.prescription_storage.get_settings", return_value=settings.return_value), \
                    patch("app.services.prescription_image_classifier.get_prescription_image_classifier", return_value=classifier), \
                    self.assertRaises(HTTPException) as raised:
                await self.upload(png, "image/png")
        self.assertEqual(raised.exception.status_code, 422)
        save.assert_not_called()

    async def test_unavailable_classifier_blocks_before_file_storage(self):
        png = b"\x89PNG\r\n\x1a\nfixture"
        with patch("app.services.prescription_storage._is_decodable_image", return_value=True), \
                patch("app.services.prescription_storage.storage.save") as save, \
                patch("app.services.prescription_image_classifier.get_prescription_image_classifier", side_effect=ImportError("missing transformers")), \
                self.assertRaises(HTTPException) as raised:
            await self.upload(png, "image/png")
        self.assertEqual(raised.exception.status_code, 503)
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
