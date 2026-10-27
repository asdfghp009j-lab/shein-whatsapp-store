from __future__ import annotations

from datetime import datetime, timezone
import random
import string


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def generate_customer_code():
    return f"CUST-{random.randint(20000, 99999)}"


def generate_order_code():
    return f"ORD-{random.randint(1000, 999999)}"


def generate_payment_ref():
    return f"PAY-{random.randint(100000, 999999)}"


def generate_supervisor_code(index: int):
    return f"SUP-{1000 + index}"


def generate_token(length: int = 20):
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))
