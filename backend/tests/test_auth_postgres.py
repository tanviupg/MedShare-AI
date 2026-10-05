import json
import importlib.util
import os
from pathlib import Path
import socket
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID

from jose import jwt
from sqlalchemy import create_engine, func, select
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from alembic.migration import MigrationContext
from alembic.operations import Operations
import uvicorn

from app.api.dependencies import get_db
from app.api.routes.donations import storage
from app.services.prescription_storage import storage as prescription_storage
from app.core.config import get_settings
from app.db.base import Base
from app.main import app
from app.models import Checkout, ClinicProfile, CommonUseCategory, DispensingRecord, Donation, DonationImage, DonationReview, DonationStatus, Inventory, InventoryStatus, MedicineRequest, MedicineRequestStatus, MedicineExtraction, Notification, NotificationType, Prescription, PrescriptionStatus, User, UserRole, WasteRecord, WasteReason, WasteStatus
from app.services.security import hash_password, verify_password


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
if not TEST_DATABASE_URL:
    test_env = Path(__file__).resolve().parents[1] / ".env.test"
    if test_env.exists():
        TEST_DATABASE_URL = next(
            (line.split("=", 1)[1].strip().strip('"') for line in test_env.read_text().splitlines() if line.startswith("TEST_DATABASE_URL=")),
            "",
        )


def request(method, path, payload=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(TestAuthPostgres.base_url + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, response.read().decode()
    except HTTPError as response:
        body = response.read().decode()
        response.close()
        return response.code, body


def upload_request(path, filename, content, content_type, token, field="files", fields=None):
    boundary = "----MedShareTestBoundary"
    body = b""
    for name, value in (fields or {}).items():
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\nContent-Type: {content_type}\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
    req = Request(TestAuthPostgres.base_url + path, data=body, headers={"Authorization": f"Bearer {token}", "Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, response.read().decode()
    except HTTPError as response:
        result = response.code, response.read().decode()
        response.close()
        return result


def image_request(path, token):
    req = Request(TestAuthPostgres.base_url + path, headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, response.read()
    except HTTPError as response:
        result = response.code, response.read()
        response.close()
        return result


class TestAuthPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TEST_DATABASE_URL:
            raise RuntimeError("TEST_DATABASE_URL is required; PostgreSQL integration tests must not be skipped")
        url = make_url(TEST_DATABASE_URL)
        if url.get_backend_name() != "postgresql" or not (url.database or "").endswith("_test") or url.database == "medshare_new":
            raise RuntimeError("TEST_DATABASE_URL must point to an isolated PostgreSQL database ending in _test")
        cls.engine = create_engine(url, pool_pre_ping=True)
        cls.Session = sessionmaker(bind=cls.engine, class_=Session, expire_on_commit=False)
        cls.port = socket.socket()
        cls.port.bind(("127.0.0.1", 0))
        port = cls.port.getsockname()[1]
        cls.port.close()
        cls.base_url = f"http://127.0.0.1:{port}"

        def override_get_db():
            with cls.Session() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        cls.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("Test API did not start")

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=5)
        app.dependency_overrides.clear()
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.upload_dir = Path(__file__).resolve().parents[1] / ".test_uploads"
        self.upload_dir.mkdir(exist_ok=True)
        storage.root = self.upload_dir
        prescription_storage.root = self.upload_dir / "prescriptions"
        self.donation_verification = {}

    def tearDown(self):
        for path in sorted(self.upload_dir.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.is_file():
                path.unlink()
            else:
                path.rmdir()
        self.upload_dir.rmdir()

    def signup(self, role, suffix=""):
        payload = {"name": f"Test {role}", "email": f"{role.lower()}{suffix}@example.com", "password": "correct-horse-battery", "role": role, "phone": "555-0100", "city": "Pune"}
        if role == "CLINIC_PHARMACIST":
            payload["clinic_profile"] = {"clinic_name": "Test Clinic", "address": "12 Sample Road", "city": "Pune", "license_number": "LIC-TEST-42", "contact_number": "555-0199"}
        status, body = request("POST", "/auth/signup", payload)
        self.assertEqual(status, 201, body)
        return payload, json.loads(body)

    def create_admin(self):
        with self.Session() as session:
            session.add(User(
                name="Platform Reviewer",
                email="reviewer@example.com",
                password_hash=hash_password("reviewer-secure-password"),
                role=UserRole.ADMIN,
            ))
            session.commit()
        status, body = request(
            "POST",
            "/auth/login",
            {"email": "reviewer@example.com", "password": "reviewer-secure-password"},
        )
        self.assertEqual(status, 200, body)
        return json.loads(body)

    def test_signup_login_me_hashes_and_clinic_profile_for_all_roles(self):
        for role in ("DONOR", "PATIENT", "CLINIC_PHARMACIST"):
            with self.subTest(role=role):
                payload, signup = self.signup(role)
                user_json = signup["user"]
                self.assertEqual(user_json["role"], role)
                self.assertNotIn("password", user_json)
                self.assertNotIn("password_hash", user_json)
                self.assertNotIn("password_hash", signup)
                if role == "CLINIC_PHARMACIST":
                    self.assertEqual(user_json["clinic_profile"]["clinic_name"], "Test Clinic")
                    self.assertEqual(user_json["clinic_profile"]["verification_status"], "PENDING")
                else:
                    self.assertIsNone(user_json["clinic_profile"])
                with self.engine.connect() as connection:
                    stored = connection.execute(select(User.password_hash).where(User.email == payload["email"])).scalar_one()
                    self.assertNotEqual(stored, payload["password"])
                    self.assertTrue(verify_password(payload["password"], stored))
                    count = connection.execute(
                        select(func.count())
                        .select_from(ClinicProfile)
                        .join(User, ClinicProfile.user_id == User.id)
                        .where(User.email == payload["email"])
                    ).scalar_one()
                    self.assertEqual(count, 1 if role == "CLINIC_PHARMACIST" else 0)
                status, body = request("POST", "/auth/login", {"email": payload["email"], "password": payload["password"]})
                self.assertEqual(status, 200, body)
                login = json.loads(body)
                self.assertNotIn("password", body)
                self.assertNotIn("password_hash", body)
                status, body = request("GET", "/auth/me", token=login["access_token"])
                self.assertEqual(status, 200, body)
                me = json.loads(body)
                self.assertEqual(me["role"], role)
                self.assertNotIn("password", body)
                self.assertNotIn("password_hash", body)

    def test_invalid_password_and_invalid_or_expired_tokens(self):
        _, signup = self.signup("PATIENT")
        status, _ = request("POST", "/auth/login", {"email": "patient@example.com", "password": "incorrect-password"})
        self.assertEqual(status, 401)
        status, _ = request("GET", "/auth/me", token="not.a.jwt")
        self.assertEqual(status, 401)
        expired = jwt.encode({"sub": str(UUID(signup["user"]["id"])), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}, get_settings().jwt_secret, algorithm=get_settings().jwt_algorithm)
        status, _ = request("GET", "/auth/me", token=expired)
        self.assertEqual(status, 401)

    def test_role_authorization_and_exact_role_set(self):
        self.assertEqual({role.value for role in UserRole}, {"DONOR", "PATIENT", "CLINIC_PHARMACIST", "ADMIN"})
        invalid_role = {"name": "Doctor", "email": "doctor@example.com", "password": "correct-horse-battery", "role": "DOCTOR"}
        self.assertEqual(request("POST", "/auth/signup", invalid_role)[0], 422)
        public_admin = {"name": "Reviewer", "email": "reviewer-public@example.com", "password": "correct-horse-battery", "role": "ADMIN"}
        self.assertEqual(request("POST", "/auth/signup", public_admin)[0], 422)
        missing_clinic = {"name": "Pharmacist", "email": "no-clinic@example.com", "password": "correct-horse-battery", "role": "CLINIC_PHARMACIST"}
        self.assertEqual(request("POST", "/auth/signup", missing_clinic)[0], 422)
        tokens = {}
        for role in ("DONOR", "PATIENT", "CLINIC_PHARMACIST"):
            _, result = self.signup(role)
            tokens[role] = result["access_token"]
        paths = {"DONOR": "/auth/test/donor", "PATIENT": "/auth/test/patient", "CLINIC_PHARMACIST": "/auth/test/clinic"}
        for role, token in tokens.items():
            for required, path in paths.items():
                status, _ = request("GET", path, token=token)
                self.assertEqual(status, 200 if role == required else 403)

    def test_admin_clinic_verification_authorization_audit_and_discovery_gates(self):
        admin = self.create_admin()
        _, donor = self.signup("DONOR", "-verification")
        _, patient = self.signup("PATIENT", "-verification")
        _, clinic_to_approve = self.signup("CLINIC_PHARMACIST", "-approve")
        _, clinic_to_reject = self.signup("CLINIC_PHARMACIST", "-reject")
        patient_token = patient["access_token"]
        admin_token = admin["access_token"]
        with self.Session() as session:
            approve_profile_id = str(session.scalar(select(ClinicProfile.id).where(
                ClinicProfile.user_id == UUID(clinic_to_approve["user"]["id"])
            )))
            reject_profile_id = str(session.scalar(select(ClinicProfile.id).where(
                ClinicProfile.user_id == UUID(clinic_to_reject["user"]["id"])
            )))
        pending_url = "/admin/clinic-verifications/pending"
        approve_url = f"/admin/clinic-verifications/{approve_profile_id}/approve"
        reject_url = f"/admin/clinic-verifications/{reject_profile_id}/reject"

        self.assertEqual(request("GET", pending_url)[0], 401)
        for role, token in (
            ("donor", donor["access_token"]),
            ("patient", patient_token),
            ("clinic", clinic_to_approve["access_token"]),
            ("clinic", clinic_to_reject["access_token"]),
        ):
            with self.subTest(non_admin_role=role):
                self.assertEqual(request("GET", pending_url, token=token)[0], 403)
                self.assertEqual(request("POST", approve_url, token=token)[0], 403)
                self.assertEqual(request("POST", reject_url, {"reason": "Not approved"}, token)[0], 403)

        status, body = request("GET", pending_url, token=admin_token)
        self.assertEqual(status, 200, body)
        pending_items = json.loads(body)
        self.assertEqual({item["id"] for item in pending_items}, {approve_profile_id, reject_profile_id})
        self.assertTrue(all("address" in item and "license_number" in item for item in pending_items))
        self.assertTrue(all("email" not in item and "user_id" not in item for item in pending_items))

        with self.Session() as session:
            admin_owned_profile = ClinicProfile(
                user_id=UUID(admin["user"]["id"]),
                clinic_name="Reviewer-owned profile",
                address="1 Test Street",
                city="Pune",
            )
            session.add(admin_owned_profile)
            session.commit()
            admin_owned_profile_id = admin_owned_profile.id
        self.assertEqual(
            request(
                "POST",
                f"/admin/clinic-verifications/{admin_owned_profile_id}/approve",
                token=admin_token,
            )[0],
            403,
        )
        with self.Session() as session:
            session.delete(session.get(ClinicProfile, admin_owned_profile_id))
            session.commit()

        self.assertEqual(request("POST", approve_url, token=clinic_to_approve["access_token"])[0], 403)
        self.assertEqual(request("POST", approve_url, token=admin_token)[0], 200)
        with self.Session() as session:
            approved_profile = session.get(ClinicProfile, UUID(approve_profile_id))
            self.assertEqual(approved_profile.verification_status, "VERIFIED")
            self.assertEqual(str(approved_profile.verification_reviewer_id), admin["user"]["id"])
            self.assertIsNotNone(approved_profile.verification_decided_at)
            self.assertIsNone(approved_profile.verification_rejection_reason)

        _, pending_donation = self.create_donation(donor["access_token"], medicine_name="Verified clinic stock")
        pending_donation = json.loads(pending_donation)
        self.assertEqual(self.approve_donation(pending_donation["id"], clinic_to_approve["access_token"])[0], 201)
        status, body = request("GET", "/patient/medicines?q=Verified%20clinic%20stock", token=patient_token)
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["total"], 1)

        _, rejected_donation = self.create_donation(donor["access_token"], medicine_name="Rejected clinic stock")
        rejected_donation = json.loads(rejected_donation)
        self.assertEqual(self.approve_donation(rejected_donation["id"], clinic_to_reject["access_token"])[0], 201)
        status, body = request("GET", "/patient/medicines?q=Rejected%20clinic%20stock", token=patient_token)
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["total"], 0)
        self.assertEqual(request("POST", reject_url, {}, admin_token)[0], 422)
        self.assertEqual(request("POST", reject_url, {"reason": "   "}, admin_token)[0], 422)
        status, body = request("POST", reject_url, {"reason": "License details need clarification."}, admin_token)
        self.assertEqual(status, 200, body)
        result = json.loads(body)
        self.assertEqual(result["verification_status"], "REJECTED")
        self.assertEqual(result["verification_rejection_reason"], "License details need clarification.")
        with self.Session() as session:
            rejected_profile = session.get(ClinicProfile, UUID(reject_profile_id))
            self.assertEqual(rejected_profile.verification_status, "REJECTED")
            self.assertEqual(str(rejected_profile.verification_reviewer_id), admin["user"]["id"])
            self.assertIsNotNone(rejected_profile.verification_decided_at)
            self.assertEqual(rejected_profile.verification_rejection_reason, "License details need clarification.")
        status, body = request("GET", "/patient/medicines?q=Rejected%20clinic%20stock", token=patient_token)
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["total"], 0)
        self.assertEqual(request("GET", pending_url, token=admin_token)[1], "[]")

        status, body = request("GET", "/auth/me", token=clinic_to_reject["access_token"])
        self.assertEqual(status, 200, body)
        clinic_profile = json.loads(body)["clinic_profile"]
        self.assertEqual(clinic_profile["verification_status"], "REJECTED")
        self.assertEqual(clinic_profile["verification_rejection_reason"], "License details need clarification.")

    def create_donation(self, token, **updates):
        details = {
            "medicine_name": "Paracetamol", "strength": "500 mg", "dosage_form": "Tablet",
            "packaging_type": "Strip", "manufacturer": "Example Labs", "batch_number": "B-42",
            "expiry_date": "2030-12-31", "quantity": 24, "unit": "tablets", "common_use_category": "COLD",
        }
        details.update({key: value for key, value in updates.items() if key in details})
        payload = {
            "pickup_address": "12 Sample Road, Pune",
            "donor_expiry_date": updates.get("donor_expiry_date", updates.get("expiry_date", "2030-12-31")),
        }
        status_code, body = request("POST", "/donations", payload, token)
        if status_code != 201 or updates.get("details_confirmed") is False:
            return status_code, body
        donation_id = json.loads(body)["id"]
        self.donation_verification[donation_id] = details
        image = b"\xff\xd8\xff" + b"x" * 100
        upload_status, upload_body = upload_request(
            f"/donations/{donation_id}/images", "package.jpg", image, "image/jpeg", token
        )
        if upload_status != 201:
            raise AssertionError(f"Donation image submission failed: {upload_status} {upload_body}")
        return status_code, body

    def approve_donation(self, donation_id, token, **overrides):
        details = {**self.donation_verification[donation_id], **overrides}
        reason = details.pop("reason", None)
        category = details.pop("common_use_category")
        payload = {
            "decision": "APPROVED",
            "reason": reason,
            "physical_package_checked": True,
            "verified_details": {**details, "common_use_category": category},
        }
        return request("POST", f"/donations/{donation_id}/review", payload, token)

    def create_patient_request(self, inventory_id, requested_quantity, token, pickup_address="Patient pickup address"):
        with self.Session() as session:
            inventory = session.get(Inventory, UUID(str(inventory_id)))
            medicine_id = inventory.public_id if inventory is not None else UUID(str(inventory_id))
        return request(
            "POST", "/patient/requests",
            {"medicine_id": str(medicine_id), "requested_quantity": requested_quantity, "pickup_address": pickup_address},
            token,
        )

    def create_patient_request_with_prescription(self, inventory_id, requested_quantity, token, pickup_address="Patient pickup address", content=b"%PDF-1.4\nrequest fixture\n%%EOF", filename="request.pdf", content_type="application/pdf"):
        with self.Session() as session:
            inventory = session.get(Inventory, UUID(str(inventory_id)))
            medicine_id = inventory.public_id if inventory is not None else UUID(str(inventory_id))
        return upload_request(
            "/patient/requests/with-prescription",
            filename,
            content,
            content_type,
            token,
            field="file",
            fields={
                "medicine_id": str(medicine_id),
                "requested_quantity": str(requested_quantity),
                "pickup_address": pickup_address,
            },
        )

    def test_notification_api_pagination_filter_read_and_ownership(self):
        _, owner = self.signup("PATIENT", "notify-owner")
        _, other = self.signup("PATIENT", "notify-other")
        owner_id = UUID(owner["user"]["id"])
        rows = [Notification(recipient_user_id=owner_id, type=NotificationType.REQUEST_APPROVED,
                 title=f"Request {i}", message="Your medicine request was approved.",
                 related_entity_type="medicine_request", related_entity_id=UUID(int=i + 1)) for i in range(3)]
        with self.Session() as session:
            session.add_all(rows)
            session.commit()
        status_code, body = request("GET", "/notifications?limit=2&offset=0", token=owner["access_token"])
        self.assertEqual(status_code, 200, body)
        page = json.loads(body)
        self.assertEqual(len(page["items"]), 2)
        self.assertEqual(page["total"], 3)
        self.assertTrue(all(not item["is_read"] for item in page["items"]))
        self.assertEqual(json.loads(request("GET", "/notifications/unread-count", token=owner["access_token"])[1])["count"], 3)
        self.assertEqual(request("GET", "/notifications", token=other["access_token"])[1].count('"items":[]'), 1)
        self.assertEqual(request("GET", "/notifications")[0], 401)
        self.assertEqual(request("POST", f"/notifications/{page['items'][0]['id']}/read", token=other["access_token"])[0], 404)
        self.assertEqual(request("POST", f"/notifications/{page['items'][0]['id']}/read", token=owner["access_token"])[0], 200)
        self.assertEqual(json.loads(request("GET", "/notifications?unread_only=true", token=owner["access_token"])[1])["total"], 2)
        self.assertEqual(request("POST", "/notifications/read-all", token=owner["access_token"])[0], 200)
        self.assertEqual(json.loads(request("GET", "/notifications/unread-count", token=owner["access_token"])[1])["count"], 0)

    def test_donor_create_status_list_get_ownership_and_roles(self):
        _, donor1 = self.signup("DONOR", "1")
        _, donor2 = self.signup("DONOR", "2")
        _, patient = self.signup("PATIENT")
        _, pharmacist = self.signup("CLINIC_PHARMACIST")
        status_code, body = self.create_donation(donor1["access_token"])
        self.assertEqual(status_code, 201, body)
        created = json.loads(body)
        self.assertEqual(created["status"], "PENDING_REVIEW")
        self.assertEqual(set(created), {"id", "status", "created_at"})
        donation_id = created["id"]
        invalid_identity = request("POST", "/donations", {
            "pickup_address": "12 Sample Road", "medicine_name": "Injected", "expiry_date": "2030-12-31",
            "quantity": 1, "unit": "box", "manufacturer": "Injected", "batch_number": "Injected",
        }, token=donor1["access_token"])
        self.assertEqual(invalid_identity[0], 422, invalid_identity[1])
        self.assertEqual(request("GET", f"/donations/{donation_id}", token=donor1["access_token"])[0], 200)
        self.assertEqual(request("GET", "/donations/mine", token=donor1["access_token"])[0], 200)
        self.assertEqual(request("GET", f"/donations/{donation_id}", token=donor2["access_token"])[0], 404)
        self.assertEqual(request("POST", "/donations", {"pickup_address": "12 Sample Road"}, token=pharmacist["access_token"])[0], 403)
        self.assertEqual(request("POST", "/donations", {"pickup_address": "12 Sample Road"}, token=patient["access_token"])[0], 403)

    def test_medicine_extraction_is_internal_and_pharmacist_review_gated(self):
        _, donor = self.signup("DONOR", "extract-owner")
        _, other = self.signup("DONOR", "extract-other")
        _, pharmacist = self.signup("CLINIC_PHARMACIST", "extract")
        created = json.loads(self.create_donation(donor["access_token"], details_confirmed=False)[1])
        donation_id = created["id"]
        self.assertEqual(request("GET", "/donations/review-queue", token=pharmacist["access_token"])[1], "[]")
        self.assertEqual(request("GET", f"/donations/{donation_id}/review", token=pharmacist["access_token"])[0], 404)
        self.assertEqual(request("POST", f"/donations/{donation_id}/extract", token=other["access_token"])[0], 403)
        image = b"\xff\xd8\xff" + b"x" * 100
        upload_status, upload_body = upload_request(f"/donations/{donation_id}/images", "package.jpg", image, "image/jpeg", donor["access_token"])
        self.assertEqual(upload_status, 201, upload_body)
        image_id = json.loads(upload_body)[0]["id"]
        self.assertEqual(request("POST", f"/donations/{donation_id}/extract", token=donor["access_token"])[0], 403)
        self.assertEqual(request("GET", f"/donations/{donation_id}/extraction", token=donor["access_token"])[0], 403)
        self.assertEqual(request("POST", f"/donations/{donation_id}/extraction/confirm", {"medicine_name": "Injected"}, donor["access_token"])[0], 404)
        pharmacist_extraction = request("GET", f"/donations/{donation_id}/extraction", token=pharmacist["access_token"])
        self.assertEqual(pharmacist_extraction[0], 200, pharmacist_extraction[1])
        self.assertEqual(json.loads(pharmacist_extraction[1])["items"], [])
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(select(func.count()).select_from(MedicineExtraction).where(MedicineExtraction.donation_id == donation_id)).scalar_one(), 0)
            self.assertEqual(connection.execute(select(func.count()).select_from(Inventory).where(Inventory.donation_id == donation_id)).scalar_one(), 0)
        from unittest.mock import patch

        class ExtractionProviderForTest:
            name = "paddleocr-test"
            version = "test"

            def extract(self, image, content_type):
                fields = {key: None for key in ("medicine_name", "strength", "dosage_form", "manufacturer", "batch_number", "expiry_date", "quantity", "packaging_type")}
                fields["raw_ocr_text"] = ""
                return type("Result", (), {
                    "fields": fields,
                    "confidence": {key: 0.0 for key in fields if key != "raw_ocr_text"},
                    "overall_confidence": 0.0,
                    "provider": self.name,
                    "version": self.version,
                })()

        with patch("app.api.routes.donations.get_extraction_provider", return_value=ExtractionProviderForTest()):
            extracted = request("POST", f"/donations/{donation_id}/extract", token=pharmacist["access_token"])
        self.assertEqual(extracted[0], 200, extracted[1])
        self.assertEqual(len(json.loads(extracted[1])["items"]), 1)
        pharmacist_extraction = request("GET", f"/donations/{donation_id}/extraction", token=pharmacist["access_token"])
        self.assertEqual(pharmacist_extraction[0], 200, pharmacist_extraction[1])
        extraction = json.loads(pharmacist_extraction[1])["items"][0]
        self.assertTrue(all(value is None for value in extraction["fields"].values()))
        self.assertEqual(extraction["raw_ocr_text"], "")
        self.assertEqual(json.loads(pharmacist_extraction[1])["items"][0]["status"], "COMPLETED")
        self.assertFalse(json.loads(pharmacist_extraction[1])["items"][0]["is_mock"])
        uploaded = image_request(f"/donations/{donation_id}/images/{image_id}", donor["access_token"])
        self.assertEqual(uploaded, (200, image))
        with self.engine.connect() as connection:
            row = connection.execute(select(MedicineExtraction.provider_name, MedicineExtraction.status).where(MedicineExtraction.donation_id == donation_id)).one()
            self.assertEqual(row.provider_name, "paddleocr-test")
            self.assertEqual(row.status.value, "COMPLETED")
            draft = connection.execute(select(Donation.status, Donation.details_confirmed).where(Donation.id == donation_id)).one()
            self.assertEqual((draft.status.value, draft.details_confirmed), ("PENDING_REVIEW", True))
            self.assertEqual(connection.execute(select(func.count()).select_from(Inventory).where(Inventory.donation_id == donation_id)).scalar_one(), 0)
        class FailingGeminiProvider:
            name = "gemini"
            version = "gemini-2.5-flash"

            def extract(self, image, content_type):
                raise RuntimeError("quota failure; key=must-not-be-returned")

        with patch("app.api.routes.donations.get_extraction_provider", return_value=FailingGeminiProvider()):
            failed_response = request("POST", f"/donations/{donation_id}/extract", token=pharmacist["access_token"])
        self.assertEqual(failed_response[0], 200, failed_response[1])
        failed_item = next(item for item in json.loads(failed_response[1])["items"] if item["status"] == "FAILED")
        self.assertEqual(failed_item["error_message"], "OCR could not read this image. Please verify the package manually.")
        self.assertNotIn("must-not-be-returned", failed_response[1])
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(select(Donation.status).where(Donation.id == donation_id)).scalar_one().value, "PENDING_REVIEW")
            self.assertEqual(connection.execute(select(func.count()).select_from(Inventory).where(Inventory.donation_id == donation_id)).scalar_one(), 0)
        from app.services.medicine_extraction import GeminiExtractionProvider

        with patch(
            "app.api.routes.donations.get_extraction_provider",
            return_value=GeminiExtractionProvider("", "gemini-2.5-flash"),
        ):
            missing_key_response = request("POST", f"/donations/{donation_id}/extract", token=pharmacist["access_token"])
        self.assertEqual(missing_key_response[0], 200, missing_key_response[1])
        missing_key_item = next(item for item in json.loads(missing_key_response[1])["items"] if item["status"] == "FAILED")
        self.assertEqual(missing_key_item["error_message"], "OCR could not read this image. Please verify the package manually.")
        self.assertNotIn("GEMINI_API_KEY", missing_key_response[1])
        self.assertEqual(request("GET", f"/donations/{donation_id}/review", token=pharmacist["access_token"])[0], 200)
        self.assertEqual(request("GET", f"/donations/{donation_id}/extraction", token=other["access_token"])[0], 403)
        self.assertEqual(request("GET", f"/donations/{donation_id}/review", token=pharmacist["access_token"])[0], 200)
        confirmed = json.loads(request("GET", f"/donations/{donation_id}", token=donor["access_token"])[1])
        self.assertEqual(set(confirmed), {"id", "status", "created_at"})
        self.assertEqual(confirmed["status"], "PENDING_REVIEW")

        blank_draft_status, blank_draft_body = request("POST", "/donations", {"pickup_address": "12 Sample Road"}, donor["access_token"])
        self.assertEqual(blank_draft_status, 201, blank_draft_body)
        blank_draft = json.loads(blank_draft_body)
        self.assertEqual(set(blank_draft), {"id", "status", "created_at"})
        queue_after_blank_draft = json.loads(request("GET", "/donations/review-queue", token=pharmacist["access_token"])[1])
        self.assertNotIn(blank_draft["id"], [item["id"] for item in queue_after_blank_draft])

        failed_donation = json.loads(self.create_donation(donor["access_token"], details_confirmed=False)[1])
        failed_id = failed_donation["id"]
        upload_request(f"/donations/{failed_id}/images", "tiny.jpg", b"\xff\xd8\xff", "image/jpeg", donor["access_token"])
        failed = request("GET", f"/donations/{failed_id}/extraction", token=pharmacist["access_token"])
        self.assertEqual(failed[0], 200, failed[1])
        self.assertEqual(json.loads(failed[1])["items"], [])
        failed_run = request("POST", f"/donations/{failed_id}/extract", token=pharmacist["access_token"])
        self.assertEqual(failed_run[0], 200, failed_run[1])
        failed = request("GET", f"/donations/{failed_id}/extraction", token=pharmacist["access_token"])
        self.assertEqual(failed[0], 200, failed[1])
        self.assertEqual(json.loads(failed[1])["items"][0]["status"], "FAILED")
        self.assertNotIn("key", failed[1].lower())

    def test_pharmacist_review_has_explicit_ocr_action(self):
        source = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "PharmacistReview.tsx").read_text()
        self.assertIn("'Run OCR'", source)
        self.assertIn("'Running OCR...'", source)
        self.assertIn("AI/OCR extracted information", source)
        self.assertIn("`${API_BASE_URL}/donations/${selected.id}/extract`", source)

    def test_pharmacist_review_queue_approval_rejection_and_audit(self):
        _, donor = self.signup("DONOR")
        _, patient = self.signup("PATIENT")
        _, pharmacist = self.signup("CLINIC_PHARMACIST")
        donor_token, patient_token, pharmacist_token = donor["access_token"], patient["access_token"], pharmacist["access_token"]
        created_status, created_body = self.create_donation(donor_token, status="APPROVED")
        self.assertEqual(created_status, 201, created_body)
        donation = json.loads(created_body)
        donation_id = donation["id"]
        self.assertEqual(donation["status"], "PENDING_REVIEW")
        self.assertEqual(request("GET", "/donations/review-queue")[0], 401)
        self.assertEqual(request("GET", "/donations/review-queue", token=donor_token)[0], 403)
        self.assertEqual(request("GET", "/donations/review-queue", token=patient_token)[0], 403)
        queue_status, queue_body = request("GET", "/donations/review-queue", token=pharmacist_token)
        self.assertEqual(queue_status, 200, queue_body)
        self.assertEqual([row["id"] for row in json.loads(queue_body)], [donation_id])
        self.assertEqual(request("GET", f"/donations/{donation_id}/review", token=donor_token)[0], 403)
        self.assertEqual(self.approve_donation(donation_id, donor_token)[0], 403)
        self.assertEqual(request("GET", f"/donations/{donation_id}/review", token=pharmacist_token)[0], 200)
        rejected_without_reason = request("POST", f"/donations/{donation_id}/review", {"decision": "REJECTED", "reason": "   "}, pharmacist_token)
        self.assertEqual(rejected_without_reason[0], 422, rejected_without_reason[1])
        approved_status, approved_body = self.approve_donation(donation_id, pharmacist_token, reason="Package physically checked")
        self.assertEqual(approved_status, 201, approved_body)
        approved = json.loads(approved_body)
        self.assertEqual(approved["decision"], "APPROVED")
        self.assertEqual(approved["pharmacist_id"], pharmacist["user"]["id"])
        self.assertEqual(approved["donation_id"], donation_id)
        self.assertIsNotNone(approved["reviewed_at"])
        donor_notices = json.loads(request("GET", "/notifications", token=donor_token)[1])["items"]
        self.assertEqual([n["type"] for n in donor_notices], ["DONATION_APPROVED"])
        self.assertEqual(json.loads(request("GET", f"/donations/{donation_id}", token=donor_token)[1])["status"], "APPROVED")
        self.assertEqual(request("POST", f"/donations/{donation_id}/review", {"decision": "REJECTED", "reason": "late"}, pharmacist_token)[0], 409)
        self.assertEqual(request("GET", f"/donations/{donation_id}/review", token=pharmacist_token)[0], 404)
        self.assertEqual(request("GET", "/donations/mine", token=donor_token)[0], 200)
        with self.Session() as session:
            records = session.query(DonationReview).filter_by(donation_id=donation_id).all()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].reason, "Package physically checked")
            item = session.query(Inventory).filter_by(donation_id=donation_id).one()
            self.assertEqual(item.pharmacist_id, UUID(pharmacist["user"]["id"]))
            self.assertEqual((item.original_quantity, item.quantity_available), (24, 24))
            self.assertEqual((item.batch_number, item.expiry_date), ("B-42", datetime.fromisoformat("2030-12-31").date()))
            self.assertEqual(item.status, InventoryStatus.AVAILABLE)
        inventory_id = str(item.id)
        listed_status, listed_body = request("GET", "/inventory", token=pharmacist_token)
        self.assertEqual(listed_status, 200, listed_body)
        listed = json.loads(listed_body)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["donation_id"], donation_id)
        self.assertEqual(listed[0]["source_donation"]["id"], donation_id)
        self.assertEqual(listed[0]["review"]["decision"], "APPROVED")
        self.assertEqual(request("GET", f"/inventory/{inventory_id}", token=pharmacist_token)[0], 200)
        self.assertEqual(request("GET", "/inventory", token=donor_token)[0], 403)
        self.assertEqual(request("GET", "/inventory", token=patient_token)[0], 403)

        rejected_status, rejected_body = self.create_donation(donor_token)
        self.assertEqual(rejected_status, 201, rejected_body)
        rejected_id = json.loads(rejected_body)["id"]
        rejected_status, rejected_body = request("POST", f"/donations/{rejected_id}/review", {"decision": "REJECTED", "reason": "Opened package"}, pharmacist_token)
        self.assertEqual(rejected_status, 201, rejected_body)
        self.assertEqual(json.loads(rejected_body)["decision"], "REJECTED")
        with self.Session() as session:
            self.assertIsNone(session.query(Inventory).filter_by(donation_id=rejected_id).one_or_none())

    def test_inventory_database_constraints_and_expiry_status(self):
        _, donor = self.signup("DONOR")
        _, pharmacist = self.signup("CLINIC_PHARMACIST")
        _, patient = self.signup("PATIENT")
        created = json.loads(self.create_donation(donor["access_token"])[1])
        self.assertEqual(request("POST", f"/donations/{created['id']}/inventory", token=pharmacist["access_token"])[0], 404)
        self.assertEqual(request("GET", "/inventory", token=donor["access_token"])[0], 403)
        self.assertEqual(request("GET", "/inventory", token=patient["access_token"])[0], 403)
        approved_status, body = self.approve_donation(created['id'], pharmacist["access_token"])
        self.assertEqual(approved_status, 201, body)
        item_id = UUID(json.loads(request("GET", "/inventory", token=pharmacist["access_token"])[1])[0]["id"])
        with self.Session() as session:
            item = session.get(Inventory, item_id)
            item.quantity_available = -1
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()
        with self.Session() as session:
            item = session.get(Inventory, item_id)
            duplicate = Inventory(donation_id=item.donation_id, pharmacist_id=item.pharmacist_id, medicine_name=item.medicine_name,
                expiry_date=item.expiry_date, quantity_available=1, original_quantity=1, unit=item.unit, status=InventoryStatus.AVAILABLE)
            session.add(duplicate)
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()
        with self.Session() as session:
            item = session.get(Inventory, item_id)
            item.quantity_available = 0
            session.commit()
        self.assertEqual(json.loads(request("GET", f"/inventory/{item_id}", token=pharmacist["access_token"])[1])["status"], "DEPLETED")
        with self.Session() as session:
            item = session.get(Inventory, item_id)
            item.expiry_date = datetime.fromisoformat("2020-01-01").date()
            item.quantity_available = 10
            item.status = InventoryStatus.AVAILABLE
            session.commit()
        expired_status, expired_body = request("GET", f"/inventory/{item_id}", token=pharmacist["access_token"])
        self.assertEqual(expired_status, 200, expired_body)
        self.assertEqual(json.loads(expired_body)["status"], "EXPIRED")

    def test_patient_medicine_discovery_filters_privacy_and_pagination(self):
        _, donor = self.signup("DONOR")
        _, patient = self.signup("PATIENT")
        _, pharmacist = self.signup("CLINIC_PHARMACIST")
        donor_token, patient_token, pharmacist_token = donor["access_token"], patient["access_token"], pharmacist["access_token"]
        with self.Session() as session:
            profile = session.query(ClinicProfile).filter_by(user_id=pharmacist["user"]["id"]).one()
            profile.verification_status = "VERIFIED"
            session.commit()

        def approve(name, expiry="2030-12-31"):
            status_code, body = self.create_donation(donor_token, medicine_name=name, expiry_date=expiry)
            self.assertEqual(status_code, 201, body)
            donation_id = json.loads(body)["id"]
            status_code, body = self.approve_donation(donation_id, pharmacist_token)
            self.assertEqual(status_code, 201, body)
            with self.Session() as session:
                medicine_id = session.scalar(select(Inventory.public_id).where(Inventory.donation_id == donation_id))
            return donation_id, medicine_id

        available = [approve("Paracetamol"), approve("Paracetamol Plus")]
        available_ids = [item[1] for item in available]
        with self.Session() as session:
            first = session.scalar(select(Inventory).where(Inventory.public_id == available_ids[0]))
            second = session.scalar(select(Inventory).where(Inventory.public_id == available_ids[1]))
            first.common_use_category = CommonUseCategory.COLD
            first.prescription_required = False
            second.common_use_category = CommonUseCategory.PAIN
            second.prescription_required = True
            session.commit()
        expired_donation, expired_public_id = approve("Expired Example")
        zero_donation, zero_public_id = approve("Zero Example")
        removed_donation, removed_public_id = approve("Removed Example")
        pending = json.loads(self.create_donation(donor_token, medicine_name="Unapproved Pending")[1])
        rejected = json.loads(self.create_donation(donor_token, medicine_name="Unapproved Rejected")[1])
        rejection = request(
            "POST", f"/donations/{rejected['id']}/review",
            {"decision": "REJECTED", "reason": "Package could not be verified"},
            pharmacist_token,
        )
        self.assertEqual(rejection[0], 201, rejection[1])
        nonapproved_public_ids = []
        with self.Session() as session:
            for donation_data, status in ((pending, DonationStatus.PENDING_REVIEW), (rejected, DonationStatus.REJECTED)):
                donation = session.get(Donation, UUID(donation_data["id"]))
                self.assertEqual(donation.status, status)
                inventory = Inventory(
                    donation_id=donation.id,
                    pharmacist_id=UUID(pharmacist["user"]["id"]),
                    medicine_name="Unapproved " + status.value,
                    expiry_date=date(2030, 12, 31),
                    quantity_available=2,
                    original_quantity=2,
                    unit="units",
                    common_use_category=CommonUseCategory.COLD.value,
                    prescription_required=False,
                    status=InventoryStatus.AVAILABLE,
                )
                session.add(inventory)
                session.flush()
                nonapproved_public_ids.append(inventory.public_id)
            session.commit()
        with self.Session() as session:
            expired_item = session.query(Inventory).filter_by(donation_id=expired_donation).one()
            expired_item.expiry_date = datetime.now(timezone.utc).date() - timedelta(days=1)
            zero_item = session.query(Inventory).filter_by(donation_id=zero_donation).one()
            zero_item.quantity_available = 0
            removed_item = session.query(Inventory).filter_by(donation_id=removed_donation).one()
            removed_item.status = InventoryStatus.REMOVED
            session.commit()

        self.assertEqual(request("GET", "/patient/medicines")[0], 401)
        self.assertEqual(request("GET", "/patient/medicines", token=donor_token)[0], 403)
        self.assertEqual(request("GET", "/patient/medicines", token=pharmacist_token)[0], 403)
        status_code, body = request("GET", "/patient/medicines?q=para&page_size=1", token=patient_token)
        self.assertEqual(status_code, 200, body)
        data = json.loads(body)
        self.assertEqual(data["total"], 2)
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["medicine_name"], "Paracetamol")
        self.assertEqual(request("GET", "/patient/medicines?q=PARACET&page=2&page_size=1", token=patient_token)[0], 200)
        self.assertEqual(json.loads(request("GET", "/patient/medicines?q=PARACET&page=2&page_size=1", token=patient_token)[1])["items"][0]["medicine_name"], "Paracetamol Plus")
        self.assertEqual(json.loads(request("GET", "/patient/medicines?city=pUnE", token=patient_token)[1])["total"], 2)
        self.assertEqual(json.loads(request("GET", "/patient/medicines?clinic=Test%20Clinic", token=patient_token)[1])["total"], 2)
        self.assertEqual(json.loads(request("GET", "/patient/medicines?category=COLD", token=patient_token)[1])["total"], 1)
        self.assertEqual(json.loads(request("GET", "/patient/medicines?category=PAIN", token=patient_token)[1])["total"], 1)
        self.assertEqual(request("GET", "/patient/medicines?category=UNKNOWN", token=patient_token)[0], 422)
        self.assertEqual(json.loads(request("GET", "/patient/medicines?q=Unapproved", token=patient_token)[1])["total"], 0)
        _, public_body = request("GET", "/patient/medicines", token=patient_token)
        self.assertNotIn(donor["user"]["id"], public_body)
        self.assertNotIn(pharmacist["user"]["id"], public_body)
        self.assertNotIn("donor_id", public_body)
        self.assertNotIn("pharmacist_id", public_body)
        self.assertNotIn("review", public_body)
        self.assertNotIn("reason", public_body)
        self.assertNotIn("batch_number", public_body)
        self.assertNotIn("inventory_id", public_body)
        self.assertNotIn("manufacturer", public_body)
        self.assertNotIn("pickup_address", public_body)
        self.assertNotIn("confidence", public_body)
        self.assertTrue(all(item["medicine_id"] in [str(value) for value in available_ids] for item in json.loads(public_body)["items"]))
        medicine = json.loads(public_body)["items"][0]
        self.assertEqual(medicine["common_use_category"], "COLD")
        self.assertEqual(len(medicine["images"]), 1)
        image_url = medicine["images"][0]["image_url"]
        served_image = image_request(image_url, patient_token)
        self.assertEqual(served_image[0], 200)
        self.assertEqual(served_image[1], b"\xff\xd8\xff" + b"x" * 100)
        self.assertEqual(image_request(image_url, donor_token)[0], 403)
        self.assertEqual(image_request(image_url, pharmacist_token)[0], 403)
        self.assertEqual(image_request(image_url, None)[0], 401)
        for donation in (pending, rejected):
            with self.Session() as session:
                image_id = session.scalar(select(DonationImage.id).where(DonationImage.donation_id == donation["id"]))
            self.assertEqual(image_request(f"/donations/{donation['id']}/images/{image_id}", patient_token)[0], 403)
        for unavailable_id in nonapproved_public_ids:
            self.assertEqual(image_request(f"/patient/medicines/{unavailable_id}/images/0", patient_token)[0], 404)
            self.assertEqual(self.create_patient_request(str(unavailable_id), 1, patient_token)[0], 409)
        for unavailable_id in (expired_public_id, zero_public_id, removed_public_id):
            self.assertEqual(image_request(f"/patient/medicines/{unavailable_id}/images/0", patient_token)[0], 404)

    def test_patient_requests_pharmacist_review_and_inventory_reservation(self):
        _, donor = self.signup("DONOR")
        _, patient = self.signup("PATIENT", "request")
        _, other_patient = self.signup("PATIENT", "other")
        _, pharmacist = self.signup("CLINIC_PHARMACIST", "request")
        _, other_pharmacist = self.signup("CLINIC_PHARMACIST", "other")
        donor_token = donor["access_token"]
        patient_token = patient["access_token"]
        other_patient_token = other_patient["access_token"]
        pharmacist_token = pharmacist["access_token"]
        other_pharmacist_token = other_pharmacist["access_token"]
        with self.Session() as session:
            profile = session.query(ClinicProfile).filter_by(user_id=pharmacist["user"]["id"]).one()
            profile.verification_status = "VERIFIED"
            session.commit()

        donation = json.loads(self.create_donation(donor_token, quantity=10)[1])
        pharmacist_notices = json.loads(request("GET", "/notifications", token=pharmacist_token)[1])["items"]
        self.assertEqual([n["type"] for n in pharmacist_notices], ["DONATION_AWAITING_REVIEW"])
        reviewed_status, reviewed_body = self.approve_donation(donation['id'], pharmacist_token)
        self.assertEqual(reviewed_status, 201, reviewed_body)
        with self.Session() as session:
            inventory_id = str(session.query(Inventory.id).filter_by(donation_id=donation["id"]).scalar())
            item = session.get(Inventory, inventory_id)
            item.common_use_category = CommonUseCategory.COLD
            item.prescription_required = False
            session.commit()

        self.assertEqual(self.create_patient_request(inventory_id, 1, donor_token)[0], 403)
        self.assertEqual(self.create_patient_request(inventory_id, 0, patient_token)[0], 422)
        self.assertEqual(self.create_patient_request(inventory_id, -1, patient_token)[0], 422)
        with self.Session() as session:
            medicine_id = str(session.get(Inventory, inventory_id).public_id)
        self.assertEqual(request("POST", "/patient/requests", {
            "medicine_id": medicine_id, "requested_quantity": 1,
        }, patient_token)[0], 422)
        self.assertEqual(self.create_patient_request(inventory_id, 1, patient_token, "   ")[0], 422)
        pickup_address = "42 Patient Lane, Pune"
        _, body = self.create_patient_request(inventory_id, 6, patient_token, pickup_address)
        created = json.loads(body)
        self.assertEqual(created["status"], "PENDING")
        self.assertEqual(created["pickup_address"], pickup_address)
        request_id = created["id"]
        with self.Session() as session:
            self.assertEqual(session.get(Inventory, inventory_id).quantity_available, 4)
        self.assertEqual(self.create_patient_request(inventory_id, 5, other_patient_token)[0], 409)
        with self.Session() as session:
            self.assertEqual(session.get(Inventory, inventory_id).quantity_available, 4)
        pharmacist_notices = json.loads(request("GET", "/notifications", token=pharmacist_token)[1])["items"]
        self.assertEqual(pharmacist_notices[0]["type"], "NEW_MEDICINE_REQUEST")
        self.assertEqual(pharmacist_notices[0]["related_entity_id"], request_id)
        self.assertEqual(request("GET", f"/patient/requests/{request_id}", token=other_patient_token)[0], 404)
        patient_request = json.loads(request("GET", f"/patient/requests/{request_id}", token=patient_token)[1])
        self.assertEqual(patient_request["pickup_address"], pickup_address)
        self.assertEqual(request("GET", f"/patient/requests/{request_id}", token=donor_token)[0], 403)
        with self.Session() as session:
            self.assertEqual(session.get(MedicineRequest, request_id).pickup_address, pickup_address)
        self.assertEqual(request("POST", f"/pharmacist/requests/{request_id}/approve", token=patient_token)[0], 403)
        self.assertEqual(request("POST", f"/pharmacist/requests/{request_id}/reject", {"reason": "No"}, patient_token)[0], 403)
        self.assertEqual(request("GET", "/pharmacist/requests", token=donor_token)[0], 403)
        self.assertEqual(request("GET", "/pharmacist/requests", token=patient_token)[0], 403)
        listed = json.loads(request("GET", "/pharmacist/requests", token=pharmacist_token)[1])
        self.assertEqual([row["id"] for row in listed], [request_id])
        self.assertEqual(listed[0]["pickup_address"], pickup_address)
        self.assertEqual(request("GET", f"/pharmacist/requests/{request_id}", token=other_pharmacist_token)[0], 404)
        self.assertEqual(request("POST", f"/pharmacist/requests/{request_id}/approve", token=other_pharmacist_token)[0], 404)
        self.assertEqual(request("POST", f"/pharmacist/requests/{request_id}/reject", {"reason": "  "}, pharmacist_token)[0], 422)

        # A second pending request can no longer be fulfilled after the first reserves stock.
        _, second_body = self.create_patient_request(inventory_id, 4, other_patient_token)
        second_id = json.loads(second_body)["id"]
        with self.Session() as session:
            self.assertEqual(session.get(Inventory, inventory_id).quantity_available, 0)
        self.assertEqual(self.create_patient_request(inventory_id, 1, other_patient_token)[0], 409)
        approved_status, approved_body = request("POST", f"/pharmacist/requests/{request_id}/approve", token=pharmacist_token)
        self.assertEqual(approved_status, 200, approved_body)
        self.assertEqual(json.loads(approved_body)["status"], "APPROVED")
        patient_notices = json.loads(request("GET", "/notifications", token=patient_token)[1])["items"]
        self.assertEqual({n["type"] for n in patient_notices}, {"REQUEST_APPROVED", "READY_FOR_PICKUP"})
        self.assertEqual(request("POST", f"/pharmacist/requests/{request_id}/approve", token=pharmacist_token)[0], 409)
        with self.Session() as session:
            self.assertEqual(session.get(Inventory, inventory_id).quantity_available, 0)

        patient_list = json.loads(request("GET", "/patient/requests", token=patient_token)[1])
        self.assertEqual(patient_list[0]["status"], "APPROVED")
        self.assertEqual(patient_list[0]["pickup_address"], pickup_address)

        rejected_status, rejected_body = request("POST", f"/pharmacist/requests/{second_id}/reject", {"reason": "Insufficient stock"}, pharmacist_token)
        self.assertEqual(rejected_status, 200, rejected_body)
        self.assertEqual(json.loads(rejected_body)["status"], "REJECTED")
        with self.Session() as session:
            self.assertEqual(session.get(Inventory, inventory_id).quantity_available, 4)

        expired_donation = json.loads(self.create_donation(donor_token)[1])
        self.approve_donation(expired_donation['id'], pharmacist_token)
        with self.Session() as session:
            expired_item = session.query(Inventory).filter_by(donation_id=expired_donation["id"]).one()
            expired_item.expiry_date = datetime.fromisoformat("2000-01-01").date()
            expired_id = str(expired_item.id)
            session.commit()
        self.assertEqual(self.create_patient_request(expired_id, 1, patient_token)[0], 409)
        self.assertEqual(self.create_patient_request("00000000-0000-0000-0000-000000000001", 1, patient_token)[0], 404)
        self.assertEqual(self.create_patient_request(inventory_id, 5, patient_token)[0], 409)
        with self.Session() as session:
            regular_item = session.get(Inventory, inventory_id)
            regular_item.quantity_available = 0
            session.commit()
        self.assertEqual(self.create_patient_request(inventory_id, 1, patient_token)[0], 409)

    def test_common_use_categories_allow_direct_requests_and_other_categories_require_prescription(self):
        _, donor = self.signup("DONOR", "category-gates")
        _, patient = self.signup("PATIENT", "category-gates")
        _, pharmacist = self.signup("CLINIC_PHARMACIST", "category-gates")
        with self.Session() as session:
            session.query(ClinicProfile).filter_by(user_id=pharmacist["user"]["id"]).one().verification_status = "VERIFIED"
            session.commit()
        donation = json.loads(self.create_donation(donor["access_token"], quantity=10)[1])
        self.assertEqual(self.approve_donation(donation["id"], pharmacist["access_token"])[0], 201)
        with self.Session() as session:
            item = session.query(Inventory).filter_by(donation_id=donation["id"]).one()
            inventory_id = str(item.id)

        for category in (CommonUseCategory.COLD, CommonUseCategory.COUGH, CommonUseCategory.FLU, CommonUseCategory.FEVER):
            with self.Session() as session:
                item = session.get(Inventory, inventory_id)
                item.common_use_category = category
                item.prescription_required = False
                session.commit()
            created_status, created_body = self.create_patient_request(inventory_id, 1, patient["access_token"])
            self.assertEqual(created_status, 201, created_body)
            created = json.loads(created_body)
            self.assertFalse(created["prescription_required"])
            self.assertEqual(created["prescription_status"], "NOT_REQUIRED")
            approved_status = request("POST", f"/pharmacist/requests/{created['id']}/approve", token=pharmacist["access_token"])[0]
            self.assertEqual(approved_status, 200, f"{category.value} direct request should not require a prescription")

        for category in (CommonUseCategory.PAIN, CommonUseCategory.ALLERGY, CommonUseCategory.OTHER, CommonUseCategory.UNCLASSIFIED):
            with self.Session() as session:
                item = session.get(Inventory, inventory_id)
                item.common_use_category = category
                item.prescription_required = True
                session.commit()
            missing_prescription_status, _ = self.create_patient_request(inventory_id, 1, patient["access_token"])
            self.assertEqual(missing_prescription_status, 409, f"{category.value} requires prescription at request submission")
            created_status, created_body = self.create_patient_request_with_prescription(
                inventory_id, 1, patient["access_token"], pickup_address=f"Pickup for {category.value}"
            )
            self.assertEqual(created_status, 201, created_body)
            created = json.loads(created_body)
            self.assertTrue(created["prescription_required"])
            self.assertEqual(created["pickup_address"], f"Pickup for {category.value}")
            self.assertEqual(created["prescription_status"], "PENDING_REVIEW")
            self.assertEqual(request("POST", f"/pharmacist/requests/{created['id']}/approve", token=pharmacist["access_token"])[0], 409)

    def test_request_creation_reserves_inventory_once_and_concurrent_requests_cannot_overallocate(self):
        _, donor = self.signup("DONOR", "request-reservation")
        _, patient = self.signup("PATIENT", "request-reservation")
        _, pharmacist = self.signup("CLINIC_PHARMACIST", "request-reservation")
        with self.Session() as session:
            session.query(ClinicProfile).filter_by(user_id=pharmacist["user"]["id"]).one().verification_status = "VERIFIED"
            session.commit()
        donation = json.loads(self.create_donation(donor["access_token"], quantity=9)[1])
        self.assertEqual(self.approve_donation(donation["id"], pharmacist["access_token"])[0], 201)
        with self.Session() as session:
            inventory = session.query(Inventory).filter_by(donation_id=donation["id"]).one()
            inventory.common_use_category = CommonUseCategory.COLD
            inventory.prescription_required = False
            inventory_id = str(inventory.id)
            session.commit()

        created_status, created_body = self.create_patient_request(inventory_id, 1, patient["access_token"])
        self.assertEqual(created_status, 201, created_body)
        request_id = json.loads(created_body)["id"]
        with self.Session() as session:
            inventory = session.get(Inventory, inventory_id)
            self.assertEqual(inventory.quantity_available, 8)
            self.assertTrue(session.get(MedicineRequest, request_id).inventory_reserved)

        approved_status, approved_body = request(
            "POST", f"/pharmacist/requests/{request_id}/approve", token=pharmacist["access_token"]
        )
        self.assertEqual(approved_status, 200, approved_body)
        with self.Session() as session:
            self.assertEqual(session.get(Inventory, inventory_id).quantity_available, 8)

        before_failed_request = 8
        self.assertEqual(self.create_patient_request(inventory_id, before_failed_request + 1, patient["access_token"])[0], 409)
        self.assertEqual(self.create_patient_request("00000000-0000-0000-0000-000000000001", 1, patient["access_token"])[0], 404)
        with self.Session() as session:
            self.assertEqual(session.get(Inventory, inventory_id).quantity_available, before_failed_request)

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(
                lambda _: self.create_patient_request(inventory_id, 5, patient["access_token"])[0],
                range(2),
            ))
        self.assertEqual(sorted(outcomes), [201, 409])
        with self.Session() as session:
            self.assertEqual(session.get(Inventory, inventory_id).quantity_available, 3)

    def test_configurable_pricing_snapshot_simulated_checkout_and_free_flow(self):
        _, donor = self.signup("DONOR", "pricing")
        _, patient = self.signup("PATIENT", "pricing")
        _, other_patient = self.signup("PATIENT", "pricing-other")
        _, pharmacist = self.signup("CLINIC_PHARMACIST", "pricing")
        _, other_pharmacist = self.signup("CLINIC_PHARMACIST", "pricing-other")
        with self.Session() as session:
            session.query(ClinicProfile).filter_by(user_id=pharmacist["user"]["id"]).one().verification_status = "VERIFIED"
            session.query(ClinicProfile).filter_by(user_id=other_pharmacist["user"]["id"]).one().verification_status = "VERIFIED"
            session.commit()
        donation = json.loads(self.create_donation(donor["access_token"], quantity=8)[1])
        self.assertEqual(self.approve_donation(donation['id'], pharmacist["access_token"])[0], 201)
        with self.Session() as session:
            item = session.query(Inventory).filter_by(donation_id=donation["id"]).one()
            item.common_use_category = CommonUseCategory.COLD
            item.prescription_required = False
            inventory_id = str(item.id)
            session.commit()
        pricing = {"original_price": "100.00", "discount_percentage": "25.00"}
        configured = request("PATCH", f"/inventory/{inventory_id}/pricing", pricing, pharmacist["access_token"])
        self.assertEqual(configured[0], 200, configured[1])
        self.assertEqual(json.loads(configured[1])["patient_price"], "75.00")
        self.assertEqual(request("PATCH", f"/inventory/{inventory_id}/pricing", pricing, other_pharmacist["access_token"])[0], 404)
        self.assertEqual(request("PATCH", f"/inventory/{inventory_id}/pricing", {"original_price": "-1", "discount_percentage": "0"}, pharmacist["access_token"])[0], 422)
        self.assertEqual(request("PATCH", f"/inventory/{inventory_id}/pricing", {"original_price": "100", "discount_percentage": "101"}, pharmacist["access_token"])[0], 422)
        discovered = json.loads(request("GET", "/patient/medicines", token=patient["access_token"])[1])
        with self.Session() as session:
            medicine_id = str(session.scalar(select(Inventory.public_id).where(Inventory.id == UUID(inventory_id))))
        visible = next(row for row in discovered["items"] if row["medicine_id"] == medicine_id)
        self.assertEqual(visible["patient_price"], "75.00")
        created = json.loads(self.create_patient_request(inventory_id, 2, patient["access_token"])[1])
        request_id = created["id"]
        self.assertEqual(created["patient_price_snapshot"], "75.00")
        self.assertIsNone(created["payment_status"])
        self.assertEqual(request("GET", f"/patient/checkout/{request_id}", token=patient["access_token"])[0], 409)
        self.assertEqual(request("GET", f"/patient/checkout/{request_id}", token=other_patient["access_token"])[0], 404)
        request("PATCH", f"/inventory/{inventory_id}/pricing", {"original_price": "200", "discount_percentage": "50"}, pharmacist["access_token"])
        approved = request("POST", f"/pharmacist/requests/{request_id}/approve", token=pharmacist["access_token"])
        self.assertEqual(approved[0], 200, approved[1])
        checkout_status, checkout_body = request("GET", f"/patient/checkout/{request_id}", token=patient["access_token"])
        self.assertEqual(checkout_status, 200, checkout_body)
        checkout = json.loads(checkout_body)
        self.assertEqual(checkout["amount"], "150.00")
        self.assertEqual(checkout["original_price"], "100.00")
        listed_checkout_status = json.loads(request("GET", "/patient/requests", token=patient["access_token"])[1])[0]["payment_status"]
        self.assertEqual(listed_checkout_status, "PENDING")
        self.assertEqual(request("POST", f"/pharmacist/requests/{request_id}/dispense", token=pharmacist["access_token"])[0], 409)
        paid_status, paid_body = request("POST", f"/patient/checkout/{request_id}/demo-pay", token=patient["access_token"])
        self.assertEqual(paid_status, 200, paid_body)
        self.assertEqual(json.loads(paid_body)["payment_status"], "PAID")
        listed_paid_status = json.loads(request("GET", "/patient/requests", token=patient["access_token"])[1])[0]["payment_status"]
        self.assertEqual(listed_paid_status, "PAID")
        repeated = request("POST", f"/patient/checkout/{request_id}/demo-pay", token=patient["access_token"])
        self.assertEqual(repeated[0], 200, repeated[1])
        with self.Session() as session:
            self.assertEqual(session.query(Checkout).filter_by(request_id=request_id).count(), 1)
            self.assertEqual(session.get(Inventory, inventory_id).quantity_available, 6)
        self.assertEqual(request("POST", f"/pharmacist/requests/{request_id}/dispense", token=pharmacist["access_token"])[0], 200)

        free_update = request("PATCH", f"/inventory/{inventory_id}/pricing", {"original_price": "0", "discount_percentage": "0"}, pharmacist["access_token"])
        self.assertEqual(free_update[0], 200, free_update[1])
        free_request = json.loads(self.create_patient_request(inventory_id, 1, patient["access_token"])[1])
        request("POST", f"/pharmacist/requests/{free_request['id']}/approve", token=pharmacist["access_token"])
        free_checkout_status, free_checkout_body = request("GET", f"/patient/checkout/{free_request['id']}", token=patient["access_token"])
        self.assertEqual(free_checkout_status, 200, free_checkout_body)
        free_checkout = json.loads(free_checkout_body)
        self.assertTrue(free_checkout["is_free"])
        self.assertEqual(free_checkout["payment_method"], "FREE")
        self.assertEqual(free_checkout["amount"], "0.00")
        self.assertEqual(free_checkout["payment_status"], "PAID")

    def test_dispensing_audit_authorization_and_no_second_inventory_decrement(self):
        _, donor = self.signup("DONOR", "dispense")
        _, patient = self.signup("PATIENT", "dispense")
        _, other_patient = self.signup("PATIENT", "dispense-other")
        _, pharmacist = self.signup("CLINIC_PHARMACIST", "dispense")
        _, other_pharmacist = self.signup("CLINIC_PHARMACIST", "dispense-other")
        with self.Session() as session:
            session.query(ClinicProfile).filter_by(user_id=pharmacist["user"]["id"]).one().verification_status = "VERIFIED"
            session.query(ClinicProfile).filter_by(user_id=other_pharmacist["user"]["id"]).one().verification_status = "VERIFIED"
            session.commit()

        def approved_inventory(pharmacist_token, quantity=10, prescription_required=False):
            donation = json.loads(self.create_donation(donor["access_token"], quantity=quantity)[1])
            self.assertEqual(self.approve_donation(donation['id'], pharmacist_token)[0], 201)
            with self.Session() as session:
                item = session.query(Inventory).filter_by(donation_id=donation["id"]).one()
                item.common_use_category = CommonUseCategory.PAIN if prescription_required else CommonUseCategory.COLD
                item.prescription_required = prescription_required
                item_id = str(item.id)
                session.commit()
            return item_id

        inv = approved_inventory(pharmacist["access_token"])
        request_id = json.loads(self.create_patient_request(inv, 3, patient["access_token"])[1])["id"]
        self.assertEqual(request("GET", "/patient/dispensing", token=donor["access_token"])[0], 403)
        self.assertEqual(request("GET", "/pharmacist/dispensing", token=patient["access_token"])[0], 403)
        self.assertEqual(request("GET", "/patient/requests", token=donor["access_token"])[0], 403)
        self.assertEqual(request("POST", f"/pharmacist/requests/{request_id}/dispense", token=patient["access_token"])[0], 403)
        self.assertEqual(request("POST", f"/pharmacist/requests/{request_id}/dispense", token=other_pharmacist["access_token"])[0], 404)
        self.assertEqual(request("POST", f"/pharmacist/requests/{request_id}/dispense", token=pharmacist["access_token"])[0], 409)
        approved, body = request("POST", f"/pharmacist/requests/{request_id}/approve", token=pharmacist["access_token"])
        self.assertEqual(approved, 200, body)
        pickup = json.loads(body)["pickup_code"]
        self.assertRegex(pickup, r"^MS-[0-9A-F]{6}$")
        other_approved_id = json.loads(self.create_patient_request(inv, 1, other_patient["access_token"])[1])["id"]
        other_approved, other_body = request("POST", f"/pharmacist/requests/{other_approved_id}/approve", token=pharmacist["access_token"])
        self.assertEqual(other_approved, 200, other_body)
        self.assertNotEqual(json.loads(other_body)["pickup_code"], pickup)
        self.assertEqual(json.loads(request("GET", "/pharmacist/dispensing", token=pharmacist["access_token"])[1])[0]["pickup_code"], pickup)
        self.assertEqual(request("GET", f"/patient/requests/{request_id}/dispensing", token=other_patient["access_token"])[0], 404)
        patient_data = json.loads(request("GET", f"/patient/requests/{request_id}/dispensing", token=patient["access_token"])[1])
        self.assertEqual(patient_data["pickup_code"], pickup)
        for private_key in ("pharmacist_id", "inventory_id", "patient_id", "id", "request_id", "storage_key"):
            self.assertNotIn(private_key, patient_data)

        with self.Session() as session:
            before = session.get(Inventory, inv).quantity_available
        code, body = request("POST", f"/pharmacist/requests/{request_id}/dispense", token=pharmacist["access_token"])
        self.assertEqual(code, 200, body)
        result = json.loads(body)
        self.assertEqual(result["status"], "FULFILLED")
        self.assertEqual(result["quantity"], 3)
        with self.Session() as session:
            self.assertEqual(session.get(Inventory, inv).quantity_available, before)
            record = session.query(DispensingRecord).filter_by(request_id=request_id).one()
            self.assertEqual(str(record.pharmacist_id), pharmacist["user"]["id"])
            self.assertEqual(record.quantity_dispensed, 3)
            self.assertIsNotNone(record.dispensed_at)
            self.assertIsNotNone(session.get(MedicineRequest, request_id).fulfilled_at)
        self.assertEqual(request("POST", f"/pharmacist/requests/{request_id}/dispense", token=pharmacist["access_token"])[0], 409)
        self.assertEqual(json.loads(request("GET", "/patient/dispensing", token=patient["access_token"])[1])[0]["status"], "FULFILLED")

        # Separate pending, cancelled, rejected and prescription-gated records are not dispensable.
        pending = json.loads(self.create_patient_request(inv, 1, other_patient["access_token"])[1])["id"]
        self.assertEqual(request("POST", f"/pharmacist/requests/{pending}/dispense", token=pharmacist["access_token"])[0], 409)
        rejected = json.loads(self.create_patient_request(inv, 1, other_patient["access_token"])[1])["id"]
        self.assertEqual(request("POST", f"/pharmacist/requests/{rejected}/reject", {"reason": "Rejected"}, pharmacist["access_token"])[0], 200)
        self.assertEqual(request("POST", f"/pharmacist/requests/{rejected}/dispense", token=pharmacist["access_token"])[0], 409)
        cancelled = json.loads(self.create_patient_request(inv, 1, other_patient["access_token"])[1])["id"]
        with self.Session() as session:
            session.get(MedicineRequest, cancelled).status = MedicineRequestStatus.CANCELLED
            session.commit()
        self.assertEqual(request("POST", f"/pharmacist/requests/{cancelled}/dispense", token=pharmacist["access_token"])[0], 409)

        rx_inv = approved_inventory(pharmacist["access_token"], prescription_required=True)
        rx_response = self.create_patient_request_with_prescription(rx_inv, 1, other_patient["access_token"])
        self.assertEqual(rx_response[0], 201, rx_response[1])
        rx_pending = json.loads(rx_response[1])["id"]
        self.assertEqual(request("POST", f"/pharmacist/requests/{rx_pending}/approve", token=pharmacist["access_token"])[0], 409)
        with self.Session() as session:
            session.get(MedicineRequest, rx_pending).status = MedicineRequestStatus.APPROVED
            session.get(MedicineRequest, rx_pending).pickup_code = "MS-123ABC"
            session.commit()
        self.assertEqual(request("POST", f"/pharmacist/requests/{rx_pending}/dispense", token=pharmacist["access_token"])[0], 409)

        unreserved = json.loads(self.create_patient_request(inv, 1, other_patient["access_token"])[1])["id"]
        with self.Session() as session:
            row = session.get(MedicineRequest, unreserved)
            row.status = MedicineRequestStatus.APPROVED
            row.pickup_code = None
            session.commit()
        self.assertEqual(request("POST", f"/pharmacist/requests/{unreserved}/dispense", token=pharmacist["access_token"])[0], 409)

    def test_donation_quantity_and_expiry_validation(self):
        _, donor = self.signup("DONOR")
        token = donor["access_token"]
        self.assertEqual(request("POST", "/donations", {"pickup_address": "12 Sample Road", "quantity": 0}, token)[0], 422)
        self.assertEqual(request("POST", "/donations", {"pickup_address": "12 Sample Road", "quantity": -1}, token)[0], 422)
        self.assertEqual(request("POST", "/donations", {"pickup_address": "12 Sample Road", "donor_expiry_date": "2020-01-01"}, token)[0], 422)

    def test_expiry_and_waste_lifecycle(self):
        _, donor = self.signup("DONOR", "waste")
        _, patient = self.signup("PATIENT", "waste")
        _, pharmacist = self.signup("CLINIC_PHARMACIST", "waste")
        donor_token, patient_token, pharmacist_token = donor["access_token"], patient["access_token"], pharmacist["access_token"]
        soon = json.loads(self.create_donation(donor_token, expiry_date=(datetime.now(timezone.utc).date() + timedelta(days=45)).isoformat())[1])
        self.assertEqual(self.approve_donation(soon['id'], pharmacist_token)[0], 201)
        expiring_status, expiring_body = request("GET", "/pharmacist/inventory/expiring", token=pharmacist_token)
        self.assertEqual(expiring_status, 200, expiring_body)
        self.assertTrue(any(row["medicine_name"] == "Paracetamol" and row["days_remaining"] == 45 for row in json.loads(expiring_body)))
        donation = json.loads(self.create_donation(donor_token, medicine_name="Expired Waste Test")[1])
        self.assertEqual(self.approve_donation(donation['id'], pharmacist_token)[0], 201)
        with self.Session() as session:
            inventory = session.query(Inventory).filter_by(donation_id=donation["id"]).one()
            inventory.expiry_date = datetime.now(timezone.utc).date() - timedelta(days=1)
            inventory_id, inventory_uuid = str(inventory.id), inventory.id
            session.commit()
        expired_status, expired_body = request("GET", "/pharmacist/inventory/expired", token=pharmacist_token)
        self.assertEqual(expired_status, 200, expired_body)
        self.assertEqual(json.loads(expired_body)[0]["id"], inventory_id)
        expiry_types = {n["type"] for n in json.loads(request("GET", "/notifications", token=pharmacist_token)[1])["items"]}
        self.assertIn("MEDICINE_EXPIRING_SOON", expiry_types)
        self.assertIn("MEDICINE_EXPIRED", expiry_types)
        self.assertNotIn("Expired Waste Test", request("GET", "/patient/medicines", token=patient_token)[1])
        self.assertEqual(self.create_patient_request(inventory_id, 1, patient_token)[0], 409)
        self.assertEqual(request("POST", f"/pharmacist/inventory/{inventory_id}/waste", {"reason": "EXPIRED", "quantity": 25}, pharmacist_token)[0], 409)
        self.assertEqual(request("POST", f"/pharmacist/inventory/{inventory_id}/waste", {"reason": "EXPIRED", "quantity": 5}, patient_token)[0], 403)
        self.assertEqual(request("POST", f"/pharmacist/inventory/{inventory_id}/waste", {"reason": "EXPIRED", "quantity": 5}, donor_token)[0], 403)
        waste_status, waste_body = request("POST", f"/pharmacist/inventory/{inventory_id}/waste", {"reason": "EXPIRED", "quantity": 5}, pharmacist_token)
        self.assertEqual(waste_status, 201, waste_body)
        waste = json.loads(waste_body)
        self.assertTrue(waste["disposal_reference"].startswith("MW-"))
        self.assertEqual(waste["status"], "DISPOSAL_PENDING")
        waste_notice = json.loads(request("GET", "/notifications", token=pharmacist_token)[1])["items"][0]
        self.assertEqual(waste_notice["type"], "WASTE_DISPOSAL_PENDING")
        self.assertEqual(waste_notice["related_entity_id"], waste["id"])
        with self.Session() as session:
            self.assertIsNotNone(session.get(Inventory, inventory_uuid))
            self.assertEqual(session.get(Inventory, inventory_uuid).quantity_available, 19)
        self.assertEqual(request("POST", f"/pharmacist/waste/{waste['id']}/dispose", token=pharmacist_token)[0], 409)
        self.assertEqual(request("POST", f"/pharmacist/waste/{waste['id']}/collect", token=pharmacist_token)[0], 200)
        self.assertEqual(request("POST", f"/pharmacist/waste/{waste['id']}/dispose", token=pharmacist_token)[0], 200)
        self.assertEqual(request("POST", f"/pharmacist/waste/{waste['id']}/collect", token=pharmacist_token)[0], 409)
        self.assertEqual(request("GET", "/pharmacist/waste", token=patient_token)[0], 403)
        _, other_pharmacist = self.signup("CLINIC_PHARMACIST", "waste-other")
        other_token = other_pharmacist["access_token"]
        self.assertEqual(request("GET", f"/pharmacist/waste/{waste['id']}", token=other_token)[0], 404)
        self.assertEqual(request("POST", f"/pharmacist/inventory/{inventory_id}/waste", {"reason": "EXPIRED", "quantity": 1}, other_token)[0], 404)
        unverified_rejection = json.loads(self.create_donation(donor_token)[1])
        rejected_status = request(
            "POST", f"/donations/{unverified_rejection['id']}/review",
            {"decision": "REJECTED", "reason": "Unable to verify quantity"},
            pharmacist_token,
        )
        self.assertEqual(rejected_status[0], 201, rejected_status[1])
        missing_quantity_waste = request(
            "POST", f"/pharmacist/donations/{unverified_rejection['id']}/waste",
            {"reason": "REJECTED_DONATION", "quantity": 1}, pharmacist_token,
        )
        self.assertEqual(missing_quantity_waste[0], 409, missing_quantity_waste[1])
        rejected = json.loads(self.create_donation(donor_token)[1])
        rejected_details = dict(self.donation_verification[rejected["id"]])
        rejected_review = request(
            "POST", f"/donations/{rejected['id']}/review",
            {"decision": "REJECTED", "reason": "Damaged package", "physical_package_checked": True,
             "verified_details": rejected_details},
            pharmacist_token,
        )
        self.assertEqual(rejected_review[0], 201, rejected_review[1])
        status_code, body = request("POST", f"/pharmacist/donations/{rejected['id']}/waste", {"reason": "REJECTED_DONATION", "quantity": 3}, pharmacist_token)
        self.assertEqual(status_code, 201, body)
        rejected_waste = json.loads(body)
        self.assertEqual(rejected_waste["donation_id"], rejected["id"])
        self.assertIsNone(rejected_waste["inventory_id"])
        with self.Session() as session:
            self.assertIsNone(session.query(Inventory).filter_by(donation_id=rejected["id"]).one_or_none())

    def test_pharmacist_dashboard_access_and_clinic_isolation(self):
        _, donor = self.signup("DONOR")
        _, patient = self.signup("PATIENT")
        _, pharmacy_a = self.signup("CLINIC_PHARMACIST", "-a")
        _, pharmacy_b = self.signup("CLINIC_PHARMACIST", "-b")
        self.assertEqual(request("GET", "/pharmacist/dashboard")[0], 401)
        self.assertEqual(request("GET", "/pharmacist/dashboard", token=donor["access_token"])[0], 403)
        self.assertEqual(request("GET", "/pharmacist/dashboard", token=patient["access_token"])[0], 403)

        shared_pending = json.loads(self.create_donation(donor["access_token"], medicine_name="Shared review queue medicine")[1])
        inventory_ids = []
        for pharmacist, suffix in ((pharmacy_a, "A"), (pharmacy_b, "B")):
            donation = json.loads(self.create_donation(donor["access_token"], medicine_name=f"Clinic {suffix} medicine")[1])
            status, body = self.approve_donation(donation['id'], pharmacist["access_token"])
            self.assertEqual(status, 201, body)
            with self.Session() as session:
                inventory = session.scalar(select(Inventory).where(Inventory.donation_id == UUID(donation["id"])))
                inventory.original_price = 25
                inventory.discount_percentage = 0
                inventory.patient_price = 25
                inventory.common_use_category = "PAIN"
                inventory.prescription_required = True
                if suffix == "A":
                    inventory.expiry_date = date.today() + timedelta(days=10)
                session.flush()
                request_row = MedicineRequest(patient_id=UUID(patient["user"]["id"]), inventory_id=inventory.id, requested_quantity=1)
                session.add(request_row)
                session.flush()
                session.add(Prescription(request_id=request_row.id, storage_key=f"dashboard-{suffix}.pdf", original_filename="prescription.pdf", content_type="application/pdf", size_bytes=10))
                session.add(WasteRecord(inventory_id=inventory.id, pharmacist_id=UUID(pharmacist["user"]["id"]), reason=WasteReason.DAMAGED, quantity=1, disposal_reference=f"MW-{suffix}12345", status=WasteStatus.DISPOSAL_PENDING))
                session.add(Notification(recipient_user_id=UUID(pharmacist["user"]["id"]), type=NotificationType.NEW_MEDICINE_REQUEST, title="Test", message="Test", is_read=False))
                inventory_ids.append(str(inventory.id))
                session.commit()

        extra_donation = json.loads(self.create_donation(donor["access_token"], medicine_name="Expired clinic medicine")[1])
        status, body = self.approve_donation(extra_donation['id'], pharmacy_a["access_token"])
        self.assertEqual(status, 201, body)
        with self.Session() as session:
            expired_item = session.scalar(select(Inventory).where(Inventory.donation_id == UUID(extra_donation["id"])))
            expired_item.expiry_date = date.today() - timedelta(days=1)
            expired_item.status = InventoryStatus.EXPIRED
            session.commit()
        missing_price_donation = json.loads(self.create_donation(donor["access_token"], medicine_name="Unpriced clinic medicine")[1])
        status, body = self.approve_donation(missing_price_donation['id'], pharmacy_a["access_token"])
        self.assertEqual(status, 201, body)
        with self.Session() as session:
            clinic_inventory = session.get(Inventory, UUID(inventory_ids[0]))
            session.add(MedicineRequest(patient_id=UUID(patient["user"]["id"]), inventory_id=clinic_inventory.id,
                requested_quantity=1, status=MedicineRequestStatus.APPROVED, pickup_code="MS-READY1"))
            session.commit()

        status, response = request("GET", "/pharmacist/dashboard", token=pharmacy_a["access_token"])
        self.assertEqual(status, 200, response)
        dashboard = json.loads(response)
        self.assertEqual(dashboard["summary"]["pending_requests"], 1)
        self.assertEqual(dashboard["summary"]["pending_donations"], 1)
        self.assertEqual(dashboard["summary"]["pending_prescriptions"], 1)
        self.assertEqual(dashboard["summary"]["ready_for_dispensing"], 1)
        self.assertEqual(dashboard["summary"]["expiring_soon"], 1)
        self.assertEqual(dashboard["summary"]["expired"], 1)
        self.assertEqual(dashboard["summary"]["waste_pending"], 1)
        self.assertEqual(dashboard["summary"]["unread_notifications"], 2)
        self.assertEqual(dashboard["inventory"]["pricing_configured"], 1)
        self.assertEqual(dashboard["inventory"]["pricing_missing"], 1)
        self.assertEqual(len(dashboard["pending_requests"]), 1)
        self.assertEqual(dashboard["pending_requests"][0]["medicine_name"], "Clinic A medicine")
        self.assertNotIn("dashboard-A.pdf", json.dumps(dashboard))
        self.assertNotIn(inventory_ids[1], response)

    def test_donation_packaging_schema_repair_restores_pharmacist_endpoints(self):
        _, pharmacist = self.signup("CLINIC_PHARMACIST", "-schema-repair")
        migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261004_0015_repair_donation_packaging_type.py"
        spec = importlib.util.spec_from_file_location("repair_donation_packaging_type", migration_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE donations DROP COLUMN packaging_type"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            columns = {column["name"] for column in inspect(connection).get_columns("donations")}
            self.assertIn("packaging_type", columns)

        for path in ("/pharmacist/dashboard", "/donations/review-queue"):
            status, body = request("GET", path, token=pharmacist["access_token"])
            self.assertEqual(status, 200, body)

    def test_cors_allows_vite_loopback_fallback_port_with_authorization_preflight(self):
        req = Request(self.base_url + "/pharmacist/dashboard", headers={
            "Origin": "http://localhost:5174",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        }, method="OPTIONS")
        with urlopen(req, timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "http://localhost:5174")
            self.assertIn("authorization", response.headers.get("Access-Control-Allow-Headers", "").lower())

    def test_prescription_upload_review_reupload_authorization_and_reservation_gate(self):
        _, donor = self.signup("DONOR", "rx")
        _, patient = self.signup("PATIENT", "rx")
        _, other_patient = self.signup("PATIENT", "rx-other")
        _, pharmacist = self.signup("CLINIC_PHARMACIST", "rx")
        _, other_pharmacist = self.signup("CLINIC_PHARMACIST", "rx-other")
        with self.Session() as session:
            session.query(ClinicProfile).filter_by(user_id=pharmacist["user"]["id"]).one().verification_status = "VERIFIED"
            session.query(ClinicProfile).filter_by(user_id=other_pharmacist["user"]["id"]).one().verification_status = "VERIFIED"
            session.commit()
        donation = json.loads(self.create_donation(donor["access_token"], quantity=9)[1])
        self.assertEqual(self.approve_donation(donation['id'], pharmacist["access_token"])[0], 201)
        with self.Session() as session:
            item = session.query(Inventory).filter_by(donation_id=donation["id"]).one()
            item.common_use_category = CommonUseCategory.PAIN
            item.prescription_required = True
            inventory_id = str(item.id)
            initial_quantity = item.quantity_available
            session.commit()
        missing = self.create_patient_request(inventory_id, 2, patient["access_token"])
        self.assertEqual(missing[0], 409)
        malformed = self.create_patient_request_with_prescription(
            inventory_id, 2, patient["access_token"], content=b"not a pdf", filename="bad.pdf"
        )
        self.assertEqual(malformed[0], 415)
        too_much = self.create_patient_request_with_prescription(
            inventory_id, initial_quantity + 1, patient["access_token"]
        )
        self.assertEqual(too_much[0], 409)
        self.assertEqual(json.loads(request("GET", "/patient/requests", token=patient["access_token"])[1]), [])
        with self.Session() as session:
            self.assertEqual(session.get(Inventory, inventory_id).quantity_available, initial_quantity)
        created_status, created_body = self.create_patient_request_with_prescription(
            inventory_id, 2, patient["access_token"], pickup_address="Patient Rx Pickup Address"
        )
        self.assertEqual(created_status, 201, created_body)
        created = json.loads(created_body)
        rid = created["id"]
        self.assertEqual(created["prescription_required"], True)
        self.assertEqual(created["pickup_address"], "Patient Rx Pickup Address")
        with self.Session() as session:
            self.assertEqual(session.get(Inventory, inventory_id).quantity_available, initial_quantity - 2)
        self.assertEqual(upload_request(f"/patient/requests/{rid}/prescription", "rx.pdf", b"%PDF-1.4 test", "application/pdf", donor["access_token"], field="file")[0], 403)
        self.assertEqual(upload_request(f"/patient/requests/{rid}/prescription", "rx.pdf", b"%PDF-1.4 test", "application/pdf", other_patient["access_token"], field="file")[0], 404)
        self.assertEqual(request("GET", f"/patient/requests/{rid}/prescription/file", token=other_patient["access_token"])[0], 404)
        upload = lambda token, data, filename="rx.pdf", mime="application/pdf": upload_request(f"/patient/requests/{rid}/prescription", filename, data, mime, token, field="file")
        pdf = b"%PDF-1.4\nvalid test fixture\n%%EOF"
        pharmacist_notices = json.loads(request("GET", "/notifications", token=pharmacist["access_token"])[1])["items"]
        self.assertIn("PRESCRIPTION_AWAITING_VERIFICATION", {notice["type"] for notice in pharmacist_notices})
        self.assertEqual(request("GET", f"/patient/requests/{rid}/prescription", token=patient["access_token"])[0], 200)
        self.assertEqual(request("GET", f"/patient/requests/{rid}/prescription/file", token=donor["access_token"])[0], 403)
        self.assertEqual(request("GET", f"/patient/requests/{rid}/prescription/file", token=patient["access_token"])[0], 200)
        self.assertEqual(request("GET", "/pharmacist/prescriptions/pending", token=donor["access_token"])[0], 403)
        self.assertEqual(request("GET", f"/pharmacist/requests/{rid}/prescription", token=other_pharmacist["access_token"])[0], 404)
        self.assertEqual(request("GET", f"/pharmacist/requests/{rid}/prescription/file", token=other_pharmacist["access_token"])[0], 404)
        self.assertEqual(request("POST", f"/pharmacist/requests/{rid}/prescription/approve", token=other_pharmacist["access_token"])[0], 404)
        self.assertEqual(len(json.loads(request("GET", "/pharmacist/prescriptions/pending", token=pharmacist["access_token"])[1])), 1)
        self.assertEqual(request("POST", f"/pharmacist/requests/{rid}/prescription/reject", {"reason": "  "}, pharmacist["access_token"])[0], 422)
        rejected = request("POST", f"/pharmacist/requests/{rid}/prescription/reject", {"reason": "Image is unreadable"}, pharmacist["access_token"])
        self.assertEqual(rejected[0], 200, rejected[1])
        self.assertEqual(json.loads(rejected[1])["rejection_reason"], "Image is unreadable")
        self.assertIn("PRESCRIPTION_REJECTED", {n["type"] for n in json.loads(request("GET", "/notifications", token=patient["access_token"])[1])["items"]})
        denied = request("POST", f"/pharmacist/requests/{rid}/approve", token=pharmacist["access_token"])
        self.assertEqual(denied[0], 409)
        with self.Session() as session:
            self.assertEqual(session.get(Inventory, inventory_id).quantity_available, initial_quantity - 2)
        self.assertEqual(upload(patient["access_token"], b"not a pdf", "bad.pdf")[0], 415)
        self.assertEqual(upload(patient["access_token"], b"%PDF-" + b"0" * (10 * 1024 * 1024 + 2))[0], 413)
        self.assertEqual(upload(patient["access_token"], pdf)[0], 201)
        approved_rx = request("POST", f"/pharmacist/requests/{rid}/prescription/approve", token=pharmacist["access_token"])
        self.assertEqual(approved_rx[0], 200, approved_rx[1])
        self.assertIn("PRESCRIPTION_APPROVED", {n["type"] for n in json.loads(request("GET", "/notifications", token=patient["access_token"])[1])["items"]})
        with self.Session() as session:
            decisions = session.query(Prescription).filter_by(request_id=rid).order_by(Prescription.created_at).all()
            self.assertEqual(len(decisions), 2)
            self.assertEqual(decisions[0].reviewed_by, UUID(pharmacist["user"]["id"]))
            self.assertIsNotNone(decisions[0].reviewed_at)
        reserved = request("POST", f"/pharmacist/requests/{rid}/approve", token=pharmacist["access_token"])
        self.assertEqual(reserved[0], 200, reserved[1])
        self.assertEqual(json.loads(reserved[1])["status"], "APPROVED")
        with self.Session() as session:
            self.assertEqual(session.get(Inventory, inventory_id).quantity_available, initial_quantity - 2)

        # Unclassified is prescription-required, but remains blocked until review.
        with self.Session() as session:
            item = session.get(Inventory, inventory_id)
            item.common_use_category = CommonUseCategory.UNCLASSIFIED
            item.prescription_required = True
            session.commit()
        pending_status, pending = self.create_patient_request_with_prescription(inventory_id, 1, other_patient["access_token"])
        self.assertEqual(pending_status, 201, pending)
        pending_id = json.loads(pending)["id"]
        blocked = request("POST", f"/pharmacist/requests/{pending_id}/approve", token=pharmacist["access_token"])
        self.assertEqual(blocked[0], 409)
        self.assertIn("approved prescription is required", json.loads(blocked[1])["detail"])
        self.assertEqual(request("PATCH", f"/inventory/{inventory_id}/common-use-category", {"common_use_category": "COLD"}, donor["access_token"])[0], 403)
        configured = request("PATCH", f"/inventory/{inventory_id}/common-use-category", {"common_use_category": "COLD"}, pharmacist["access_token"])
        self.assertEqual(configured[0], 200, configured[1])
        self.assertFalse(json.loads(configured[1])["prescription_required"])
        for category in ("COLD", "COUGH", "FLU", "FEVER", "PAIN", "ALLERGY", "OTHER", "UNCLASSIFIED"):
            response = request(
                "PATCH", f"/inventory/{inventory_id}/common-use-category",
                {"common_use_category": category}, pharmacist["access_token"],
            )
            self.assertEqual(response[0], 200, response[1])
            self.assertEqual(
                json.loads(response[1])["prescription_required"],
                category not in {"COLD", "COUGH", "FLU", "FEVER"},
                category,
            )

    def test_image_upload_authorization_and_validation(self):
        _, donor = self.signup("DONOR", "1")
        _, other = self.signup("DONOR", "2")
        _, patient = self.signup("PATIENT")
        _, pharmacist = self.signup("CLINIC_PHARMACIST")
        status_code, body = self.create_donation(donor["access_token"], details_confirmed=False)
        donation_id = json.loads(body)["id"]
        upload = lambda token, data, content_type="image/png": upload_request(f"/donations/{donation_id}/images", "package.png", data, content_type, token)
        self.assertEqual(upload(other["access_token"], b"\x89PNG\r\n\x1a\ninvalid")[0], 404)
        self.assertEqual(upload(patient["access_token"], b"\x89PNG\r\n\x1a\ninvalid")[0], 403)
        self.assertEqual(upload(pharmacist["access_token"], b"\x89PNG\r\n\x1a\ninvalid")[0], 403)
        self.assertEqual(upload(donor["access_token"], b"not an image")[0], 415)
        image_status, image_body = upload(donor["access_token"], b"\x89PNG\r\n\x1a\nsmall test image")
        self.assertEqual(image_status, 201, image_body)
        image = json.loads(image_body)[0]
        self.assertNotIn("storage_key", image)
        self.assertEqual(image_request(image["download_url"], donor["access_token"])[0], 200)
        self.assertEqual(image_request(image["download_url"], other["access_token"])[0], 404)


if __name__ == "__main__":
    unittest.main()
