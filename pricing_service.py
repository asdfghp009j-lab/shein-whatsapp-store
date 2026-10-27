from __future__ import annotations

from urllib.parse import urlparse


ALLOWED_HOSTS = {"www.shein.com", "shein.com", "m.shein.com"}


def validate_shein_link(raw_url: str) -> bool:
    if not raw_url:
        return False
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"}:
        return False
    netloc = parsed.netloc.lower()
    return netloc in ALLOWED_HOSTS or netloc.endswith(".shein.com")


def extract_product_metadata(raw_url: str, manual_data: dict | None = None):
    data = {
        "source_url": raw_url,
        "name": "",
        "image": "",
        "price": None,
        "sizes": [],
        "colors": [],
        "source": "unknown",
    }
    if manual_data:
        data.update(manual_data)
        return data
    if validate_shein_link(raw_url):
        data["source"] = "validated_link"
        data["name"] = "منتج SHEIN" if not raw_url else raw_url.strip().split("/")[-1] or "منتج SHEIN"
        return data
    return data
