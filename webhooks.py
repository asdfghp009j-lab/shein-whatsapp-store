from __future__ import annotations

from datetime import datetime, timezone

from database import log_event


def create_audit(db, actor_user_id, action, entity_type, entity_id, details):
    db.execute("INSERT INTO audit_logs(actor_user_id, action, entity_type, entity_id, details, created_at) VALUES (?, ?, ?, ?, ?, ?)", (actor_user_id, action, entity_type, str(entity_id), details, datetime.now(timezone.utc).isoformat()))
    return True
