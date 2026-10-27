import os, sqlite3
from flask import g
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash

DB_PATH = os.getenv("DATABASE_PATH", "store.db")

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 username TEXT UNIQUE NOT NULL,
 password_hash TEXT NOT NULL,
 display_name TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('customer','supervisor','admin')),
 supervisor_code TEXT UNIQUE,
 active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 order_code TEXT UNIQUE NOT NULL,
 customer_id INTEGER REFERENCES users(id),
 supervisor_id INTEGER REFERENCES users(id),
 product_name TEXT NOT NULL,
 product_url TEXT NOT NULL,
 quantity INTEGER NOT NULL,
 unit_price REAL NOT NULL,
 total_amount REAL NOT NULL,
 currency TEXT NOT NULL DEFAULT 'YER',
 country TEXT NOT NULL,
 options TEXT,
 environment TEXT NOT NULL CHECK(environment IN ('DEMO','LIVE')),
 status TEXT NOT NULL DEFAULT 'pending_payment',
 payment_status TEXT NOT NULL DEFAULT 'unpaid',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 order_id INTEGER NOT NULL REFERENCES orders(id),
 payment_ref TEXT UNIQUE NOT NULL,
 method TEXT NOT NULL,
 amount REAL NOT NULL,
 currency TEXT NOT NULL,
 status TEXT NOT NULL,
 is_demo INTEGER NOT NULL DEFAULT 1,
 note TEXT,
 reviewed_by INTEGER REFERENCES users(id),
 created_at TEXT NOT NULL,
 reviewed_at TEXT
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
CREATE TABLE IF NOT EXISTS salary_transactions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 transaction_ref TEXT UNIQUE NOT NULL,
 supervisor_id INTEGER NOT NULL REFERENCES users(id),
 kind TEXT NOT NULL,
 amount_sar REAL NOT NULL,
 rating_batch_start INTEGER,
 rating_batch_end INTEGER,
 period TEXT NOT NULL,
 approved INTEGER NOT NULL DEFAULT 0,
 environment TEXT NOT NULL,
 reason TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(supervisor_id, rating_batch_start, rating_batch_end, environment)
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_logs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 actor_user_id INTEGER REFERENCES users(id),
 action TEXT NOT NULL,
 entity_type TEXT NOT NULL,
 entity_id TEXT NOT NULL,
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
    }
    for k, v in defaults.items():
        db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    db.commit()

def seed_demo():
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    users = [
        ("admin", "DemoAdmin!2026", "مدير تجريبي", "admin", None),
        ("supervisor", "DemoSupervisor!2026", "مشرف تجريبي", "supervisor", "SUP-1001"),
        ("customer", "DemoCustomer!2026", "عميل تجريبي", "customer", None),
    ]
    for username, password, name, role, code in users:
        db.execute("INSERT OR IGNORE INTO users(username,password_hash,display_name,role,supervisor_code,active,created_at) VALUES(?,?,?,?,?,1,?)",
                   (username, generate_password_hash(password), name, role, code, now))
    db.commit()
    has_order = db.execute("SELECT id FROM orders WHERE order_code='ORD-1048'").fetchone()
    if not has_order:
        customer = db.execute("SELECT id FROM users WHERE username='customer'").fetchone()
        sup = db.execute("SELECT id FROM users WHERE username='supervisor'").fetchone()
        db.execute("""INSERT INTO orders(order_code,customer_id,supervisor_id,product_name,product_url,quantity,unit_price,total_amount,currency,country,options,environment,status,payment_status,created_at,updated_at)
          VALUES('ORD-1048',?,?,?,?,1,50000,50000,'YER','اليمن','مقاس تجريبي','DEMO','pending_payment','unpaid',?,?)""",
          (customer["id"], sup["id"], "منتج تجريبي — ليس بيانات مستخرجة من SHEIN", "https://www.shein.com/", now, now))
        db.commit()

def log_event(db, actor_user_id, action, entity_type, entity_id, details=""):
    db.execute("INSERT INTO audit_logs(actor_user_id,action,entity_type,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
               (actor_user_id, action, entity_type, str(entity_id), details, datetime.now(timezone.utc).isoformat()))
