import os
from datetime import datetime, timezone

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash
from dotenv import load_dotenv

from auth import current_user, login_required, role_required
from database import close_db, get_db, init_db, log_event, seed_demo
from payment_service import create_payment_record, review_payment
from pricing_service import calculate_final_price
from product_service import validate_shein_link
from rating_service import submit_rating
from shipping_service import update_shipping_status

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


@app.context_processor
def inject_globals():
    return {"current_user": current_user(), "app_mode": app.config["APP_MODE"]}


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
        user = db.execute("SELECT * FROM users WHERE username = ? AND active = 1", (username,)).fetchone()
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
        orders = db.execute("SELECT * FROM orders WHERE customer_id = ? ORDER BY id DESC LIMIT 20", (user["id"],)).fetchall()
        stats = {
            "orders": db.execute("SELECT COUNT(*) AS n FROM orders WHERE customer_id = ?", (user["id"],)).fetchone()["n"],
            "pending": db.execute("SELECT COUNT(*) AS n FROM orders WHERE customer_id = ? AND payment_status != 'paid'", (user["id"],)).fetchone()["n"],
        }
    elif user["role"] == "supervisor":
        orders = db.execute("SELECT * FROM orders WHERE supervisor_id = ? OR supervisor_id IS NULL ORDER BY id DESC LIMIT 20", (user["id"],)).fetchall()
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


@app.route("/orders/new", methods=["GET", "POST"])
@login_required
def new_order():
    user = current_user()
    if user["role"] not in ("customer", "admin"):
        abort(403)
    if request.method == "POST":
        db = get_db()
        product_url = request.form.get("product_url", "").strip()
        product_name = request.form.get("product_name", "").strip() or "منتج SHEIN"
        quantity = max(1, int(request.form.get("quantity", "1") or "1"))
        unit_price = float(request.form.get("unit_price", "0") or "0")
        country = request.form.get("country", "اليمن").strip()

        if not validate_shein_link(product_url):
            flash("رابط المنتج غير صحيح أو غير مدعوم", "error")
            return render_template("new_order.html")
        if unit_price <= 0:
            flash("أدخل سعر منتج صحيح", "error")
            return render_template("new_order.html")

        order_code = f"ORD-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        total_amount = calculate_final_price(unit_price, quantity)
        now = datetime.now(timezone.utc).isoformat()

        db.execute(
            "INSERT INTO orders(order_code, customer_id, supervisor_id, product_name, product_url, quantity, unit_price, total_amount, currency, country, options, environment, status, payment_status, is_demo, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                order_code,
                user["id"],
                None,
                product_name,
                product_url,
                quantity,
                unit_price,
                total_amount,
                "YER",
                country,
                f"مقاس:{request.form.get('size', '')}; لون:{request.form.get('color', '')}",
                app.config["APP_MODE"],
                "received",
                "unpaid",
                1 if app.config["APP_MODE"] == "DEMO" else 0,
                now,
                now,
            ),
        )
        order = db.execute("SELECT id FROM orders WHERE order_code = ?", (order_code,)).fetchone()
        db.execute(
            "INSERT INTO order_items(order_id, product_name, quantity, unit_price, total_price, color, size, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (order["id"], product_name, quantity, unit_price, total_amount, request.form.get("color"), request.form.get("size"), "", now),
        )
        log_event(db, user["id"], "create_order", "order", order["id"], f"إنشاء الطلب {order_code}")
        db.commit()
        flash(f"تم إنشاء الطلب بنجاح: {order_code}", "success")
        return redirect(url_for("order_detail", order_id=order_code))
    return render_template("new_order.html")


@app.route("/orders/<order_id>")
@login_required
def order_detail(order_id):
    db = get_db()
    user = current_user()
    order = db.execute("SELECT * FROM orders WHERE order_code = ?", (order_id,)).fetchone()
    if not order:
        abort(404)
    if user["role"] == "customer" and order["customer_id"] != user["id"]:
        abort(403)
    if user["role"] == "supervisor" and order["supervisor_id"] not in (None, user["id"]):
        abort(403)
    payments = db.execute("SELECT * FROM payments WHERE order_id = ? ORDER BY id DESC", (order["id"],)).fetchall()
    return render_template("order_detail.html", order=order, payments=payments, user=user)


@app.route("/orders/<order_id>/status", methods=["POST"])
@role_required("admin", "supervisor")
def update_order_status(order_id):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE order_code = ?", (order_id,)).fetchone()
    if not order:
        abort(404)
    status = request.form.get("status")
    note = request.form.get("note", "")
    update_shipping_status(db, order["id"], status, current_user()["id"], note)
    db.commit()
    flash("تم تحديث حالة الطلب", "success")
    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/orders/<order_id>/payment", methods=["POST"])
@login_required
def add_payment(order_id):
    db = get_db()
    user = current_user()
    order = db.execute("SELECT * FROM orders WHERE order_code = ?", (order_id,)).fetchone()
    if not order:
        abort(404)
    if user["role"] != "customer" or order["customer_id"] != user["id"]:
        abort(403)
    try:
        amount = float(request.form.get("amount", "0") or "0")
        method = request.form.get("method", "manual_receipt")
        ref = create_payment_record(db, order["id"], method, amount, order["currency"], "إيصال موثق", user["id"], True if app.config["APP_MODE"] == "DEMO" else False)
        db.commit()
        flash(f"تم تسجيل دفعة جديدة: {ref}", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/orders/<order_id>/rate", methods=["POST"])
@login_required
def rate_order(order_id):
    db = get_db()
    user = current_user()
    order = db.execute("SELECT * FROM orders WHERE order_code = ?", (order_id,)).fetchone()
    if not order:
        abort(404)
    if user["role"] != "customer" or order["customer_id"] != user["id"]:
        abort(403)
    try:
        submit_rating(db, order["id"], user["id"], request.form, app.config["APP_MODE"])
        db.commit()
        flash("تم حفظ التقييم بنجاح", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("order_detail", order_id=order_id))


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
    return render_template("admin_dashboard.html", stats=stats, recent_orders=recent_orders)


@app.route("/admin/reset-demo", methods=["POST"])
@role_required("admin")
def reset_demo():
    if app.config["APP_MODE"] != "DEMO":
        flash("إعادة ضبط الوضع التجريبي متاحة فقط في DEMO", "error")
        return redirect(url_for("admin_dashboard"))
    db = get_db()
    db.execute("DELETE FROM payments")
    db.execute("DELETE FROM order_items")
    db.execute("DELETE FROM shipping_updates")
    db.execute("DELETE FROM orders")
    db.execute("DELETE FROM customers")
    db.execute("DELETE FROM supervisors")
    db.execute("DELETE FROM notifications")
    db.execute("DELETE FROM audit_logs")
    db.execute("DELETE FROM users WHERE username IN ('admin', 'supervisor', 'customer')")
    db.commit()
    seed_demo()
    db.commit()
    flash("تمت إعادة ضبط البيانات التجريبية", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/payments/<int:payment_id>/review", methods=["POST"])
@role_required("admin", "supervisor")
def review_payment_route(payment_id):
    db = get_db()
    payment = db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
    if not payment:
        abort(404)
    accepted = request.form.get("accepted") == "true"
    note = request.form.get("note", "")
    review_payment(db, payment["order_id"], payment_id, accepted, current_user()["id"], note)
    db.commit()
    flash("تم تحديث مراجعة الدفع", "success")
    return redirect(url_for("dashboard"))


@app.route("/health")
def health():
    return {"status": "ok", "mode": app.config["APP_MODE"], "whatsapp_configured": bool(app.config["WHATSAPP_TOKEN"] and app.config["WHATSAPP_PHONE_NUMBER_ID"]) }


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
        return {"received": False, "reason": "Webhook disabled in DEMO mode."}, 503
    return {"received": False, "reason": "Signature verification not enabled yet."}, 501


if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
