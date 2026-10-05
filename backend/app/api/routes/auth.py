from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import get_current_user, require_role
from app.db.database import get_db
from app.models import ClinicProfile, ClinicVerificationStatus, User, UserRole
from app.schemas.auth import AuthResponse, LoginRequest, SignupRequest, UserResponse
from app.services.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["authentication"])


def auth_result(user: User) -> AuthResponse:
    return AuthResponse(access_token=create_access_token(user.id), user=UserResponse.model_validate(user))


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> AuthResponse:
    email = str(payload.email).lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")
    user = User(name=payload.name.strip(), email=email, password_hash=hash_password(payload.password), role=UserRole(payload.role.value), phone=payload.phone, city=payload.city)
    if payload.clinic_profile:
        profile = payload.clinic_profile
        user.clinic_profile = ClinicProfile(clinic_name=profile.clinic_name.strip(), address=profile.address.strip(), city=profile.city.strip(), license_number=profile.license_number, contact_number=profile.contact_number, verification_status=ClinicVerificationStatus.PENDING)
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists") from exc
    db.refresh(user)
    return auth_result(user)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.scalar(select(User).options(joinedload(User.clinic_profile)).where(User.email == str(payload.email).lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password", headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is inactive")
    return auth_result(user)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)


@router.get("/test/donor", tags=["temporary role verification"])
def test_donor(user: User = Depends(require_role(UserRole.DONOR))) -> dict[str, str]:
    return {"message": "Donor access granted", "role": user.role.value}


@router.get("/test/patient", tags=["temporary role verification"])
def test_patient(user: User = Depends(require_role(UserRole.PATIENT))) -> dict[str, str]:
    return {"message": "Patient access granted", "role": user.role.value}


@router.get("/test/clinic", tags=["temporary role verification"])
def test_clinic(user: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))) -> dict[str, str]:
    return {"message": "Clinic/Pharmacist access granted", "role": user.role.value}
