import os
import sqlite3
from datetime import datetime, timezone
from flask import g
from werkzeug.security import generate_password_hash

DB_PATH = os.getenv("DATABASE_PATH", "store.db")

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('customer','supervisor','admin','system')),
    supervisor_code TEXT UNIQUE,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
    customer_code TEXT UNIQUE NOT NULL,
    full_name TEXT,
    country TEXT,
    whatsapp_number TEXT,
    address TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS supervisors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
    supervisor_code TEXT UNIQUE NOT NULL,
    assigned_orders INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier TEXT,
    source_url TEXT,
    product_name TEXT NOT NULL,
    product_image TEXT,
    product_price REAL,
    currency TEXT DEFAULT 'SAR',
    product_details TEXT,
    sizes TEXT,
    colors TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_code TEXT UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES users(id),
    supervisor_id INTEGER REFERENCES users(id),
    product_name TEXT NOT NULL,
    product_url TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price REAL NOT NULL,
    total_amount REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'SAR',
    country TEXT NOT NULL,
    options TEXT,
    environment TEXT NOT NULL CHECK(environment IN ('DEMO','LIVE')),
    status TEXT NOT NULL DEFAULT 'received',
    payment_status TEXT NOT NULL DEFAULT 'unpaid',
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price REAL NOT NULL,
    total_price REAL NOT NULL,
    color TEXT,
    size TEXT,
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    payment_ref TEXT UNIQUE NOT NULL,
    method TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending_review',
    is_demo INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    reviewed_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    reviewed_at TEXT
);

CREATE TABLE IF NOT EXISTS payment_receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER UNIQUE NOT NULL REFERENCES payments(id),
    file_path TEXT NOT NULL,
    original_name TEXT,
    uploaded_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id),
    customer_id INTEGER NOT NULL REFERENCES users(id),
    supervisor_id INTEGER REFERENCES users(id),
    transaction_rating INTEGER NOT NULL,
    supervisor_rating INTEGER NOT NULL,
    speed_rating INTEGER NOT NULL,
    communication_rating INTEGER NOT NULL,
    overall_rating INTEGER NOT NULL,
    comment TEXT,
    eligible INTEGER NOT NULL DEFAULT 0,
    environment TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS salary_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    total_base_salary REAL NOT NULL,
    total_deductions REAL NOT NULL,
    total_bonus REAL NOT NULL,
    approved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(period)
);

CREATE TABLE IF NOT EXISTS salary_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_ref TEXT UNIQUE NOT NULL,
    supervisor_id INTEGER NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL CHECK(kind IN ('base_salary','deduction','bonus')),
    amount_sar REAL NOT NULL,
    rating_batch_start INTEGER,
    rating_batch_end INTEGER,
    period TEXT NOT NULL,
    approved INTEGER NOT NULL DEFAULT 1,
    environment TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(supervisor_id, rating_batch_start, rating_batch_end, environment)
);

CREATE TABLE IF NOT EXISTS exchange_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_currency TEXT NOT NULL,
    target_currency TEXT NOT NULL,
    rate REAL NOT NULL,
    applied_at TEXT NOT NULL,
    created_by INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS shipping_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    status TEXT NOT NULL,
    note TEXT,
    updated_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'internal',
    entity_type TEXT,
    entity_id TEXT,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS promo_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    discount_percent REAL NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS support_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER REFERENCES users(id),
    actor_user_id INTEGER REFERENCES users(id),
    subject TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payment_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    payment_ref TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor_user_id INTEGER REFERENCES users(id),
    details TEXT,
    created_at TEXT NOT NULL
);
"""


def get_db():
    if "db" not in g:
        path = os.getenv("DATABASE_PATH", DB_PATH)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(SCHEMA)

    defaults = {
        "salary_base_sar": "1000",
        "exchange_yer_per_sar": "140",
        "negative_threshold": "5",
        "deduction_sar": "350",
        "app_mode": "DEMO",
        "whatsapp_enabled": "0",
        "margin_percent": "0.15",
    }
    for key, value in defaults.items():
        db.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
            (key, value),
        )
    db.commit()


def seed_demo():
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    demo_users = [
        ("admin", "DemoAdmin!2026", "مدير تجريبي", "admin", None),
        ("supervisor", "DemoSupervisor!2026", "مشرف تجريبي", "supervisor", "SUP-1001"),
        ("customer", "DemoCustomer!2026", "عميل تجريبي", "customer", None),
    ]

    for username, password, display_name, role, supervisor_code in demo_users:
        exists = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if not exists:
            db.execute(
                "INSERT INTO users(username, password_hash, display_name, role, supervisor_code, active, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
                (username, generate_password_hash(password), display_name, role, supervisor_code, now),
            )

    customer = db.execute("SELECT id FROM users WHERE username = 'customer' ").fetchone()
    supervisor = db.execute("SELECT id FROM users WHERE username = 'supervisor' ").fetchone()
    admin = db.execute("SELECT id FROM users WHERE username = 'admin' ").fetchone()

    if customer:
        existing_customer = db.execute("SELECT id FROM customers WHERE user_id = ?", (customer["id"],)).fetchone()
        if not existing_customer:
            db.execute(
                "INSERT INTO customers(user_id, customer_code, full_name, country, whatsapp_number, address, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (customer["id"], "62782", "عميل تجريبي", "اليمن", "+966500000000", "صنعاء", now, now),
            )

    if supervisor:
        existing_supervisor = db.execute("SELECT id FROM supervisors WHERE user_id = ?", (supervisor["id"],)).fetchone()
        if not existing_supervisor:
            db.execute(
                "INSERT INTO supervisors(user_id, supervisor_code, assigned_orders, active, created_at) VALUES (?, ?, 0, 1, ?)",
                (supervisor["id"], "SUP-1001", now),
            )

    order_exists = db.execute("SELECT id FROM orders WHERE order_code = 'ORD-1048' ").fetchone()
    if not order_exists and customer and supervisor:
        db.execute(
            """
            INSERT INTO orders(
                order_code, customer_id, supervisor_id, product_name, product_url, quantity,
                unit_price, total_amount, currency, country, options, environment,
                status, payment_status, is_demo, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD-1048",
                customer["id"],
                supervisor["id"],
                "منتج تجريبي — مثال توضيحي",
                "https://www.shein.com/",
                1,
                50000,
                50000,
                "YER",
                "اليمن",
                "مقاس L - اللون أسود",
                "DEMO",
                "received",
                "unpaid",
                1,
                now,
                now,
            ),
        )

    notifications = [
        (customer["id"] if customer else None, "طلب تجريبي", "تم إنشاء طلب تجريبي لك بنجاح.", "internal", "order", 0, now),
        (supervisor["id"] if supervisor else None, "إشعار تجريبي", "تم تخصيص طلب تجريبي للمراجعة.", "internal", "order", 0, now),
        (admin["id"] if admin else None, "لوحة المدير", "النظام التجريبي جاهز للاختبار.", "internal", "system", 0, now),
    ]
    for item in notifications:
        db.execute(
            "INSERT OR IGNORE INTO notifications(user_id, title, message, channel, entity_type, is_read, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            item,
        )

    db.commit()


def log_event(db, actor_user_id, action, entity_type, entity_id, details=""):
    db.execute(
        "INSERT INTO audit_logs(actor_user_id, action, entity_type, entity_id, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (actor_user_id, action, entity_type, str(entity_id), details, datetime.now(timezone.utc).isoformat()),
    )


DB_PATH = os.getenv("DATABASE_PATH", DB_PATH)
