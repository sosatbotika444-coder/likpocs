from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditEvent, Notification, User


def audit(
    
    db: Session,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
    )
    db.add(event)
    return event


def notify(db: Session, title: str, message: str, kind: str = "INFO", entity_id: UUID | None = None) -> Notification:
    item = Notification(title=title, message=message, kind=kind, entity_id=entity_id)
    db.add(item)
    return item


