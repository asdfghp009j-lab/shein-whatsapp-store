from __future__ import annotations

import hashlib
import hmac

from config import META_APP_SECRET


def verify_meta_signature(raw_body: bytes, signature: str | None) -> bool:
    if not META_APP_SECRET or not signature:
        return False
    expected = "sha256=" + hmac.new(META_APP_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
