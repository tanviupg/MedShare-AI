import os
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.medicine_extraction import (
    FIELDS,
    GeminiExtractionProvider,
    PaddleOCRExtractionProvider,
    _map_visible_fields,
    get_extraction_provider,
)


class MedicineExtractionProviderTests(unittest.TestCase):
    @patch("app.services.medicine_extraction.get_settings")
    def test_gemini_is_the_default_provider_and_uses_configured_model(self, get_settings):
        get_settings.return_value = SimpleNamespace(
            medicine_extraction_provider="gemini",
            gemini_api_key="test-key-not-real",
            gemini_model="gemini-2.5-flash",
        )

        provider = get_extraction_provider()

        self.assertIsInstance(provider, GeminiExtractionProvider)
        self.assertEqual(provider.name, "gemini")
        self.assertEqual(provider.model, "gemini-2.5-flash")

    @patch("app.services.medicine_extraction.get_settings")
    def test_paddleocr_remains_an_explicit_fallback_provider(self, get_settings):
        get_settings.return_value = SimpleNamespace(medicine_extraction_provider="paddleocr")

        provider = get_extraction_provider()

        self.assertIsInstance(provider, PaddleOCRExtractionProvider)
        self.assertEqual(provider.name, "paddleocr")

    @patch("app.services.medicine_extraction.get_settings")
    def test_unknown_provider_is_rejected(self, get_settings):
        get_settings.return_value = SimpleNamespace(medicine_extraction_provider="unknown")

        with self.assertRaisesRegex(RuntimeError, "gemini"):
            get_extraction_provider()

    def test_gemini_missing_key_fails_without_disclosing_key(self):
        provider = GeminiExtractionProvider("", "gemini-2.5-flash")
        with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY is not configured") as raised:
            provider.extract(b"image", "image/png")
        self.assertNotIn("test-key", str(raised.exception))

    def test_gemini_maps_structured_response_and_marks_confidence_unavailable(self):
        response_fields = {
            "medicine_name": "PANTOPRAZOLE",
            "strength": "40 mg",
            "dosage_form": "TABLETS",
            "manufacturer": None,
            "batch_number": "AB1234",
            "expiry_date": "12/2030",
            "quantity": 10,
            "packaging_type": None,
        }
        fake_client = SimpleNamespace(
            models=SimpleNamespace(
                generate_content=lambda **kwargs: SimpleNamespace(text=json.dumps(response_fields))
            )
        )

        result = GeminiExtractionProvider("test-key-not-real", "gemini-2.5-flash", fake_client).extract(
            b"synthetic image bytes", "image/png"
        )

        self.assertEqual({field: result.fields[field] for field in FIELDS}, response_fields)
        self.assertIsNone(result.fields["raw_ocr_text"])
        self.assertEqual(result.confidence, {field: None for field in FIELDS})
        self.assertIsNone(result.overall_confidence)
        self.assertEqual(result.provider, "gemini")
        self.assertEqual(result.version, "gemini-2.5-flash")

    def test_gemini_request_uses_configured_model_and_uploaded_image_bytes(self):
        response_fields = {field: None for field in FIELDS}
        captured = {}

        def generate_content(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text=json.dumps(response_fields))

        fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        GeminiExtractionProvider("test-key-not-real", "gemini-2.5-flash", fake_client).extract(
            b"protected uploaded image", "image/png"
        )

        self.assertEqual(captured["model"], "gemini-2.5-flash")
        self.assertIn("ONLY return information that is actually visible", captured["contents"][0])
        image_part = captured["contents"][1]
        self.assertEqual(image_part.inline_data.mime_type, "image/png")
        self.assertEqual(image_part.inline_data.data, b"protected uploaded image")
        self.assertEqual(captured["config"].response_mime_type, "application/json")

    def test_gemini_accepts_markdown_json_and_keeps_missing_or_uncertain_fields_null(self):
        response = "```json\n" + json.dumps({
            "medicine_name": None,
            "strength": "500 MG",
            "expiry_date": None,
        }) + "\n```"
        fake_client = SimpleNamespace(
            models=SimpleNamespace(
                generate_content=lambda **kwargs: SimpleNamespace(text=response)
            )
        )

        result = GeminiExtractionProvider("test-key-not-real", "gemini-2.5-flash", fake_client).extract(
            b"synthetic image bytes", "image/jpeg"
        )

        self.assertIsNone(result.fields["medicine_name"])
        self.assertEqual(result.fields["strength"], "500 MG")
        self.assertIsNone(result.fields["expiry_date"])
        self.assertIsNone(result.fields["manufacturer"])

    def test_gemini_malformed_response_fails_safely(self):
        fake_client = SimpleNamespace(
            models=SimpleNamespace(
                generate_content=lambda **kwargs: SimpleNamespace(text="not json")
            )
        )
        provider = GeminiExtractionProvider("test-key-not-real", "gemini-2.5-flash", fake_client)
        with self.assertRaisesRegex(RuntimeError, "Gemini could not extract this image"):
            provider.extract(b"synthetic image bytes", "image/png")

    def test_gemini_api_error_does_not_leak_provider_error(self):
        def fail_request(**kwargs):
            raise RuntimeError("quota failure; key=test-key-not-real")

        fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=fail_request))
        provider = GeminiExtractionProvider("test-key-not-real", "gemini-2.5-flash", fake_client)
        with self.assertRaisesRegex(RuntimeError, "Gemini could not extract this image") as raised:
            provider.extract(b"synthetic image bytes", "image/png")
        self.assertNotIn("test-key-not-real", str(raised.exception))

    def test_maps_only_visible_text_with_confidence(self):
        lines = [
            ("SAMPLE MEDICINE", 0.98),
            ("500 MG", 0.97),
            ("TABLETS", 0.96),
            ("BATCH AB1234", 0.94),
            ("EXP 12/2030", 0.93),
            ("10 TABLETS", 0.95),
        ]

        fields, confidence = _map_visible_fields(lines)

        self.assertEqual(fields["medicine_name"], "SAMPLE MEDICINE")
        self.assertEqual(fields["strength"], "500 MG")
        self.assertEqual(fields["dosage_form"], "TABLETS")
        self.assertEqual(fields["batch_number"], "AB1234")
        self.assertEqual(fields["expiry_date"], "12/2030")
        self.assertEqual(fields["quantity"], 10)
        self.assertIsNone(fields["manufacturer"])
        self.assertIsNone(fields["packaging_type"])
        self.assertEqual(confidence["strength"], 0.97)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in confidence.values()))

    def test_maps_lowercase_package_text_without_losing_visible_strength(self):
        lines = [
            ("PANTOPRAZOLE", 0.996),
            ("40 mg", 0.998),
            ("GASTRO-RESISTANT", 0.962),
            ("TABLETS IP", 0.952),
            ("BATCH AB1234", 0.997),
            ("EXP 12/2030", 0.981),
            ("10 tablets", 0.944),
        ]

        fields, confidence = _map_visible_fields(lines)

        self.assertEqual(fields["medicine_name"], "PANTOPRAZOLE")
        self.assertEqual(fields["strength"], "40 mg")
        self.assertEqual(fields["dosage_form"], "TABLETS")
        self.assertEqual(fields["batch_number"], "AB1234")
        self.assertEqual(fields["expiry_date"], "12/2030")
        self.assertEqual(fields["quantity"], 10)
        self.assertIsNone(fields["manufacturer"])
        self.assertIsNone(fields["packaging_type"])
        self.assertGreater(confidence["medicine_name"], 0)
        self.assertGreater(confidence["strength"], 0)

    def test_blank_or_unreadable_text_has_no_inferred_values(self):
        fields, confidence = _map_visible_fields([])
        self.assertEqual(fields, {field: None for field in FIELDS})
        self.assertEqual(confidence, {field: 0.0 for field in FIELDS})

        fields, confidence = _map_visible_fields([
            ("SAMP1E MED1CINE", 0.42),
            ("500 MG", 0.51),
            ("TABLETS", 0.55),
            ("Take with water", 0.99),
        ])
        self.assertTrue(all(fields[field] is None for field in FIELDS))
        self.assertTrue(all(confidence[field] == 0.0 for field in FIELDS))

    def test_expiry_formats_are_preserved_without_fabricating_a_day(self):
        for visible in ("08/27", "08-2027", "2027-08"):
            with self.subTest(visible=visible):
                fields, _ = _map_visible_fields([(f"EXP {visible}", 0.95)])
                self.assertEqual(fields["expiry_date"], visible)

    @unittest.skipUnless(os.environ.get("RUN_LOCAL_PADDLEOCR") == "1", "set RUN_LOCAL_PADDLEOCR=1 to run the real local model")
    def test_real_paddleocr_on_synthetic_package_image(self):
        from PIL import Image, ImageDraw, ImageFont
        import io

        image = Image.new("RGB", (1400, 900), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 72)
        for y, text in (
            (70, "SAMPLE MEDICINE"),
            (190, "500 MG"),
            (310, "TABLETS"),
            (430, "BATCH AB1234"),
            (550, "EXP 12/2030"),
            (670, "10 TABLETS"),
        ):
            draw.text((70, y), text, fill="black", font=font)
        content = io.BytesIO()
        image.save(content, format="PNG")

        result = PaddleOCRExtractionProvider().extract(content.getvalue(), "image/png")

        self.assertIn("SAMPLE MEDICINE", result.fields["raw_ocr_text"])
        self.assertIn("500 MG", result.fields["raw_ocr_text"])
        self.assertIn("BATCH AB1234", result.fields["raw_ocr_text"])
        self.assertIn("EXP 12/2030", result.fields["raw_ocr_text"])
        self.assertEqual(result.fields["medicine_name"], "SAMPLE MEDICINE")
        self.assertEqual(result.fields["strength"], "500 MG")
        self.assertEqual(result.fields["dosage_form"], "TABLETS")
        self.assertEqual(result.fields["batch_number"], "AB1234")
        self.assertEqual(result.fields["expiry_date"], "12/2030")
        self.assertEqual(result.fields["quantity"], 10)
        self.assertGreater(result.overall_confidence, 0)

        blank = Image.new("RGB", (1400, 900), "white")
        blank_content = io.BytesIO()
        blank.save(blank_content, format="PNG")
        blank_result = PaddleOCRExtractionProvider().extract(blank_content.getvalue(), "image/png")
        self.assertTrue(all(blank_result.fields[field] is None for field in FIELDS))
        self.assertEqual(blank_result.fields["raw_ocr_text"], "")
        self.assertTrue(all(value == 0.0 for value in blank_result.confidence.values()))
        self.assertEqual(blank_result.overall_confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
