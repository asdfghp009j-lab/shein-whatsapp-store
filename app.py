import os
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash
from dotenv import load_dotenv

from db import close_db, get_db, init_db, log_event, seed_demo

load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
app.config["APP_MODE"] = os.getenv("APP_MODE", "DEMO").upper()
app.config["WHATSAPP_TOKEN"] = os.getenv("WHATSAPP_TOKEN", "")
app.config["WHATSAPP_PHONE_NUMBER_ID"] = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
app.config["WHATSAPP_VERIFY_TOKEN"] = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
app.config["META_APP_SECRET"] = os.getenv("META_APP_SECRET", "")

app.teardown_appcontext(close_db)

with app.app_context():
    init_db()
    if app.config["APP_MODE"] == "DEMO":
        seed_demo()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    db = get_db()
    return db.execute(
        "SELECT id, username, display_name, role, supervisor_code, active FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()


@app.context_processor
def inject_globals():
    return {
        "current_user": current_user(),
        "app_mode": app.config["APP_MODE"],
    }


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None or user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.route("/")
def index():
    if not current_user():
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ? AND active = 1",
            (username,),
        ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            log_event(db, user["id"], "login", "user", str(user["id"]), "تسجيل دخول")
            db.commit()
            next_target = request.args.get("next")
            return redirect(next_target if next_target and next_target.startswith("/") else url_for("dashboard"))
        flash("اسم المستخدم أو كلمة المرور غير صحيحة", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    user = current_user()
    if user["role"] == "customer":
        orders = db.execute(
            "SELECT * FROM orders WHERE customer_id = ? ORDER BY id DESC LIMIT 20",
            (user["id"],),
        ).fetchall()
        stats = {
            "orders": db.execute("SELECT COUNT(*) AS n FROM orders WHERE customer_id = ?", (user["id"],)).fetchone()["n"],
            "pending": db.execute("SELECT COUNT(*) AS n FROM orders WHERE customer_id = ? AND payment_status != 'paid'", (user["id"],)).fetchone()["n"],
        }
    elif user["role"] == "supervisor":
        orders = db.execute(
            "SELECT * FROM orders WHERE supervisor_id = ? OR supervisor_id IS NULL ORDER BY id DESC LIMIT 20",
            (user["id"],),
        ).fetchall()
        stats = {
            "orders": db.execute("SELECT COUNT(*) AS n FROM orders WHERE supervisor_id = ? OR supervisor_id IS NULL", (user["id"],)).fetchone()["n"],
            "pending": db.execute("SELECT COUNT(*) AS n FROM orders WHERE (supervisor_id = ? OR supervisor_id IS NULL) AND payment_status != 'paid'", (user["id"],)).fetchone()["n"],
        }
    else:
        orders = db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 20").fetchall()
        stats = {
            "orders": db.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"],
            "pending": db.execute("SELECT COUNT(*) AS n FROM orders WHERE payment_status != 'paid'").fetchone()["n"],
            "paid": db.execute("SELECT COUNT(*) AS n FROM orders WHERE payment_status = 'paid'").fetchone()["n"],
        }
    return render_template("dashboard.html", user=user, orders=orders, stats=stats)


@app.route("/admin")
@role_required("admin")
def admin_dashboard():
    db = get_db()
    stats = {
        "customers": db.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'customer'").fetchone()["n"],
        "supervisors": db.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'supervisor'").fetchone()["n"],
        "orders": db.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"],
        "pending": db.execute("SELECT COUNT(*) AS n FROM orders WHERE payment_status != 'paid'").fetchone()["n"],
    }
    recent_orders = db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 10").fetchall()
    return render_template("admin_dashboard.html", user=current_user(), stats=stats, recent_orders=recent_orders)


@app.route("/admin/reset-demo", methods=["POST"])
@role_required("admin")
def reset_demo():
    if app.config["APP_MODE"] != "DEMO":
        flash("إعادة ضبط البيانات التجريبية متاحة فقط في وضع DEMO", "error")
        return redirect(url_for("admin_dashboard"))
    db = get_db()
    db.execute("DELETE FROM payments")
    db.execute("DELETE FROM order_items")
    db.execute("DELETE FROM orders")
    db.execute("DELETE FROM customers")
    db.execute("DELETE FROM supervisors")
    db.execute("DELETE FROM audit_logs")
    db.execute("DELETE FROM notifications")
    db.execute("DELETE FROM users WHERE username IN ('admin', 'supervisor', 'customer')")
    db.commit()
    seed_demo()
    log_event(db, current_user()["id"], "reset_demo", "system", "demo", "إعادة ضبط الوضع التجريبي")
    db.commit()
    flash("تمت إعادة ضبط البيانات التجريبية", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/health")
def health():
    return {
        "status": "ok",
        "mode": app.config["APP_MODE"],
        "whatsapp_configured": bool(app.config["WHATSAPP_TOKEN"] and app.config["WHATSAPP_PHONE_NUMBER_ID"]),
    }


@app.route("/webhook/whatsapp", methods=["GET", "POST"])
def whatsapp_webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge", "")
        if mode == "subscribe" and token and token == app.config["WHATSAPP_VERIFY_TOKEN"]:
            return challenge, 200
        return "Forbidden", 403

    if app.config["APP_MODE"] != "LIVE":
        return {"received": False, "reason": "Webhook is disabled in DEMO mode."}, 503

    return {"received": False, "reason": "Signature verification and processing are not enabled yet."}, 501


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
