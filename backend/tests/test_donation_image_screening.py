import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.services.donation_image_screening import (
    AMBIGUOUS_IMAGE_MESSAGE,
    UNRELATED_IMAGE_MESSAGE,
    screen_medicine_photo,
)


class FakeClassifier:
    def __init__(self, label, confidence, margin):
        self.result = SimpleNamespace(label=label, confidence=confidence, margin=margin)

    def classify_medicine_photo(self, content):
        return self.result


class DonationImageScreeningTests(unittest.TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(
            prescription_image_classifier_min_confidence=0.75,
            prescription_image_classifier_min_margin=0.20,
        )
        self.settings_patch = patch(
            "app.services.donation_image_screening.get_settings",
            return_value=self.settings,
        )
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)

    def test_confident_medicine_packaging_is_accepted(self):
        screen_medicine_photo(b"image", FakeClassifier("medicine_packaging", 0.92, 0.61))

    def test_confident_unrelated_photo_is_rejected_with_specific_message(self):
        with self.assertRaises(HTTPException) as raised:
            screen_medicine_photo(b"dog photo", FakeClassifier("unrelated", 0.97, 0.91))
        self.assertEqual(raised.exception.status_code, 415)
        self.assertEqual(raised.exception.detail, UNRELATED_IMAGE_MESSAGE)

    def test_ambiguous_or_unrecognized_photo_requires_clearer_packaging(self):
        results = (
            FakeClassifier("medicine_packaging", 0.61, 0.18),
            FakeClassifier("unrecognized_subject", 0.94, 0.82),
            FakeClassifier("unrelated", 0.68, 0.11),
        )
        for classifier in results:
            with self.subTest(label=classifier.result.label), self.assertRaises(HTTPException) as raised:
                screen_medicine_photo(b"image", classifier)
            self.assertEqual(raised.exception.status_code, 415)
            self.assertEqual(raised.exception.detail, AMBIGUOUS_IMAGE_MESSAGE)

    def test_unavailable_classifier_fails_closed_without_storing(self):
        with patch(
            "app.services.prescription_image_classifier.get_prescription_image_classifier",
            side_effect=ImportError("transformers is unavailable"),
        ), self.assertRaises(HTTPException) as raised:
            screen_medicine_photo(b"image")
        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("upload was not stored", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
