from __future__ import annotations

from datetime import datetime, timezone

from database import get_db, log_event
from models import generate_order_code


def create_order_record(db, customer_id: int, payload: dict, environment: str = "DEMO") -> str:
    now = datetime.now(timezone.utc).isoformat()

    order_code = generate_order_code()
    while db.execute("SELECT 1 FROM orders WHERE order_code = ?", (order_code,)).fetchone():
        order_code = generate_order_code()

    product_name = (payload.get("product_name") or "منتج بدون اسم").strip()
    product_url = (payload.get("product_url") or "").strip()
    quantity = max(1, int(payload.get("quantity", 1)))
    unit_price = float(payload.get("unit_price", 0.0) or 0.0)
    country = (payload.get("country") or "اليمن").strip()
    options = payload.get("options") or ""
    total_amount = round(unit_price * quantity, 2)

    cursor = db.execute(
        """
        INSERT INTO orders(
            order_code, customer_id, supervisor_id, product_name, product_url, quantity,
            unit_price, total_amount, currency, country, options, environment,
            status, payment_status, is_demo, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            order_code,
            customer_id,
            payload.get("supervisor_id"),
            product_name,
            product_url,
            quantity,
            unit_price,
            total_amount,
            payload.get("currency", "YER"),
            country,
            options,
            environment,
            "received",
            "unpaid",
            1 if environment == "DEMO" else 0,
            now,
            now,
        ),
    )

    order_id = cursor.lastrowid
    db.execute(
        "INSERT INTO order_items(order_id, product_name, quantity, unit_price, total_price, color, size, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            order_id,
            product_name,
            quantity,
            unit_price,
            total_amount,
            payload.get("color"),
            payload.get("size"),
            payload.get("note"),
            now,
        ),
    )

    log_event(db, customer_id, "create_order", "order", order_id, f"إنشاء الطلب {order_code}")
    return order_code


def get_order_by_code(db, order_code: str):
    return db.execute(
        "SELECT o.*, c.display_name AS customer_name FROM orders o JOIN users c ON c.id = o.customer_id WHERE o.order_code = ?",
        (order_code,),
    ).fetchone()
