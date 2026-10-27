from __future__ import annotations

from typing import Any


class WhatsAppClient:
    def __init__(self, token: str = "", phone_number_id: str = ""):
        self.token = token
        self.phone_number_id = phone_number_id

    def is_configured(self) -> bool:
        return bool(self.token and self.phone_number_id)

    def send_text_message(self, to_number: str, message: str) -> dict[str, Any]:
        if not self.is_configured():
            return {"status": "not_configured", "to": to_number, "message": message}
        return {"status": "queued", "to": to_number, "message": message}

    def send_template(self, to_number: str, template_name: str, language: str = "ar") -> dict[str, Any]:
        if not self.is_configured():
            return {"status": "not_configured", "to": to_number, "template": template_name}
        return {"status": "queued", "to": to_number, "template": template_name, "language": language}
