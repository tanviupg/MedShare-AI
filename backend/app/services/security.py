from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

def hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must be no longer than 72 UTF-8 bytes")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError, UnicodeError):
        return False


def create_access_token(user_id: UUID) -> str:
    settings = get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured")
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiration_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expires}, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> UUID:
    settings = get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return UUID(payload["sub"])
    except (JWTError, KeyError, ValueError, TypeError) as exc:
        raise ValueError("Invalid or expired authentication token") from exc
