"""Jednolite nagłówki bezpieczeństwa i blokada cache dla danych prywatnych."""

from services.app.core.config import settings


class SecurityHeadersMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        headers_in = {k.lower(): v for k, v in scope.get("headers", [])}
        private_response = (
            b"authorization" in headers_in
            or path.startswith("/api/me")
            or path.startswith("/api/admin")
        )

        async def send_with_headers(message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    ]
                )
                if private_response:
                    headers.append((b"cache-control", b"no-store"))
                if settings.ENV == "prod":
                    headers.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
