"""Audit trail writer. Every login, KB edit, lead change, takeover, and
deletion goes through here. Never put message content, phone numbers, or
secrets in details — ids and field names only.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def record_audit(
    session: AsyncSession,
    *,
    user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Add an audit row to the current transaction (committed with it)."""
    session.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
        )
    )
