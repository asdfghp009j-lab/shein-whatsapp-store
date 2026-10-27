import os
import tempfile
import pytest
from flask import Flask
from db import get_db, init_db, seed_demo
from services import create_order, record_cash_payment, submit_rating, apply_salary_rules

@pytest.fixture()
def app():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_PATH"] = path
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    with app.app_context():
        init_db()
        seed_demo()
        yield app
        get_db().close()
    os.unlink(path)
    os.environ.pop("DATABASE_PATH", None)

def test_demo_seeded_order_exists(app):
    with app.app_context():
        db = get_db()
        row = db.execute("SELECT * FROM orders WHERE order_code='ORD-1048'").fetchone()
        assert row is not None
        assert row["environment"] == "DEMO"
        assert row["payment_status"] == "unpaid"

def test_create_order_uses_demo_environment(app):
    with app.app_context():
        db = get_db()
        customer = db.execute("SELECT id FROM users WHERE username='customer'").fetchone()
        code = create_order(db, customer["id"], "Test item", "https://www.shein.com/item", 2, 100, "اليمن", "M", "DEMO")
        db.commit()
        row = db.execute("SELECT * FROM orders WHERE order_code=?", (code,)).fetchone()
        assert row["total_amount"] == 200
        assert row["environment"] == "DEMO"

def test_demo_cash_payment_is_marked_demo(app):
    with app.app_context():
        db = get_db()
        order = db.execute("SELECT * FROM orders WHERE order_code='ORD-1048'").fetchone()
        sup = db.execute("SELECT * FROM users WHERE username='supervisor'").fetchone()
        record_cash_payment(db, order, sup, 50000, "YER", "DEMO", "test")
        db.commit()
        payment = db.execute("SELECT * FROM payments WHERE order_id=?", (order["id"],)).fetchone()
        assert payment["is_demo"] == 1
        refreshed = db.execute("SELECT * FROM orders WHERE id=?", (order["id"],)).fetchone()
        assert refreshed["payment_status"] == "paid"

def test_salary_rules_do_not_deduct_in_demo(app):
    with app.app_context():
        db = get_db()
        settings = {r["key"]: r["value"] for r in db.execute("SELECT key,value FROM settings")}
        apply_salary_rules(db, settings, "DEMO")
        db.commit()
        count = db.execute("SELECT COUNT(*) n FROM salary_transactions").fetchone()["n"]
        assert count == 0
