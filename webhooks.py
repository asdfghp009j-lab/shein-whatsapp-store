from __future__ import annotations

import hashlib
import hmac
import os

from config import META_APP_SECRET


def verify_meta_signature(raw_body: bytes, signature_header: str | None) -> bool:
    if not META_APP_SECRET:
        return False
    if not signature_header:
        return False
    expected = "sha256=" + hmac.new(META_APP_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def verify_webhook_event(payload: dict) -> bool:
    return isinstance(payload, dict) and "entry" in payload
