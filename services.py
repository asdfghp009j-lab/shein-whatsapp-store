from datetime import datetime, timezone
import secrets
from db import log_event

def now():
    return datetime.now(timezone.utc).isoformat()

def create_order(db, customer_id, product, link, qty, price, country, options, mode):
    latest = db.execute("SELECT id FROM orders ORDER BY id DESC LIMIT 1").fetchone()
    num = (latest["id"] + 1048) if latest else 1048
    code = f"ORD-{num}"
    while db.execute("SELECT 1 FROM orders WHERE order_code=?", (code,)).fetchone():
        num += 1
        code = f"ORD-{num}"
    total = round(float(price) * int(qty), 2)
    cur = db.execute("""INSERT INTO orders(order_code,customer_id,product_name,product_url,quantity,unit_price,total_amount,currency,country,options,environment,status,payment_status,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,'pending_payment','unpaid',?,?)""",
        (code, customer_id, product, link, qty, price, total, "YER", country, options, mode, now(), now()))
    log_event(db, customer_id, "create_order", "order", cur.lastrowid, f"إنشاء {code} في وضع {mode}")
    return code

def set_order_status(db, order, user, status, note=""):
    db.execute("UPDATE orders SET status=?,updated_at=? WHERE id=?", (status, now(), order["id"]))
    log_event(db, user["id"], "update_shipping", "order", order["id"], f"{status}: {note}")

def record_cash_payment(db, order, user, amount, currency, mode, note=""):
    if mode == "LIVE" and order["environment"] != "LIVE":
        raise ValueError("لا يمكن تسجيل دفعة حقيقية لطلب تجريبي.")
    if order["environment"] != mode:
        raise ValueError("بيئة الطلب لا تطابق بيئة الخادم.")
    paid = db.execute("SELECT COALESCE(SUM(amount),0) AS total FROM payments WHERE order_id=? AND status='confirmed' AND currency=?", (order["id"], currency)).fetchone()["total"]
    if currency != order["currency"]:
        raise ValueError("عملة الدفع يجب أن تطابق عملة الطلب في هذه النسخة.")
    ref = "PAY-" + secrets.token_hex(5).upper()
    new_total = paid + amount
    status = "paid" if new_total >= order["total_amount"] else "partial"
    db.execute("INSERT INTO payments(order_id,payment_ref,method,amount,currency,status,is_demo,note,reviewed_by,created_at,reviewed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
               (order["id"], ref, "cash", amount, currency, "confirmed", 1 if mode=="DEMO" else 0, note, user["id"], now(), now()))
    db.execute("UPDATE orders SET payment_status=?,status=?,updated_at=? WHERE id=?",
               (status, "packing" if status=="paid" else order["status"], now(), order["id"]))
    log_event(db, user["id"], "cash_payment", "order", order["id"], f"{ref}; amount={amount} {currency}; mode={mode}")
    if status == "paid":
        log_event(db, user["id"], "payment_confirmed", "order", order["id"], "تأكيد استلام نقدي بعد تأكيد المشرف")
    return ref

def review_receipt(db, order, user, payment_id, accepted, note, mode):
    payment = db.execute("SELECT * FROM payments WHERE id=? AND order_id=?", (payment_id, order["id"])).fetchone()
    if not payment:
        raise ValueError("الدفعة غير موجودة.")
    if payment["status"] != "pending_review":
        raise ValueError("هذه الدفعة تمت مراجعتها مسبقًا.")
    if mode == "LIVE":
        raise ValueError("تأكيد الدفع في وضع LIVE يحتاج ربطًا فعليًا بمصدر الدفع والتحقق من وصول الأموال.")
    status = "confirmed" if accepted else "rejected"
    db.execute("UPDATE payments SET status=?,reviewed_by=?,reviewed_at=?,note=? WHERE id=?",
               (status, user["id"], now(), note, payment_id))
    total_paid = db.execute("SELECT COALESCE(SUM(amount),0) AS total FROM payments WHERE order_id=? AND status='confirmed' AND currency=?", (order["id"], order["currency"])).fetchone()["total"]
    pay_status = "paid" if total_paid >= order["total_amount"] else ("partial" if total_paid > 0 else "unpaid")
    order_status = "packing" if pay_status == "paid" else order["status"]
    db.execute("UPDATE orders SET payment_status=?,status=?,updated_at=? WHERE id=?", (pay_status, order_status, now(), order["id"]))
    log_event(db, user["id"], "receipt_review", "order", order["id"], f"{payment['payment_ref']}: {status}; {note}")

def submit_rating(db, order, user, form, mode):
    if order["status"] != "delivered":
        raise ValueError("يمكن تقييم الطلب بعد تأكيد التسليم فقط.")
    if db.execute("SELECT id FROM ratings WHERE order_id=?", (order["id"],)).fetchone():
        raise ValueError("تم تقييم هذا الطلب مسبقًا.")
    vals = {}
    for key in ("transaction_rating", "supervisor_rating", "speed_rating", "communication_rating", "overall_rating"):
        try:
            vals[key] = int(form.get(key, "5"))
        except ValueError:
            raise ValueError("التقييم يجب أن يكون رقمًا من 1 إلى 5.")
        if vals[key] < 1 or vals[key] > 5:
            raise ValueError("التقييم يجب أن يكون بين 1 و5.")
    eligible = 1 if mode == "LIVE" and order["environment"] == "LIVE" and order["supervisor_id"] else 0
    db.execute("""INSERT INTO ratings(order_id,customer_id,supervisor_id,transaction_rating,supervisor_rating,speed_rating,communication_rating,overall_rating,comment,eligible,environment,created_at)
       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
       (order["id"], user["id"], order["supervisor_id"], vals["transaction_rating"], vals["supervisor_rating"], vals["speed_rating"], vals["communication_rating"], vals["overall_rating"], form.get("comment","").strip(), eligible, mode, now()))
    log_event(db, user["id"], "submit_rating", "order", order["id"], f"eligible={eligible}; supervisor_rating={vals['supervisor_rating']}")

def apply_salary_rules(db, settings, mode):
    # DEMO never creates salary deductions. LIVE uses eligible ratings only.
    if mode != "LIVE":
        return
    threshold = max(1, int(settings.get("negative_threshold", "5")))
    deduction = max(0, float(settings.get("deduction_sar", "350")))
    supervisors = db.execute("SELECT id FROM users WHERE role='supervisor'").fetchall()
    for sup in supervisors:
        ratings = db.execute("""SELECT id FROM ratings WHERE supervisor_id=? AND eligible=1 AND environment='LIVE' AND supervisor_rating<=2 ORDER BY id""", (sup["id"],)).fetchall()
        for idx in range(0, len(ratings) - threshold + 1, threshold):
            batch = ratings[idx:idx+threshold]
            start_id, end_id = batch[0]["id"], batch[-1]["id"]
            exists = db.execute("SELECT id FROM salary_transactions WHERE supervisor_id=? AND rating_batch_start=? AND rating_batch_end=? AND environment='LIVE'", (sup["id"], start_id, end_id)).fetchone()
            if exists:
                continue
            ref = "SAL-" + secrets.token_hex(5).upper()
            db.execute("""INSERT INTO salary_transactions(transaction_ref,supervisor_id,kind,amount_sar,rating_batch_start,rating_batch_end,period,approved,environment,reason,created_at)
              VALUES(?,?,?,?,?,?,?,1,'LIVE',?,?)""",
              (ref, sup["id"], "deduction", deduction, start_id, end_id, datetime.now(timezone.utc).strftime("%Y-%m"), f"{threshold} تقييمات سلبية مؤهلة ({start_id}-{end_id})", now()))
            log_event(db, None, "automatic_salary_deduction", "salary", ref, f"supervisor={sup['id']}; amount={deduction}")

def get_dashboard_stats(db, user):
    if user["role"] == "customer":
        orders = db.execute("SELECT COUNT(*) n FROM orders WHERE customer_id=?", (user["id"],)).fetchone()["n"]
        unpaid = db.execute("SELECT COUNT(*) n FROM orders WHERE customer_id=? AND payment_status!='paid'", (user["id"],)).fetchone()["n"]
        return [("طلباتي", orders), ("بانتظار الدفع", unpaid)]
    if user["role"] == "supervisor":
        orders = db.execute("SELECT COUNT(*) n FROM orders WHERE supervisor_id=? OR supervisor_id IS NULL", (user["id"],)).fetchone()["n"]
        pending = db.execute("SELECT COUNT(*) n FROM orders WHERE (supervisor_id=? OR supervisor_id IS NULL) AND status='pending_payment'", (user["id"],)).fetchone()["n"]
        return [("الطلبات المتاحة", orders), ("بانتظار الدفع", pending)]
    return [
        ("كل الطلبات", db.execute("SELECT COUNT(*) n FROM orders").fetchone()["n"]),
        ("بانتظار الدفع", db.execute("SELECT COUNT(*) n FROM orders WHERE payment_status!='paid'").fetchone()["n"]),
        ("مدفوع", db.execute("SELECT COUNT(*) n FROM orders WHERE payment_status='paid'").fetchone()["n"]),
        ("إيصالات قيد المراجعة", db.execute("SELECT COUNT(*) n FROM payments WHERE status='pending_review'").fetchone()["n"]),
    ]
