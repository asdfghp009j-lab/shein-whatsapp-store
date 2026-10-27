from __future__ import annotations

from datetime import datetime, timezone
import random
import string

ROLES = ("customer", "supervisor", "admin", "system")
COUNTRIES = [
    "اليمن", "السودان", "ليبيا", "لبنان", "موريتانيا", "العراق", "سوريا", "جيبوتي", "الصومال"
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def generate_customer_code() -> str:
    return f"CUST-{random.randint(10000, 99999)}"


def generate_order_code() -> str:
    return f"ORD-{random.randint(1000, 999999)}"


def generate_payment_ref() -> str:
    return f"PAY-{random.randint(100000, 999999)}"


def generate_supervisor_code(index: int) -> str:
    return f"SUP-{1000 + index}"


def generate_random_token(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))
