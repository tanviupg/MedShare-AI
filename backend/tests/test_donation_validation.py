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


if __name__ == "__main__":
    unittest.main()
