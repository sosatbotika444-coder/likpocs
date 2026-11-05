from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import settings
from app.models import Dormitory, SystemSetting, User
from app.security import hash_password


def _ensure_role_account(db: Session, operator: User, *, email: str, password: str, name: str, role: str) -> None:
    """Create an optional ADMIN/INVESTOR account once; never overwrite an existing user's password."""
    email = email.strip().lower()
    if not email and not password:
        return
    if not email or not password:
        raise RuntimeError(f"{role} hisobi uchun email va parol birga kiritilishi shart.")
    try:
        TypeAdapter(EmailStr).validate_python(email)
    except ValidationError:
        raise RuntimeError(f"{role} email manzili noto‘g‘ri.") from None
    if len(password) < 12:
        raise RuntimeError(f"{role} paroli kamida 12 belgidan iborat bo‘lishi shart.")
    if db.scalar(select(User).where(User.email == email)):
        return
    user = User(email=email, full_name=name.strip() or role.title(), password_hash=hash_password(password), role=role, is_active=True, is_primary=False)
    db.add(user)
    db.flush()
    audit(db, operator, "USER_BOOTSTRAPPED", "User", user.id, {"role": role})


def bootstrap(db: Session) -> None:
    operator = db.scalar(select(User).where(User.role == "OPERATOR", User.is_primary.is_(True)))
    if not operator:
        if not settings.initial_operator_password:
            raise RuntimeError("INITIAL_OPERATOR_PASSWORD sozlamasi kiritilishi shart.")
        operator = User(
            email=str(settings.initial_operator_email).lower(),
            full_name=settings.initial_operator_name,
            password_hash=hash_password(settings.initial_operator_password),
            role="OPERATOR",
            is_active=True,
            is_primary=True,
        )
        db.add(operator)
        db.flush()
        audit(db, operator, "OPERATOR_BOOTSTRAPPED", "User", operator.id)
    if not db.get(SystemSetting, "general"):
        db.add(SystemSetting(key="general", value={"dorm_name": "RS Best Hostel", "default_period_days": 30, "currency": "UZS"}, updated_by=operator.id))
    if not db.scalar(select(Dormitory).where(Dormitory.is_default.is_(True))):
        general = db.get(SystemSetting, "general")
        dormitory_name = (general.value.get("dorm_name") if general else None) or "RS Best Hostel"
        db.add(Dormitory(name=dormitory_name, is_default=True, is_active=True))
    _ensure_role_account(db, operator, email=settings.initial_admin_email, password=settings.initial_admin_password, name=settings.initial_admin_name, role="ADMIN")
    _ensure_role_account(db, operator, email=settings.initial_investor_email, password=settings.initial_investor_password, name=settings.initial_investor_name, role="INVESTOR")
    db.commit()
