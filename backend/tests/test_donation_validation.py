import unittest
from datetime import date, timedelta
from io import BytesIO
from PIL import Image

from pydantic import ValidationError

from app.schemas.donation import DonationReviewCreate
from app.api.routes.donations import validate_image_content


class DonationImageValidationTests(unittest.TestCase):
    def encoded_image(self, format, **options):
        image = Image.new("RGB", (12, 12), (30, 100, 180))
        output = BytesIO()
        image.save(output, format=format, **options)
        return output.getvalue()

    def test_decodable_supported_images_are_accepted(self):
        for format, kind in (("JPEG", "jpeg"), ("PNG", "png"), ("WEBP", "webp")):
            with self.subTest(format=format):
                self.assertEqual(validate_image_content(self.encoded_image(format)), kind)

    def test_progressive_jpeg_is_accepted(self):
        self.assertEqual(validate_image_content(self.encoded_image("JPEG", progressive=True)), "jpeg")

    def test_corrupt_or_renamed_non_image_content_is_rejected(self):
        self.assertIsNone(validate_image_content(b"not an image named medicine.jpg"))
        self.assertIsNone(validate_image_content(b"\xff\xd8\xff" + b"corrupt jpeg data"))
        valid_jpeg = self.encoded_image("JPEG")
        self.assertIsNone(validate_image_content(valid_jpeg[:-20]))
        self.assertIsNone(validate_image_content(b""))

    def test_image_format_must_match_its_signature(self):
        jpeg = self.encoded_image("JPEG")
        forged_signature = b"\x89PNG\r\n\x1a\n" + jpeg[8:]
        self.assertIsNone(validate_image_content(forged_signature))


class DonationApprovalValidationTests(unittest.TestCase):
    def payload(self, expiry_date):
        return {
            "decision": "APPROVED",
            "physical_package_checked": True,
            "verified_details": {
                "medicine_name": "Example medicine",
                "batch_number": "B-42",
                "expiry_date": expiry_date,
                "quantity": 5,
                "unit": "tablets",
                "common_use_category": "OTHER",
            },
        }

    def test_expired_medicine_cannot_be_approved(self):
        with self.assertRaises(ValidationError) as raised:
            DonationReviewCreate.model_validate(self.payload(date.today() - timedelta(days=1)))
        self.assertIn("Expired medicine cannot be approved", str(raised.exception))

    def test_unexpired_medicine_remains_approvable(self):
        review = DonationReviewCreate.model_validate(self.payload(date.today() + timedelta(days=1)))
        self.assertEqual(review.decision.value, "APPROVED")

    def test_medicine_without_traceable_batch_cannot_be_approved(self):
        payload = self.payload(date.today() + timedelta(days=1))
        payload["verified_details"]["batch_number"] = None
        with self.assertRaisesRegex(ValidationError, "traceable batch number"):
            DonationReviewCreate.model_validate(payload)

    def test_appearance_only_or_insufficient_evidence_does_not_bypass_manual_review(self):
        payload = self.payload(date.today() + timedelta(days=1))
        payload["physical_package_checked"] = False
        with self.assertRaisesRegex(ValidationError, "Physically check the package"):
            DonationReviewCreate.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
