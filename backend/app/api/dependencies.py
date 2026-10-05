from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models import User, UserRole
from app.services.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        user_id = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc), headers={"WWW-Authenticate": "Bearer"}) from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is unavailable", headers={"WWW-Authenticate": "Bearer"})
    return user


def require_role(*roles: UserRole) -> Callable:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not authorized to access this resource")
        return user
    return dependency
