from __future__ import annotations

from django.contrib.auth.models import User

from .models import AuditLog


def record_audit(
    *,
    actor: User | None,
    action: str,
    summary: str,
    object_type: str = "",
    object_id: str | int | None = "",
) -> AuditLog:
    return AuditLog.objects.create(
        actor=actor if actor and getattr(actor, "is_authenticated", False) else None,
        action=action[:64],
        object_type=(object_type or "")[:64],
        object_id=str(object_id or "")[:64],
        summary=(summary or "")[:500],
    )
