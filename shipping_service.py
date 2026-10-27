from __future__ import annotations

from datetime import datetime, timezone

from database import log_event


def submit_rating(db, order_id: int, customer_id: int, form: dict, environment: str = "DEMO"):
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        raise ValueError("الطلب غير موجود")
    if order["status"] != "delivered":
        raise ValueError("يجب أن يتم التسليم أولاً")
    if db.execute("SELECT id FROM ratings WHERE order_id = ?", (order_id,)).fetchone():
        raise ValueError("تم تقييم هذا الطلب مسبقًا")

    values = {}
    for key in ("transaction_rating", "supervisor_rating", "speed_rating", "communication_rating", "overall_rating"):
        try:
            val = int(form.get(key, 5))
        except ValueError:
            raise ValueError("التقييم يجب أن يكون رقمًا بين 1 و5")
        if val < 1 or val > 5:
            raise ValueError("التقييم يجب أن يكون بين 1 و5")
        values[key] = val

    eligible = 1 if environment == "LIVE" and order["environment"] == "LIVE" and order["supervisor_id"] else 0
    db.execute(
        "INSERT INTO ratings(order_id, customer_id, supervisor_id, transaction_rating, supervisor_rating, speed_rating, communication_rating, overall_rating, comment, eligible, environment, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (order_id, customer_id, order["supervisor_id"], values["transaction_rating"], values["supervisor_rating"], values["speed_rating"], values["communication_rating"], values["overall_rating"], form.get("comment", ""), eligible, environment, datetime.now(timezone.utc).isoformat()),
    )
    log_event(db, customer_id, "submit_rating", "order", order_id, f"eligible={eligible}; supervisor_rating={values['supervisor_rating']}")


def negative_ratings_count(db, supervisor_id: int, environment: str = "LIVE"):
    count = db.execute("SELECT COUNT(*) AS count FROM ratings WHERE supervisor_id = ? AND environment = ? AND eligible = 1 AND supervisor_rating <= 2", (supervisor_id, environment)).fetchone()["count"]
    return count
