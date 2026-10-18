import unittest
from datetime import date, timedelta

from pydantic import ValidationError

from app.schemas.donation import DonationReviewCreate


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
