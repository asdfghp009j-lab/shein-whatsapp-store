from __future__ import annotations

from datetime import datetime, timezone

from database import log_event


def submit_rating(db, order_id: int, customer_id: int, form: dict, environment: str = "DEMO"):
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        raise ValueError("الطلب غير موجود")
    if order["status"] != "delivered":
        raise ValueError("يمكن التقييم فقط بعد التسليم")
    if db.execute("SELECT id FROM ratings WHERE order_id = ?", (order_id,)).fetchone():
        raise ValueError("تم تقييم هذا الطلب مسبقًا")

    vals = {}
    for key in ("transaction_rating", "supervisor_rating", "speed_rating", "communication_rating", "overall_rating"):
        try:
            value = int(form.get(key, 5))
        except ValueError:
            raise ValueError("التقييم يجب أن يكون رقمًا من 1 إلى 5")
        if value < 1 or value > 5:
            raise ValueError("التقييم يجب أن يكون بين 1 و5")
        vals[key] = value

    eligible = 1 if environment == "LIVE" and order["environment"] == "LIVE" and order["supervisor_id"] else 0
    db.execute(
        """
        INSERT INTO ratings(
            order_id, customer_id, supervisor_id, transaction_rating, supervisor_rating,
            speed_rating, communication_rating, overall_rating, comment, eligible, environment, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            order_id,
            customer_id,
            order["supervisor_id"],
            vals["transaction_rating"],
            vals["supervisor_rating"],
            vals["speed_rating"],
            vals["communication_rating"],
            vals["overall_rating"],
            form.get("comment", ""),
            eligible,
            environment,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    log_event(db, customer_id, "submit_rating", "order", order_id, f"eligible={eligible}; supervisor_rating={vals['supervisor_rating']}")


def negative_ratings_count(db, supervisor_id: int, environment: str = "LIVE"):
    row = db.execute(
        "SELECT COUNT(*) AS count FROM ratings WHERE supervisor_id = ? AND environment = ? AND eligible = 1 AND supervisor_rating <= 2",
        (supervisor_id, environment),
    ).fetchone()
    return row["count"] if row else 0
