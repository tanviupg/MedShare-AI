from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import require_role
from app.db.database import get_db
from app.models import Donation, DonationImage, DonationReview, DonationStatus, Inventory, InventoryStatus, User, UserRole, MedicineExtraction, ExtractionStatus
from app.schemas.donation import DonationCreate, DonationImageResponse, DonationResponse, DonationReviewCreate, DonationReviewResponse, DonorDonationResponse
from app.services.donation_storage import LocalDonationStorage
from app.services.medicine_extraction import ExtractionConfigurationError, get_extraction_provider
from app.models import ClinicProfile, ClinicVerificationStatus
from datetime import date, datetime, timezone datetime, timezone
from app.models import CommonUseCategory, NotificationType, prescription_required_for
from app.services.notifications import notify, notify_verified_pharmacists

router = APIRouter(prefix="/donations", tags=["donations"])
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
IMAGE_EXTENSIONS = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}
IMAGE_CONTENT_TYPES = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
storage = LocalDonationStorage()


def detect_image_type(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    return None


def owned_donation(donation_id: UUID, user: User, db: Session) -> Donation:
    donation = db.scalar(select(Donation).options(selectinload(Donation.images)).where(Donation.id == donation_id, Donation.donor_id == user.id))
    if donation is None:
        raise HTTPException(status_code=404, detail="Donation not found")
    return donation


def donation_response(donation: Donation) -> DonationResponse:
    result = DonationResponse.model_validate(donation)
    for image in result.images:
        image.download_url = f"/donations/{donation.id}/images/{image.id}"
    return result


def pending_review_donation(donation_id: UUID, db: Session) -> Donation:
    donation = db.scalar(select(Donation).options(selectinload(Donation.images)).where(Donation.id == donation_id, Donation.status == DonationStatus.PENDING_REVIEW, Donation.details_confirmed.is_(True)))
    if donation is None:
        raise HTTPException(status_code=404, detail="Pending donation not found")
    return donation


def _extract_images(donation: Donation, images: list[DonationImage], db: Session) -> None:
    provider = get_extraction_provider()
    for image in images:
        record = MedicineExtraction(
            donation_id=donation.id,
            image_id=image.id,
            status=ExtractionStatus.PROCESSING,
            extracted_fields={},
            confidence={},
            provider_name=provider.name,
            provider_version=provider.version,
        )
        db.add(record)
        db.flush()
        try:
            content = storage.read(image.storage_key)
            if len(content) < 64 or detect_image_type(content) is None:
                raise RuntimeError("Invalid image")
            result = provider.extract(content, image.content_type)
            record.extracted_fields = result.fields
            record.confidence = {**result.confidence, "overall_confidence": result.overall_confidence}
            record.status = ExtractionStatus.COMPLETED
            record.provider_name = result.provider
            record.provider_version = result.version
        except Exception:
            record.status = ExtractionStatus.FAILED
            record.error_message = "OCR could not read this image. Please verify the package manually."
        record.completed_at = datetime.now(timezone.utc)
    db.commit()


@router.get("/review-queue", response_model=list[DonationResponse])
def get_review_queue(db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))) -> list[DonationResponse]:
    donations = db.scalars(select(Donation).options(selectinload(Donation.images)).where(Donation.status == DonationStatus.PENDING_REVIEW, Donation.details_confirmed.is_(True)).order_by(Donation.created_at.asc())).all()
    return [donation_response(item) for item in donations]


@router.get("/{donation_id}/review", response_model=DonationResponse)
def get_review_donation(donation_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))) -> DonationResponse:
    return donation_response(pending_review_donation(donation_id, db))


@router.post("/{donation_id}/extract")
def extract_donation_images(
    donation_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.CLINIC_PHARMACIST)),
) -> dict:
    donation = pending_review_donation(donation_id, db)
    if not donation.images:
        raise HTTPException(status_code=409, detail="Donation photos are required before running OCR")
    try:
        _extract_images(donation, donation.images, db)
    except ExtractionConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    rows = db.scalars(
        select(MedicineExtraction)
        .where(MedicineExtraction.donation_id == donation.id)
        .order_by(MedicineExtraction.created_at.desc())
    ).all()
    return {"items": [extraction_response(row) for row in rows]}


@router.post("/{donation_id}/review", response_model=DonationReviewResponse, status_code=status.HTTP_201_CREATED)
def review_donation(donation_id: UUID, payload: DonationReviewCreate, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))) -> DonationReviewResponse:
    donation = db.scalar(select(Donation).options(selectinload(Donation.images)).where(Donation.id == donation_id).with_for_update())
    if donation is None or donation.status != DonationStatus.PENDING_REVIEW:
        raise HTTPException(status_code=409, detail="Only donations awaiting review can be reviewed")
    if not donation.details_confirmed or not donation.images:
        raise HTTPException(status_code=409, detail="Donation photos must be submitted before review")
    verified = payload.verified_details
    if payload.decision.value == "APPROVED" and verified is None:
        raise HTTPException(status_code=422, detail="Verified medicine details are required for approval")
    reviewed_status = DonationStatus(payload.decision.value)
    changed = db.execute(update(Donation).where(Donation.id == donation_id, Donation.status == DonationStatus.PENDING_REVIEW).values(status=reviewed_status))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Only donations awaiting review can be reviewed")
    if verified is not None:
        for key, value in verified.model_dump(exclude={"common_use_category"}).items():
            setattr(donation, key, value)
    review = DonationReview(
        donation_id=donation_id,
        pharmacist_id=user.id,
        decision=payload.decision,
        reason=payload.reason,
        physical_package_checked=payload.physical_package_checked,
        verified_details=verified.model_dump(mode="json") if verified else None,
    )
    db.add(review)
    kind = NotificationType.DONATION_APPROVED if payload.decision.value == "APPROVED" else NotificationType.DONATION_REJECTED
    notify(db, donation.donor_id, kind, "Donation approved" if kind == NotificationType.DONATION_APPROVED else "Donation rejected",
           "Your medicine donation was approved." if kind == NotificationType.DONATION_APPROVED else "Your medicine donation was rejected.", "donation", donation.id)
    if payload.decision.value == "APPROVED":
        db.add(Inventory(
            donation_id=donation.id,
            pharmacist_id=user.id,
            medicine_name=donation.medicine_name,
            strength=donation.strength,
            dosage_form=donation.dosage_form,
            manufacturer=donation.manufacturer,
            batch_number=donation.batch_number,
            expiry_date=donation.expiry_date,
            quantity_available=donation.quantity,
            original_quantity=donation.quantity,
            unit=donation.unit,
            common_use_category=verified.common_use_category,
            prescription_required=prescription_required_for(verified.common_use_category),
            status=InventoryStatus.AVAILABLE,
        ))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This donation has already been reviewed") from exc
    db.refresh(review)
    return DonationReviewResponse.model_validate(review)


@router.post("", response_model=DonorDonationResponse, status_code=status.HTTP_201_CREATED)
def create_donation(payload: DonationCreate, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.DONOR))) -> DonorDonationResponse:
    donation = Donation(donor_id=user.id, pickup_address=payload.pickup_address, donor_expiry_date=payload.donor_expiry_date,
                        details_confirmed=False, status=DonationStatus.PENDING_REVIEW)
    db.add(donation)
    db.commit()
    db.refresh(donation)
    return DonorDonationResponse.model_validate(donation)


@router.get("/mine", response_model=list[DonorDonationResponse])
def get_my_donations(db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.DONOR))) -> list[DonorDonationResponse]:
    donations = db.scalars(select(Donation).where(Donation.donor_id == user.id).order_by(Donation.created_at.desc())).all()
    return [DonorDonationResponse.model_validate(item) for item in donations]


@router.get("/{donation_id}", response_model=DonorDonationResponse)
def get_my_donation(donation_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.DONOR))) -> DonorDonationResponse:
    return DonorDonationResponse.model_validate(owned_donation(donation_id, user, db))


def extraction_response(row: MedicineExtraction) -> dict:
    return {"id": str(row.id), "image_id": str(row.image_id), "status": row.status.value,
            "fields": {key: value for key, value in row.extracted_fields.items() if key != "raw_ocr_text"},
            "raw_ocr_text": row.extracted_fields.get("raw_ocr_text"), "confidence": row.confidence,
            "overall_confidence": row.confidence.get("overall_confidence", 0),
            "provider": row.provider_name,
            "is_mock": row.provider_name == "mock", "error_message": row.error_message,
            "created_at": row.created_at.isoformat() if row.created_at else None}


@router.get("/{donation_id}/extraction")
def get_extraction(donation_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))) -> dict:
    donation = db.scalar(select(Donation).where(Donation.id == donation_id))
    if donation is None or (
        donation.status != DonationStatus.PENDING_REVIEW
        and db.scalar(select(DonationReview.id).where(
            DonationReview.donation_id == donation_id, DonationReview.pharmacist_id == user.id
        )) is None
    ):
        raise HTTPException(status_code=404, detail="Donation extraction not found")
    rows = db.scalars(select(MedicineExtraction).where(MedicineExtraction.donation_id == donation_id).order_by(MedicineExtraction.created_at.desc())).all()
    return {"items": [extraction_response(row) for row in rows]}


@router.post("/{donation_id}/images", response_model=list[DonationImageResponse], status_code=status.HTTP_201_CREATED)
async def add_donation_images(donation_id: UUID, files: list[UploadFile] = File(...), db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.DONOR))) -> list[DonationImageResponse]:
    donation = owned_donation(donation_id, user, db)
    if donation.details_confirmed:
        raise HTTPException(status_code=409, detail="Photos cannot be changed after donation submission")
    if not files or len(files) > 8 or len(donation.images) + len(files) > 8:
        raise HTTPException(status_code=400, detail="A donation can have at most 8 images")
    saved: list[tuple[str, DonationImage]] = []
    try:
        for upload in files:
            content = await upload.read(MAX_IMAGE_BYTES + 1)
            if len(content) > MAX_IMAGE_BYTES:
                raise HTTPException(status_code=413, detail="Each image must be 5 MB or smaller")
            kind = detect_image_type(content)
            content_type = upload.content_type or ""
            if kind not in IMAGE_EXTENSIONS or content_type not in ALLOWED_IMAGE_TYPES or content_type != IMAGE_CONTENT_TYPES.get(kind):
                raise HTTPException(status_code=415, detail="Only JPEG, PNG, and WebP images are accepted")
            key = storage.save(content, IMAGE_EXTENSIONS[kind])
            original = Path(upload.filename or "image").name[:255]
            record = DonationImage(donation_id=donation.id, storage_key=key, original_filename=original, content_type=content_type, size_bytes=len(content))
            db.add(record)
            saved.append((key, record))
        donation.details_confirmed = True
        notify_verified_pharmacists(
            db,
            NotificationType.DONATION_AWAITING_REVIEW,
            "New donation awaiting review",
            "A donor submitted medicine photos and pickup information for clinic review.",
            "donation",
            donation.id,
        )
        db.commit()
    except Exception:
        db.rollback()
        for key, _ in saved:
            storage.delete(key)
        raise
    for _, record in saved:
        db.refresh(record)
    return [DonationImageResponse.model_validate(record).model_copy(update={"download_url": f"/donations/{donation.id}/images/{record.id}"}) for _, record in saved]


@router.get("/{donation_id}/images/{image_id}")
def get_donation_image(donation_id: UUID, image_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.DONOR, UserRole.CLINIC_PHARMACIST))) -> Response:
    if user.role == UserRole.DONOR:
        donation = owned_donation(donation_id, user, db)
    else:
        donation = db.scalar(
            select(Donation).options(selectinload(Donation.images)).where(
                Donation.id == donation_id,
                Donation.status == DonationStatus.PENDING_REVIEW,
                Donation.details_confirmed.is_(True),
            )
        )
        if donation is None and db.scalar(select(DonationReview.id).where(
            DonationReview.donation_id == donation_id, DonationReview.pharmacist_id == user.id
        )) is not None:
            donation = db.scalar(select(Donation).options(selectinload(Donation.images)).where(Donation.id == donation_id))
        if donation is None:
            raise HTTPException(status_code=404, detail="Donation not found")
    image = next((item for item in donation.images if item.id == image_id), None)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        content = storage.read(image.storage_key)
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Image file not found") from exc
    return Response(content=content, media_type=image.content_type, headers={"X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"})
