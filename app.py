{% extends 'base.html' %}
{% block title %}تفاصيل الطلب{% endblock %}
{% block content %}
<div class="card">
  <h2>تفاصيل الطلب: {{ order.order_code }}</h2>
  <p><strong>المنتج:</strong> {{ order.product_name }}</p>
  <p><strong>السعر:</strong> {{ order.total_amount }} {{ order.currency }}</p>
  <p><strong>الحالة:</strong> {{ order.status }}</p>
  <p><strong>حالة الدفع:</strong> {{ order.payment_status }}</p>
  <p><strong>الدولة:</strong> {{ order.country }}</p>
  <p><strong>الرابط:</strong> <a href="{{ order.product_url }}" target="_blank">{{ order.product_url }}</a></p>
</div>

{% if current_user.role in ['admin', 'supervisor'] %}
<div class="card">
  <h3>تحديث حالة الشحن</h3>
  <form method="post" action="{{ url_for('update_order_status', order_id=order.order_code) }}">
    <div class="form-row">
      <label>الحالة</label>
      <select name="status">
        <option value="received">تم استلام الطلب</option>
        <option value="awaiting_payment">بانتظار الدفع</option>
        <option value="approved">تمت الموافقة</option>
        <option value="payment_confirmed">تم تأكيد الدفع</option>
        <option value="packing">قيد التجهيز</option>
        <option value="shipped">تم الشحن</option>
        <option value="out_for_delivery">خرج للتسليم</option>
        <option value="delivered">تم التسليم</option>
      </select>
    </div>
    <div class="form-row">
      <label>ملاحظات</label>
      <textarea name="note"></textarea>
    </div>
    <button type="submit">تحديث الحالة</button>
  </form>
</div>
{% endif %}

{% if current_user.role == 'customer' %}
<div class="card">
  <h3>تقييم الطلب</h3>
  <form method="post" action="{{ url_for('rate_order', order_id=order.order_code) }}">
    <div class="form-row">
      <label>سهولة المعاملة</label>
      <input type="number" min="1" max="5" name="transaction_rating" value="5">
    </div>
    <div class="form-row">
      <label>أداء المشرف</label>
      <input type="number" min="1" max="5" name="supervisor_rating" value="5">
    </div>
    <div class="form-row">
      <label>سرعة الاستجابة</label>
      <input type="number" min="1" max="5" name="speed_rating" value="5">
    </div>
    <div class="form-row">
      <label>وضوح التواصل</label>
      <input type="number" min="1" max="5" name="communication_rating" value="5">
    </div>
    <div class="form-row">
      <label>التقييم العام</label>
      <input type="number" min="1" max="5" name="overall_rating" value="5">
    </div>
    <div class="form-row">
      <label>تعليق</label>
      <textarea name="comment"></textarea>
    </div>
    <button type="submit">إرسال التقييم</button>
  </form>
</div>
{% endif %}
{% endblock %}
