from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sessiya tugagan. Qayta kiring.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            raise unauthorized
        user_id = UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized from None
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise unauthorized
    return user


def require_operator(user: User = Depends(get_current_user)) -> User:
    if user.role != "OPERATOR":
        raise HTTPException(status_code=403, detail="Bu amal faqat operator uchun.")
    return user


def require_billing_permission(user: User = Depends(get_current_user)) -> User:
    if user.role == "OPERATOR" or settings.admins_can_adjust_billing:
        return user
    raise HTTPException(status_code=403, detail="To‘lov davrini faqat operator o‘zgartira oladi.")
