import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.dispensing import (
    dispense_request,
    list_patient_dispensing,
    list_ready_for_pickup,
    get_patient_dispensing,
)
from app.api.routes.checkout import get_checkout
from app.api.routes.patient import available_inventory_query, search_medicines
from app.api.routes.requests import _new_request, _review
from app.api.routes.waste import move_inventory_to_waste
from app.db.base import Base
from app.models import (
    ClinicProfile,
    ClinicVerificationStatus,
    CommonUseCategory,
    Donation,
    DonationStatus,
    Inventory,
    InventoryStatus,
    MedicineRequest,
    MedicineRequestStatus,
    Notification,
    NotificationType,
    User,
    UserRole,
    WasteReason,
    WasteRecord,
)
from app.schemas.donation import DonationResponse
from app.schemas.medicine_request import MedicineRequestCreate
from app.schemas.waste import WasteCreate
from app.services.business_time import business_today
from app.services.expiry import (
    expiry_is_eligible,
    expiry_warning_days,
    synchronize_expired_reservations,
)


class ExpiryPolicyTests(unittest.TestCase):
    def test_minimum_shelf_life_boundary_and_warning_window_are_separate(self):
        settings = SimpleNamespace(
            minimum_remaining_shelf_life_days=30,
            expiry_warning_days=90,
        )
        with patch("app.services.expiry.get_settings", return_value=settings):
            today = date(2030, 1, 1)
            self.assertTrue(expiry_is_eligible(today + timedelta(days=30), today))
            self.assertFalse(expiry_is_eligible(today + timedelta(days=29), today))
            self.assertEqual(expiry_warning_days(), 90)

    def test_business_date_uses_asia_kolkata_calendar_day(self):
        utc_instant = datetime(2030, 1, 1, 20, 0, tzinfo=timezone.utc)

        class FixedDateTime:
            @staticmethod
            def now(tz=None):
                return utc_instant.astimezone(tz)

        with patch("app.services.business_time.datetime", FixedDateTime):
            self.assertEqual(business_today(), date(2030, 1, 2))


class ExpiryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, class_=Session, expire_on_commit=False)
        self.db = self.Session()
        self.today = business_today()
        self.patient, self.pharmacist, self.inventory, self.request = self.create_records(
            self.today - timedelta(days=1),
            request_status=MedicineRequestStatus.APPROVED,
            reserved=True,
        )

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def create_records(
        self,
        expiry_date: date,
        request_status: MedicineRequestStatus | None = None,
        reserved: bool = False,
    ):
        donor = User(
            id=uuid4(), name="Donor", email=f"{uuid4()}@example.test",
            password_hash="test-hash", role=UserRole.DONOR,
        )
        patient = User(
            id=uuid4(), name="Patient", email=f"{uuid4()}@example.test",
            password_hash="test-hash", role=UserRole.PATIENT,
        )
        pharmacist = User(
            id=uuid4(), name="Pharmacist", email=f"{uuid4()}@example.test",
            password_hash="test-hash", role=UserRole.CLINIC_PHARMACIST,
        )
        donation = Donation(
            id=uuid4(), donor_id=donor.id, medicine_name="Test medicine",
            expiry_date=expiry_date, quantity=5, unit="tablets",
            status=DonationStatus.APPROVED,
        )
        profile = ClinicProfile(
            id=uuid4(), user_id=pharmacist.id, clinic_name="Test clinic",
            address="1 Test Road", city="Pune",
            verification_status=ClinicVerificationStatus.VERIFIED,
        )
        inventory = Inventory(
            id=uuid4(), donation_id=donation.id, pharmacist_id=pharmacist.id,
            medicine_name="Test medicine", common_use_category=CommonUseCategory.OTHER,
            prescription_required=True, public_id=uuid4(), expiry_date=expiry_date,
            quantity_available=2 if reserved else 5, original_quantity=5,
            unit="tablets",
            status=InventoryStatus.RESERVED if reserved else InventoryStatus.AVAILABLE,
        )
        request = None
        self.db.add_all([donor, patient, pharmacist, donation, profile, inventory])
        self.db.flush()
        if request_status is not None:
            request = MedicineRequest(
                id=uuid4(), patient_id=patient.id, inventory_id=inventory.id,
                requested_quantity=3 if reserved else 1,
                pickup_address="1 Patient Road", inventory_reserved=reserved,
                status=request_status, pickup_code="MS-123456" if reserved else None,
            )
            self.db.add(request)
            self.db.flush()
        self.db.commit()
        return patient, pharmacist, inventory, request

    def settings(self):
        return SimpleNamespace(
            minimum_remaining_shelf_life_days=30,
            expiry_warning_days=90,
        )

    def test_donation_review_response_carries_business_date_and_expiry_policy(self):
        donation = self.db.get(Donation, self.inventory.donation_id)
        with patch("app.schemas.donation.business_today", return_value=self.today), \
                patch("app.schemas.donation.get_settings", return_value=self.settings()):
            response = DonationResponse.model_validate(donation)
        self.assertEqual(response.business_date, self.today)
        self.assertEqual(response.expiry_warning_days, 90)
        self.assertEqual(response.minimum_remaining_shelf_life_days, 30)
        payload = response.model_dump(mode="json")
        self.assertEqual(payload["business_date"], self.today.isoformat())
        self.assertEqual(payload["expiry_warning_days"], 90)
        self.assertEqual(payload["minimum_remaining_shelf_life_days"], 30)

    def test_expired_reservation_is_released_once_and_waste_retry_is_blocked(self):
        self.db.add(Notification(
            recipient_user_id=self.patient.id,
            type=NotificationType.READY_FOR_PICKUP,
            title="Medicine ready for pickup",
            message="Your approved medicine request is ready for dispensing.",
            related_entity_type="medicine_request",
            related_entity_id=self.request.id,
        ))
        self.db.commit()

        def persist_notice(db, recipient_id, kind, title, message, entity_type, entity_id):
            db.add(Notification(
                recipient_user_id=recipient_id,
                type=kind,
                title=title,
                message=message,
                related_entity_type=entity_type,
                related_entity_id=entity_id,
            ))

        with (
            patch("app.services.expiry.get_settings", return_value=self.settings()),
            patch("app.services.expiry.notify", side_effect=persist_notice) as reservation_notification,
        ):
            changed = synchronize_expired_reservations(self.db, today=self.today)
            self.assertEqual(changed, 1)
            self.db.refresh(self.inventory)
            self.db.refresh(self.request)
            self.assertEqual(self.request.status, MedicineRequestStatus.REJECTED)
            self.assertFalse(self.request.inventory_reserved)
            self.assertIsNone(self.request.pickup_code)
            self.assertEqual(self.inventory.quantity_available, 5)
            self.assertEqual(self.inventory.status, InventoryStatus.EXPIRED)
            self.assertEqual(
                self.db.scalar(select(func.count()).select_from(Notification).where(
                    Notification.type == NotificationType.READY_FOR_PICKUP,
                    Notification.related_entity_id == self.request.id,
                )),
                0,
            )
            self.assertEqual(
                self.db.scalar(select(func.count()).select_from(Notification).where(
                    Notification.type == NotificationType.REQUEST_REJECTED,
                    Notification.related_entity_id == self.request.id,
                )),
                1,
            )

            self.assertEqual(synchronize_expired_reservations(self.db, today=self.today), 0)
            self.assertEqual(reservation_notification.call_count, 1)

        body = WasteCreate(reason=WasteReason.EXPIRED, quantity=2, notes="Expired stock")
        with patch("app.services.expiry.get_settings", return_value=self.settings()), \
                patch("app.api.routes.waste.notify") as waste_notification:
            move_inventory_to_waste(
                inventory_id=self.inventory.id,
                body=body,
                db=self.db,
                pharmacist=self.pharmacist,
            )
            with self.assertRaises(HTTPException) as raised:
                move_inventory_to_waste(
                    inventory_id=self.inventory.id,
                    body=body,
                    db=self.db,
                    pharmacist=self.pharmacist,
                )
            self.assertEqual(raised.exception.status_code, 409)
            self.assertEqual(
                self.db.scalar(select(func.count()).select_from(WasteRecord)),
                1,
            )
            self.assertEqual(waste_notification.call_count, 1)

    def test_near_expiry_reservation_is_released_but_remains_unrequestable(self):
        self.inventory.expiry_date = self.today + timedelta(days=29)
        self.db.commit()
        with patch("app.services.expiry.get_settings", return_value=self.settings()), \
                patch("app.services.expiry.notify"):
            self.assertEqual(synchronize_expired_reservations(self.db, today=self.today), 1)

        self.db.refresh(self.inventory)
        self.db.refresh(self.request)
        self.assertEqual(self.request.status, MedicineRequestStatus.REJECTED)
        self.assertFalse(self.request.inventory_reserved)
        self.assertEqual(self.inventory.quantity_available, 5)
        self.assertEqual(self.inventory.status, InventoryStatus.AVAILABLE)
        self.assertEqual(self.db.execute(available_inventory_query()).all(), [])

    def test_expired_stock_is_blocked_from_search_request_checkout_and_dispensing(self):
        with patch("app.services.expiry.get_settings", return_value=self.settings()), \
                patch("app.services.expiry.notify"), \
                patch("app.api.routes.dispensing.notify"):
            self.assertEqual(self.db.execute(available_inventory_query()).all(), [])

            request_body = MedicineRequestCreate(
                medicine_id=self.inventory.public_id,
                requested_quantity=1,
                pickup_address="1 Patient Road",
            )
            with self.assertRaises(HTTPException) as request_error:
                _new_request(request_body, self.db, self.patient)
            self.assertEqual(request_error.exception.status_code, 409)

            with self.assertRaises(HTTPException) as checkout_error:
                get_checkout(
                    request_id=self.request.id,
                    db=self.db,
                    patient=self.patient,
                )
            self.assertEqual(checkout_error.exception.status_code, 409)

            ready = list_ready_for_pickup(db=self.db, pharmacist=self.pharmacist)
            self.assertEqual(ready, [])
            self.assertEqual(
                list_patient_dispensing(db=self.db, patient=self.patient),
                [],
            )
            with self.assertRaises(HTTPException) as detail_error:
                get_patient_dispensing(
                    request_id=self.request.id,
                    db=self.db,
                    patient=self.patient,
                )
            self.assertEqual(detail_error.exception.status_code, 404)

            self.db.refresh(self.request)
            self.assertEqual(self.request.status, MedicineRequestStatus.REJECTED)
            with self.assertRaises(HTTPException) as dispense_error:
                dispense_request(
                    request_id=self.request.id,
                    db=self.db,
                    pharmacist=self.pharmacist,
                )
            self.assertEqual(dispense_error.exception.status_code, 409)

    def test_normal_eligible_reservation_approval_and_dispensing_still_work(self):
        self.inventory.expiry_date = self.today + timedelta(days=60)
        self.inventory.status = InventoryStatus.AVAILABLE
        self.inventory.quantity_available = 5
        self.inventory.common_use_category = CommonUseCategory.COLD
        self.inventory.prescription_required = False
        self.request.status = MedicineRequestStatus.PENDING
        self.request.requested_quantity = 2
        self.request.inventory_reserved = False
        self.request.pickup_code = None
        self.db.commit()

        with patch("app.services.expiry.get_settings", return_value=self.settings()), \
                patch("app.api.routes.requests.notify"), \
                patch("app.api.routes.dispensing.notify"):
            result = _review(
                self.request.id,
                self.db,
                self.pharmacist,
                MedicineRequestStatus.APPROVED,
                None,
            )
            self.db.refresh(self.inventory)
            self.db.refresh(self.request)
            self.assertEqual(result["status"], MedicineRequestStatus.APPROVED)
            self.assertTrue(self.request.inventory_reserved)
            self.assertIsNotNone(self.request.pickup_code)
            self.assertEqual(self.inventory.quantity_available, 3)

            dispensed = dispense_request(
                request_id=self.request.id,
                db=self.db,
                pharmacist=self.pharmacist,
            )
        self.assertEqual(dispensed["status"], MedicineRequestStatus.FULFILLED)
        self.assertEqual(self.inventory.quantity_available, 3)

    def test_patient_search_returns_server_computed_expiry_warning(self):
        self.inventory.expiry_date = self.today + timedelta(days=60)
        self.inventory.quantity_available = 5
        self.inventory.status = InventoryStatus.AVAILABLE
        self.request.status = MedicineRequestStatus.REJECTED
        self.request.inventory_reserved = False
        self.request.pickup_code = None
        self.db.commit()
        with (
            patch("app.services.expiry.get_settings", return_value=self.settings()),
            patch("app.api.routes.patient.get_settings", return_value=self.settings()),
            patch("app.api.routes.patient.business_today", return_value=self.today) as today_provider,
        ):
            result = search_medicines(
                q=None,
                strength=None,
                dosage_form=None,
                category=None,
                city=None,
                clinic=None,
                page=1,
                page_size=12,
                db=self.db,
                _user=self.patient,
            )
        self.assertEqual(today_provider.call_count, 1)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0].days_remaining, 60)
        self.assertEqual(result.items[0].expiry_warning_days, 90)
        self.assertEqual(result.items[0].minimum_remaining_shelf_life_days, 30)


if __name__ == "__main__":
    unittest.main()
