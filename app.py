import os
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from db import get_db, init_db, seed_demo, close_db
from services import (
    create_order, set_order_status, record_cash_payment, review_receipt,
    submit_rating, apply_salary_rules, get_dashboard_stats, log_event
)

load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-me")
app.config["APP_MODE"] = os.getenv("APP_MODE", "DEMO").upper()
app.config["WHATSAPP_TOKEN"] = os.getenv("WHATSAPP_TOKEN", "")
app.config["WHATSAPP_PHONE_NUMBER_ID"] = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
app.config["WHATSAPP_VERIFY_TOKEN"] = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
app.config["META_APP_SECRET"] = os.getenv("META_APP_SECRET", "")
app.config["DEMO_ALLOW_LOGIN"] = os.getenv("DEMO_ALLOW_LOGIN", "true").lower() == "true"

app.teardown_appcontext(close_db)

with app.app_context():
    init_db()
    if app.config["APP_MODE"] == "DEMO":
        seed_demo()

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    db = get_db()
    return db.execute("SELECT id, username, display_name, role, supervisor_code, active FROM users WHERE id=?", (uid,)).fetchone()

@app.context_processor
def inject_globals():
    return {"current_user": current_user(), "app_mode": app.config["APP_MODE"]}

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user or user["role"] not in roles:
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
        user = db.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            log_event(db, user["id"], "login", "user", str(user["id"]), "تسجيل دخول")
            db.commit()
            target = request.args.get("next")
            return redirect(target if target and target.startswith("/") else url_for("dashboard"))
        flash("اسم المستخدم أو كلمة المرور غير صحيحة.", "error")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    db = get_db()
    if user["role"] == "customer":
        orders = db.execute("SELECT * FROM orders WHERE customer_id=? ORDER BY id DESC", (user["id"],)).fetchall()
    elif user["role"] == "supervisor":
        orders = db.execute("SELECT * FROM orders WHERE supervisor_id=? OR supervisor_id IS NULL ORDER BY id DESC", (user["id"],)).fetchall()
    else:
        orders = db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 50").fetchall()
    stats = get_dashboard_stats(db, user)
    return render_template("dashboard.html", orders=orders, stats=stats, user=user)

@app.route("/orders/new", methods=["GET", "POST"])
@roles_required("customer", "admin")
def new_order():
    if request.method == "POST":
        db = get_db()
        user = current_user()
        link = request.form.get("product_url", "").strip()
        product = request.form.get("product_name", "").strip() or "منتج — يحتاج إدخال بياناته"
        qty = max(1, min(100, int(request.form.get("quantity", "1") or "1")))
        price = float(request.form.get("unit_price", "0") or "0")
        country = request.form.get("country", "اليمن").strip()
        options = request.form.get("options", "").strip()
        if not link.startswith(("https://", "http://")):
            flash("أدخل رابطًا صحيحًا يبدأ بـ https:// أو http://", "error")
            return render_template("new_order.html")
        if price <= 0:
            flash("أدخل السعر التقديري للمنتج. لا يتم اختلاق السعر تلقائيًا.", "error")
            return render_template("new_order.html")
        customer_id = user["id"] if user["role"] == "customer" else None
        order_id = create_order(db, customer_id, product, link, qty, price, country, options, app.config["APP_MODE"])
        db.commit()
        flash(f"تم إنشاء الطلب {order_id}. السعر المُدخل تقديري ولم يتم جلبه من SHEIN تلقائيًا.", "success")
        return redirect(url_for("order_detail", order_id=order_id))
    return render_template("new_order.html")

@app.route("/orders/<order_id>")
@login_required
def order_detail(order_id):
    db = get_db()
    user = current_user()
    order = db.execute("""
        SELECT o.*, c.display_name AS customer_name, c.username AS customer_username,
               s.display_name AS supervisor_name, s.supervisor_code
        FROM orders o
        LEFT JOIN users c ON c.id=o.customer_id
        LEFT JOIN users s ON s.id=o.supervisor_id
        WHERE o.order_code=?
    """, (order_id,)).fetchone()
    if not order:
        abort(404)
    if user["role"] == "customer" and order["customer_id"] != user["id"]:
        abort(403)
    if user["role"] == "supervisor" and order["supervisor_id"] not in (None, user["id"]):
        abort(403)
    events = db.execute("SELECT * FROM audit_logs WHERE entity_type='order' AND entity_id=? ORDER BY id DESC", (str(order["id"]),)).fetchall()
    payments = db.execute("SELECT * FROM payments WHERE order_id=? ORDER BY id DESC", (order["id"],)).fetchall()
    supervisors = db.execute("SELECT id, display_name, supervisor_code FROM users WHERE role='supervisor' AND active=1") .fetchall() if user["role"] in ("admin","supervisor") else []
    return render_template("order_detail.html", order=order, events=events, payments=payments, supervisors=supervisors)

@app.route("/orders/<order_id>/receipt", methods=["POST"])
@roles_required("customer")
def upload_demo_receipt(order_id):
    db = get_db()
    user = current_user()
    order = db.execute("SELECT * FROM orders WHERE order_code=? AND customer_id=?", (order_id, user["id"])).fetchone()
    if not order:
        abort(404)
    if app.config["APP_MODE"] != "DEMO":
        flash("رفع الإيصالات الحقيقي يحتاج إعداد تخزين آمن. هذه الوظيفة متاحة في وضع DEMO فقط.", "error")
        return redirect(url_for("order_detail", order_id=order_id))
    ref = f"PAY-{100000 + int(datetime.now().timestamp()) % 899999}"
    db.execute("INSERT INTO payments(order_id, payment_ref, method, amount, currency, status, is_demo, note, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
               (order["id"], ref, "demo_receipt", order["total_amount"], order["currency"], "pending_review", 1, "إيصال تجريبي وهمي — لا يثبت وصول أموال", datetime.now(timezone.utc).isoformat()))
    log_event(db, user["id"], "receipt_uploaded_demo", "order", str(order["id"]), "إيصال تجريبي غير حقيقي")
    db.commit()
    flash("تم تسجيل إيصال تجريبي للمراجعة. لم يتم تأكيد الدفع.", "success")
    return redirect(url_for("order_detail", order_id=order_id))

@app.route("/orders/<order_id>/action", methods=["POST"])
@roles_required("supervisor", "admin")
def order_action(order_id):
    db = get_db()
    user = current_user()
    order = db.execute("SELECT * FROM orders WHERE order_code=?", (order_id,)).fetchone()
    if not order:
        abort(404)
    if user["role"] == "supervisor" and order["supervisor_id"] not in (None, user["id"]):
        abort(403)
    action = request.form.get("action")
    note = request.form.get("note", "").strip()
    try:
        if action == "assign":
            target_id = int(request.form.get("supervisor_id", "0"))
            target = db.execute("SELECT id FROM users WHERE id=? AND role='supervisor' AND active=1", (target_id,)).fetchone()
            if not target or user["role"] != "admin":
                abort(403)
            db.execute("UPDATE orders SET supervisor_id=?, updated_at=? WHERE id=?", (target_id, datetime.now(timezone.utc).isoformat(), order["id"]))
            log_event(db, user["id"], "assign_supervisor", "order", str(order["id"]), f"تعيين مشرف {target_id}")
        elif action == "approve":
            db.execute("UPDATE orders SET status='approved', updated_at=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), order["id"]))
            log_event(db, user["id"], "approve_order", "order", str(order["id"]), "موافقة على الطلب — لا تعني تأكيد الدفع")
        elif action == "cash":
            amount = float(request.form.get("amount", "0") or "0")
            currency = request.form.get("currency", "YER")
            if amount <= 0:
                raise ValueError("أدخل مبلغًا صحيحًا.")
            record_cash_payment(db, order, user, amount, currency, app.config["APP_MODE"], note)
        elif action == "review_paid":
            payment_id = int(request.form.get("payment_id", "0"))
            review_receipt(db, order, user, payment_id, True, note, app.config["APP_MODE"])
        elif action == "review_reject":
            payment_id = int(request.form.get("payment_id", "0"))
            review_receipt(db, order, user, payment_id, False, note or "لم يتم التحقق من وصول الأموال", app.config["APP_MODE"])
        elif action == "ship":
            new_status = request.form.get("status", "")
            allowed = {"packing", "shipped", "out_for_delivery", "delivered", "cancelled"}
            if new_status not in allowed:
                raise ValueError("حالة شحن غير صحيحة.")
            if new_status in {"packing", "shipped", "out_for_delivery", "delivered"} and order["payment_status"] != "paid":
                raise ValueError("يجب تأكيد الدفع قبل الانتقال إلى مراحل الشحن.")
            set_order_status(db, order, user, new_status, note)
        else:
            raise ValueError("إجراء غير معروف.")
        db.commit()
        flash("تم حفظ الإجراء.", "success")
    except ValueError as exc:
        db.rollback()
        flash(str(exc), "error")
    return redirect(url_for("order_detail", order_id=order_id))

@app.route("/orders/<order_id>/rate", methods=["POST"])
@roles_required("customer")
def rate_order(order_id):
    db = get_db()
    user = current_user()
    order = db.execute("SELECT * FROM orders WHERE order_code=? AND customer_id=?", (order_id, user["id"])).fetchone()
    if not order:
        abort(404)
    try:
        submit_rating(db, order, user, request.form, app.config["APP_MODE"])
        db.commit()
        flash("تم حفظ التقييم.", "success")
    except ValueError as exc:
        db.rollback()
        flash(str(exc), "error")
    return redirect(url_for("order_detail", order_id=order_id))

@app.route("/admin/supervisors")
@roles_required("admin")
def supervisors():
    db = get_db()
    rows = db.execute("""
        SELECT u.id,u.display_name,u.supervisor_code,u.active,
               COALESCE((SELECT COUNT(*) FROM orders o WHERE o.supervisor_id=u.id),0) AS order_count,
               COALESCE((SELECT AVG((r.transaction_rating+r.supervisor_rating+r.speed_rating+r.communication_rating+r.overall_rating)/5.0) FROM ratings r WHERE r.supervisor_id=u.id),0) AS avg_rating,
               COALESCE((SELECT COUNT(*) FROM ratings r WHERE r.supervisor_id=u.id AND r.supervisor_rating<=2),0) AS negative_count
        FROM users u WHERE u.role='supervisor' ORDER BY u.id
    """).fetchall()
    return render_template("supervisors.html", supervisors=rows)

@app.route("/admin/supervisors/new", methods=["POST"])
@roles_required("admin")
def add_supervisor():
    name = request.form.get("display_name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not name or not username or len(password) < 10:
        flash("أدخل الاسم واسم المستخدم وكلمة مرور لا تقل عن 10 أحرف.", "error")
        return redirect(url_for("supervisors"))
    db = get_db()
    exists = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if exists:
        flash("اسم المستخدم مستخدم بالفعل.", "error")
        return redirect(url_for("supervisors"))
    code_num = db.execute("SELECT COUNT(*) AS n FROM users WHERE role='supervisor'").fetchone()["n"] + 1001
    db.execute("INSERT INTO users(username,password_hash,display_name,role,supervisor_code,active,created_at) VALUES(?,?,?,?,?,1,?)",
               (username, generate_password_hash(password), name, "supervisor", f"SUP-{code_num}", datetime.now(timezone.utc).isoformat()))
    log_event(db, current_user()["id"], "create_supervisor", "user", username, f"إنشاء مشرف {name}")
    db.commit()
    flash("تم إنشاء حساب المشرف.", "success")
    return redirect(url_for("supervisors"))

@app.route("/admin/payroll")
@roles_required("admin")
def payroll():
    db = get_db()
    settings = {r["key"]: r["value"] for r in db.execute("SELECT key,value FROM settings").fetchall()}
    apply_salary_rules(db, settings, app.config["APP_MODE"])
    db.commit()
    rows = db.execute("""
      SELECT u.id,u.display_name,u.supervisor_code,
      COALESCE((SELECT SUM(amount_sar) FROM salary_transactions st WHERE st.supervisor_id=u.id AND st.kind='deduction' AND st.approved=1),0) AS deductions,
      COALESCE((SELECT COUNT(*) FROM ratings r WHERE r.supervisor_id=u.id AND r.eligible=1 AND r.supervisor_rating<=2),0) AS bad_ratings
      FROM users u WHERE u.role='supervisor'
    """).fetchall()
    return render_template("payroll.html", rows=rows, settings=settings)

@app.route("/admin/payroll/settings", methods=["POST"])
@roles_required("admin")
def save_payroll_settings():
    db = get_db()
    values = {
        "salary_base_sar": request.form.get("salary_base_sar", "1000"),
        "exchange_yer_per_sar": request.form.get("exchange_yer_per_sar", "140"),
        "negative_threshold": request.form.get("negative_threshold", "5"),
        "deduction_sar": request.form.get("deduction_sar", "350"),
    }
    try:
        if float(values["salary_base_sar"]) < 0 or float(values["exchange_yer_per_sar"]) <= 0 or int(values["negative_threshold"]) < 1 or float(values["deduction_sar"]) < 0:
            raise ValueError()
    except ValueError:
        flash("تحقق من إدخال أرقام صحيحة.", "error")
        return redirect(url_for("payroll"))
    for k, v in values.items():
        db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
    log_event(db, current_user()["id"], "update_payroll_settings", "settings", "payroll", "تعديل إعدادات الرواتب")
    db.commit()
    flash("تم حفظ الإعدادات.", "success")
    return redirect(url_for("payroll"))

@app.route("/admin/audit")
@roles_required("admin")
def audit():
    db = get_db()
    logs = db.execute("""
      SELECT a.*,u.display_name FROM audit_logs a LEFT JOIN users u ON u.id=a.actor_user_id
      ORDER BY a.id DESC LIMIT 200
    """).fetchall()
    return render_template("audit.html", logs=logs)

@app.route("/health")
def health():
    return {"status": "ok", "mode": app.config["APP_MODE"], "whatsapp_configured": bool(app.config["WHATSAPP_TOKEN"] and app.config["WHATSAPP_PHONE_NUMBER_ID"])}

@app.route("/webhook/whatsapp", methods=["GET", "POST"])
def whatsapp_webhook():
    # GET verification follows Meta's webhook challenge protocol.
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge", "")
        if mode == "subscribe" and token and token == app.config["WHATSAPP_VERIFY_TOKEN"]:
            return challenge, 200
        return "Forbidden", 403
    # Production deployment must additionally verify X-Hub-Signature-256 using META_APP_SECRET
    # before accepting POST events. This starter intentionally does not process unsigned events.
    if app.config["APP_MODE"] != "LIVE" or not app.config["META_APP_SECRET"]:
        return {"received": False, "reason": "Webhook processing disabled until LIVE mode and signature verification are configured."}, 503
    return {"received": False, "reason": "Implement and test Meta signature verification before enabling event processing."}, 501

if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
