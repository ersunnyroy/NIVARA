from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.logging import redact
from app.core.timeutil import utcnow
from app.models import AuditLog


def audit(db: Session, action: str, user_id: int | None = None, entity: str | None = None,
          entity_id: str | int | None = None, data: dict | None = None, ip: str | None = None) -> None:
    db.add(AuditLog(user_id=user_id, action=action, entity=entity, entity_id=None if entity_id is None else str(entity_id),
                    data=redact(data or {}), ip=ip, created_at=utcnow()))
