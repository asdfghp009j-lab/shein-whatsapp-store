from __future__ import annotations

from datetime import datetime, timezone

from database import log_event


def create_notification(db, user_id: int | None, title: str, message: str, channel: str = "internal", entity_type: str | None = None, entity_id: str | None = None):
    db.execute(
        "INSERT INTO notifications(user_id, title, message, channel, entity_type, entity_id, is_read, created_at) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
        (user_id, title, message, channel, entity_type, entity_id, datetime.now(timezone.utc).isoformat()),
    )
    log_event(db, user_id, "notification_created", entity_type or "system", entity_id or "system", title)
    return True
