from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_role
from app.db.database import get_db
from app.models import ClinicProfile, ClinicVerificationStatus, User, UserRole
from app.schemas.clinic_verification import (
    ClinicVerificationRejection,
    ClinicVerificationResult,
    PendingClinicVerification,
)

router = APIRouter(prefix="/admin/clinic-verifications", tags=["clinic verification"])


@router.get("/pending", response_model=list[PendingClinicVerification])
def list_pending_clinics(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> list[PendingClinicVerification]:
    profiles = db.scalars(
        select(ClinicProfile)
        .where(ClinicProfile.verification_status == ClinicVerificationStatus.PENDING)
        .order_by(ClinicProfile.created_at, ClinicProfile.id)
    ).all()
    return [PendingClinicVerification.model_validate(profile) for profile in profiles]


def decide_clinic(
    clinic_profile_id: UUID,
    status: ClinicVerificationStatus,
    admin: User,
    db: Session,
    rejection_reason: str | None = None,
) -> ClinicVerificationResult:
    profile = db.scalar(
        select(ClinicProfile)
        .where(ClinicProfile.id == clinic_profile_id)
        .with_for_update()
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Clinic profile not found")
    if profile.user_id == admin.id:
        raise HTTPException(status_code=403, detail="Administrators cannot review their own clinic profile")
    if profile.verification_status != ClinicVerificationStatus.PENDING:
        raise HTTPException(status_code=409, detail="Only pending clinic profiles can be reviewed")

    profile.verification_status = status
    profile.verification_reviewer_id = admin.id
    profile.verification_decided_at = datetime.now(timezone.utc)
    profile.verification_rejection_reason = rejection_reason
    db.commit()
    db.refresh(profile)
    return ClinicVerificationResult(
        verification_status=profile.verification_status,
        verification_decided_at=profile.verification_decided_at,
        verification_rejection_reason=profile.verification_rejection_reason,
    )


@router.post("/{clinic_profile_id}/approve", response_model=ClinicVerificationResult)
def approve_clinic(
    clinic_profile_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> ClinicVerificationResult:
    return decide_clinic(clinic_profile_id, ClinicVerificationStatus.VERIFIED, admin, db)


@router.post("/{clinic_profile_id}/reject", response_model=ClinicVerificationResult)
def reject_clinic(
    clinic_profile_id: UUID,
    body: ClinicVerificationRejection,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> ClinicVerificationResult:
    return decide_clinic(
        clinic_profile_id,
        ClinicVerificationStatus.REJECTED,
        admin,
        db,
        rejection_reason=body.reason,
    )
