from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
OPERATIONS_ROLES = frozenset({"OPERATOR", "ADMIN"})
MONEY_ROLES = frozenset({"OPERATOR"})
INVESTOR_VIEW_ROLES = frozenset({"OPERATOR", "INVESTOR"})


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


def require_operations_staff(user: User = Depends(get_current_user)) -> User:
    """Allow staff workflows while excluding the aggregate-only investor."""
    if user.role not in OPERATIONS_ROLES:
        raise HTTPException(status_code=403, detail="Bu bo'lim faqat xodimlar uchun.")
    return user


def require_money_access(user: User = Depends(get_current_user)) -> User:
    """Finance records are visible only to the operator by default."""
    if user.role not in MONEY_ROLES:
        raise HTTPException(status_code=403, detail="Moliyaviy ma'lumot faqat operator uchun.")
    return user


def require_investor_view(user: User = Depends(get_current_user)) -> User:
    """Expose aggregate financial totals to investors without operational data."""
    if user.role not in INVESTOR_VIEW_ROLES:
        raise HTTPException(status_code=403, detail="Bu moliyaviy ko'rinish uchun ruxsat yo'q.")
    return user


def require_payment_recording_permission(user: User = Depends(get_current_user)) -> User:
    """Optional exception for payment entry; response redaction still applies."""
    if user.role == "OPERATOR" or (user.role == "ADMIN" and settings.admins_can_record_payments):
        return user
    raise HTTPException(status_code=403, detail="To'lovni faqat operator qayd eta oladi.")


def require_billing_permission(user: User = Depends(get_current_user)) -> User:
    if user.role == "OPERATOR" or settings.admins_can_adjust_billing:
        return user
    raise HTTPException(status_code=403, detail="To‘lov davrini faqat operator o‘zgartira oladi.")
