from __future__ import annotations

import re
from urllib.parse import urlparse

ALLOWED_HOSTS = {"www.shein.com", "shein.com", "m.shein.com"}


def validate_shein_link(raw_url: str) -> bool:
    if not raw_url:
        return False
    try:
        parsed = urlparse(raw_url)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.netloc not in ALLOWED_HOSTS and not parsed.netloc.endswith(".shein.com"):
        return False
    return True


def extract_product_metadata(raw_url: str, manual_data: dict | None = None):
    data = {
        "source_url": raw_url,
        "name": "",
        "image": "",
        "price": None,
        "sizes": [],
        "colors": [],
        "source": "manual",
        "is_manual": True,
    }

    if manual_data:
        data.update(manual_data)
        data["is_manual"] = True
        return data

    if not validate_shein_link(raw_url):
        return data

    parsed = urlparse(raw_url)
    path = parsed.path or ""
    name_match = re.search(r"/([^/?]+)", path)
    if name_match:
        data["name"] = name_match.group(1).replace("-", " ").title()
    data["source"] = "link_validation_only"
    data["is_manual"] = True
    return data
