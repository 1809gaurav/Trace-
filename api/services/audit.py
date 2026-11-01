"""Append audit events for case activity."""

from contextvars import ContextVar
from typing import Any

from sqlalchemy.orm import Session

from api.db.models import AuditLog

current_actor: ContextVar[str] = ContextVar("trace_actor", default="local-demo")


def record_audit(
    session: Session,
    action: str,
    case_id: str | None,
    details: dict[str, Any],
    actor: str | None = None,
) -> AuditLog:
    """Add an audit row to the caller's transaction."""
    row = AuditLog(case_id=case_id, actor=actor or current_actor.get(), action=action, details=details)
    session.add(row)
    return row
