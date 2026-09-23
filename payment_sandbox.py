#!/usr/bin/env python3
"""
Payment sandbox — система под тест для тестового задания QA.
Требования: Python 3.9+; внешних зависимостей нет.
Запуск: python3 payment_sandbox.py   (порт 8080)

Не редактировать. Это система под тест: пиши автотесты снаружи.
"""

import json
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PAYMENTS = {}   # payment_id -> record
IDEM = {}       # idempotency_key -> payment_id

ALLOWED_CURRENCIES = {"RUB", "USD", "THB"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # тихий лог

    def do_GET(self):
        request = urlparse(self.path)

        if request.path == "/health":
            return self._send(200, {"status": "ok"})

        if request.path == "/debug/payments":
            beneficiary_ref = parse_qs(request.query).get("beneficiary_ref", [None])[0]
            if not beneficiary_ref:
                return self._send(400, {"error": "beneficiary_ref required"})

            payments = [
                record
                for record in PAYMENTS.values()
                if record["beneficiary_ref"] == beneficiary_ref
            ]
            return self._send(200, {"count": len(payments), "payments": payments})

        parts = request.path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "v1" and parts[1] == "payments":
            pid = parts[2]
            rec = PAYMENTS.get(pid)
            if not rec:
                return self._send(404, {"error": "not found"})
            return self._send(200, rec)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/v1/payments":
            return self._send(404, {"error": "not found"})

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return self._send(422, {"error": "invalid json"})

        key = self.headers.get("Idempotency-Key")
        if not key:
            return self._send(400, {"error": "idempotency key required"})

        # --- валидация тела ---
        required = ("corridor", "amount", "currency", "beneficiary_ref")
        if any(f not in body for f in required):
            return self._send(422, {"error": "missing fields"})
        if not isinstance(body["amount"], (int, float)):
            return self._send(422, {"error": "amount must be a number"})
        if body["currency"] not in ALLOWED_CURRENCIES:
            return self._send(422, {"error": "unsupported currency"})
        # NB: сумма <= 0 сюда проходит.

        # --- идемпотентность ---
        if key in IDEM:
            existing = PAYMENTS[IDEM[key]]
            # реплей: возвращаем оригинал (тело не сверяем)
            return self._send(200, existing)

        pid = "P-" + uuid.uuid4().hex[:12]
        rec = {
            "payment_id": pid,
            "status": "processing",
            "idempotency_key": key,
            "corridor": body["corridor"],
            "amount": body["amount"],
            "currency": body["currency"],
            "beneficiary_ref": body["beneficiary_ref"],
        }
        PAYMENTS[pid] = rec

        if self.headers.get("X-Simulate") == "fail-after-create":
            return self._send(500, {"error": "upstream timeout"})

        IDEM[key] = pid
        return self._send(201, rec)


if __name__ == "__main__":
    print("Payment sandbox on http://127.0.0.1:8080")
    ThreadingHTTPServer(("127.0.0.1", 8080), Handler).serve_forever()
