from __future__ import annotations

from datetime import datetime, timezone

from database import log_event


def update_shipping_status(db, order_id: int, status: str, updated_by: int, note: str = ""):
    allowed = {"received", "awaiting_payment", "approved", "payment_confirmed", "packing", "shipped", "out_for_delivery", "delivered", "cancelled", "rejected", "on_hold"}
    if status not in allowed:
        raise ValueError("حالة الشحن غير صالحة")

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, order_id),
    )
    db.execute(
        "INSERT INTO shipping_updates(order_id, status, note, updated_by, created_at) VALUES (?, ?, ?, ?, ?)",
        (order_id, status, note, updated_by, now),
    )
    log_event(db, updated_by, "shipping_status_update", "order", order_id, f"status={status}; {note}")
    return status
