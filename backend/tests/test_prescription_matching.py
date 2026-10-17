import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.prescription_matching import compare_prescription_medicine, extract_and_match_prescription


class PrescriptionMedicineMatchingTests(unittest.TestCase):
    def extracted(self, name="Amoxicillin", strength="500 mg", confidence=0.97):
        return {"medicine_name": name, "strength": strength,
                "confidence": {"medicine_name": confidence},
                "requested_strength": "500 mg"}

    def test_matching_name_is_match_case_insensitively(self):
        self.assertEqual(compare_prescription_medicine(self.extracted(), "AMOXICILLIN"), "MATCH")

    def test_different_name_is_mismatch(self):
        self.assertEqual(compare_prescription_medicine(self.extracted(), "Paracetamol"), "MISMATCH")

    def test_strength_difference_is_mismatch(self):
        self.assertEqual(compare_prescription_medicine(self.extracted(strength="250 mg"), "Amoxicillin"), "MISMATCH")

    def test_unreadable_name_is_uncertain(self):
        self.assertEqual(compare_prescription_medicine(self.extracted(name=None), "Amoxicillin"), "UNCERTAIN")

    def test_uncertain_ocr_is_never_a_match(self):
        self.assertEqual(compare_prescription_medicine(self.extracted(confidence=0.52), "Amoxicillin"), "UNCERTAIN")

    def test_unavailable_confidence_is_uncertain(self):
        self.assertEqual(compare_prescription_medicine(self.extracted(confidence=None), "Amoxicillin"), "UNCERTAIN")

    @patch("app.services.medicine_extraction.get_extraction_provider")
    def test_extraction_uses_existing_provider_and_matches_with_its_confidence(self, get_provider):
        provider = SimpleNamespace(extract=lambda image, mime: SimpleNamespace(
            fields={"medicine_name": "Amoxicillin", "strength": "500 mg", "dosage_form": "TABLET"},
            confidence={"medicine_name": 0.97}))
        get_provider.return_value = provider
        result = extract_and_match_prescription(b"mock image", "image/png", "Amoxicillin", "500 mg")
        self.assertEqual(result["matching_result"], "MATCH")
        self.assertEqual(result["dosage_form"], "TABLET")

    @patch("app.services.medicine_extraction.get_extraction_provider", side_effect=RuntimeError("unavailable"))
    def test_extraction_failure_is_uncertain(self, _get_provider):
        result = extract_and_match_prescription(b"mock image", "image/png", "Amoxicillin")
        self.assertEqual(result["matching_result"], "UNCERTAIN")
        self.assertIsNone(result["medicine_name"])


if __name__ == "__main__":
    unittest.main()
