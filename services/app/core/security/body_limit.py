"""Limit wielkości ciała requestu — obrona przed zapychaniem RAM-u.

Pydantic waliduje długości pól dopiero PO sparsowaniu całego JSON-a, więc bez
tego middleware'a 100 MB payload najpierw ląduje w pamięci, a dopiero potem
dostaje 422. Tutaj ucinamy na progu:

- body z Content-Length ponad limit → 413 payload_too_large,
- body bez Content-Length (chunked) → 411 length_required; uczciwe klienty
  zawsze deklarują długość, a h11 egzekwuje ramkowanie, więc zaniżyć się nie da.

Czysty ASGI (nie BaseHTTPMiddleware) — działa przed routingiem, auth i limiterem,
czyli chroni także requesty nieuwierzytelnione. Rejestracja: server.py.
"""

import json

from services.app.core.errors import ErrorCode

# 64 KB z zapasem starcza na największy legalny payload (bio 2000 znaków
# unicode + reszta pól to ułamek tego).
MAX_BODY_SIZE = 64 * 1024

_METHODS_WITH_BODY = {"POST", "PUT", "PATCH"}


class BodySizeLimitMiddleware:
    def __init__(self, app, max_body_size: int = MAX_BODY_SIZE) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope.get("method") not in _METHODS_WITH_BODY:
            return await self.app(scope, receive, send)

        content_length = None
        for name, value in scope.get("headers") or []:
            if name == b"content-length":
                content_length = value
                break

        if content_length is None:
            # transfer-encoding: chunked albo brak nagłówka — nie da się
            # sprawdzić rozmiaru z góry, więc żądamy jawnej długości
            return await self._reject(send, 411, ErrorCode.LENGTH_REQUIRED)

        try:
            declared = int(content_length)
        except ValueError:
            return await self._reject(send, 411, ErrorCode.LENGTH_REQUIRED)

        if declared > self.max_body_size:
            return await self._reject(send, 413, ErrorCode.PAYLOAD_TOO_LARGE)

        return await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send, status: int, error_code: ErrorCode) -> None:
        body = json.dumps({"detail": {"error_code": error_code.value}}).encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})
