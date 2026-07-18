"""Limit wielkości ciała requestu — obrona przed zapychaniem RAM-u.

Pydantic waliduje długości pól dopiero PO sparsowaniu całego JSON-a, więc bez
tego middleware'a 100 MB payload najpierw ląduje w pamięci, a dopiero potem
dostaje 422. Tutaj ucinamy na progu:

- body z Content-Length ponad limit → 413 payload_too_large,
- body bez Content-Length (chunked) → 411 length_required; uczciwe klienty
  zawsze deklarują długość, a h11 egzekwuje ramkowanie, więc zaniżyć się nie da.

Standardowe progi to 64 KB dla JSON i 3 MB dla multipart (2 MB obrazu oraz
narzut formularza). Wyłącznie dokładna ścieżka operatorska
`/api/admin/games/import` ma limit 51 MB, a ścieżki kończące się `/3d-model`
mają 14 MB dla sześciu
obrazów po maksymalnie 2 MB. Spoofing content-type nie podnosi limitu innych
endpointów.

Czysty ASGI (nie BaseHTTPMiddleware) — działa przed routingiem, auth i limiterem,
czyli chroni także requesty nieuwierzytelnione. Rejestracja: server.py.
"""

import json

from services.app.core.errors import ErrorCode

MAX_BODY_SIZE = 64 * 1024
MAX_MULTIPART_BODY_SIZE = 3 * 1024 * 1024
# Plik CSV ma limit 50 MB; dodatkowy 1 MB pokrywa bezpiecznie framing multipart.
MAX_CATALOG_IMPORT_BODY_SIZE = 51 * 1024 * 1024
MAX_MODEL_UPLOAD_BODY_SIZE = 14 * 1024 * 1024

_METHODS_WITH_BODY = {"POST", "PUT", "PATCH"}


class BodySizeLimitMiddleware:
    def __init__(self, app, max_body_size: int = MAX_BODY_SIZE) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope.get("method") not in _METHODS_WITH_BODY:
            return await self.app(scope, receive, send)

        content_length = None
        is_multipart = False
        for name, value in scope.get("headers") or []:
            if name == b"content-length":
                content_length = value
            elif name == b"content-type" and value.lower().startswith(b"multipart/form-data"):
                is_multipart = True

        if content_length is None:
            # transfer-encoding: chunked albo brak nagłówka — nie da się
            # sprawdzić rozmiaru z góry, więc żądamy jawnej długości
            return await self._reject(send, 411, ErrorCode.LENGTH_REQUIRED)

        try:
            declared = int(content_length)
        except ValueError:
            return await self._reject(send, 411, ErrorCode.LENGTH_REQUIRED)

        # Wyjątek tylko dla operatorskiego importu katalogu. Sprawdzenie dokładnej
        # ścieżki zapobiega podniesieniu limitu dla pozostałych uploadów.
        limit_error = ErrorCode.PAYLOAD_TOO_LARGE
        if is_multipart and scope.get("path") == "/api/admin/games/import":
            limit = MAX_CATALOG_IMPORT_BODY_SIZE
            limit_error = ErrorCode.CSV_TOO_LARGE
        elif (
            is_multipart
            and scope.get("path", "").startswith("/api/games/")
            and scope.get("path", "").endswith("/3d-model")
        ):
            limit = MAX_MODEL_UPLOAD_BODY_SIZE
        else:
            limit = MAX_MULTIPART_BODY_SIZE if is_multipart else self.max_body_size
        if declared > limit:
            return await self._reject(send, 413, limit_error)

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
