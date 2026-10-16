from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import settings
from app.models import SystemSetting, User
from app.security import hash_password


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
        db.add(SystemSetting(key="general", value={"dorm_name": "DormFlow", "default_period_days": 30, "currency": "UZS"}, updated_by=operator.id))
    db.commit()
