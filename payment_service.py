from __future__ import annotations


def calculate_final_price(unit_price: float, quantity: int, shipping_fee: float = 0.0, discount: float = 0.0) -> float:
    subtotal = float(unit_price) * int(quantity)
    discounted = max(subtotal - float(discount), 0.0)
    total = discounted + float(shipping_fee)
    return round(total, 2)


def convert_currency(amount: float, rate: float) -> float:
    return round(float(amount) * float(rate), 2)
