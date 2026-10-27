from __future__ import annotations

from datetime import datetime, timezone

from database import log_event
from models import generate_payment_ref


def create_payment_record(db, order_id: int, method: str, amount: float, currency: str, note: str = "", actor_id: int | None = None, is_demo: bool = False):
    if amount <= 0:
        raise ValueError("قيمة الدفع يجب أن تكون أكبر من صفر")
    ref = generate_payment_ref()
    while db.execute("SELECT 1 FROM payments WHERE payment_ref = ?", (ref,)).fetchone():
        ref = generate_payment_ref()
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO payments(order_id, payment_ref, method, amount, currency, status, is_demo, note, reviewed_by, created_at, reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (order_id, ref, method, amount, currency, "pending_review", 1 if is_demo else 0, note, actor_id, now, None),
    )
    payment_id = db.execute("SELECT id FROM payments WHERE payment_ref = ?", (ref,)).fetchone()["id"]
    log_event(db, actor_id, "create_payment", "payment", payment_id, f"{method}; {amount} {currency}")
    return ref


def review_payment(db, order_id: int, payment_id: int, accepted: bool, reviewer_id: int, note: str = ""):
    payment = db.execute("SELECT * FROM payments WHERE id = ? AND order_id = ?", (payment_id, order_id)).fetchone()
    if not payment:
        raise ValueError("الدفعة غير موجودة")
    if payment["status"] != "pending_review":
        raise ValueError("تمت مراجعة هذه الدفعة من قبل")
    status = "confirmed" if accepted else "rejected"
    now = datetime.now(timezone.utc).isoformat()
    db.execute("UPDATE payments SET status = ?, reviewed_by = ?, reviewed_at = ?, note = ? WHERE id = ?", (status, reviewer_id, now, note, payment_id))

    total_paid = db.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE order_id = ? AND status = 'confirmed'", (order_id,)).fetchone()["total"]
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    payment_status = "paid" if total_paid >= order["total_amount"] else ("partial" if total_paid > 0 else "unpaid")
    db.execute("UPDATE orders SET payment_status = ?, updated_at = ? WHERE id = ?", (payment_status, now, order_id))
    log_event(db, reviewer_id, "review_payment", "payment", payment_id, f"accepted={accepted}; {note}")
    return status


def record_cash_payment(db, order_id: int, amount: float, currency: str, actor_id: int, note: str = ""):
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        raise ValueError("الطلب غير موجود")
    if amount <= 0:
        raise ValueError("المبلغ المستلم يجب أن يكون أكبر من صفر")
    ref = generate_payment_ref()
    while db.execute("SELECT 1 FROM payments WHERE payment_ref = ?", (ref,)).fetchone():
        ref = generate_payment_ref()
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO payments(order_id, payment_ref, method, amount, currency, status, is_demo, note, reviewed_by, created_at, reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (order_id, ref, "cash", amount, currency, "confirmed", 1 if order["environment"] == "DEMO" else 0, note, actor_id, now, now),
    )
    total_paid = db.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE order_id = ? AND status = 'confirmed'", (order_id,)).fetchone()["total"]
    payment_status = "paid" if total_paid >= order["total_amount"] else ("partial" if total_paid > 0 else "unpaid")
    db.execute("UPDATE orders SET payment_status = ?, updated_at = ? WHERE id = ?", (payment_status, now, order_id))
    log_event(db, actor_id, "cash_payment", "order", order_id, f"استلام نقدي: {ref}; {amount} {currency}")
    return ref
