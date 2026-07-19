"""Awaryjny limit per IP wykonywany przed routingiem i dependencies FastAPI.

SlowAPI nadal nakłada dokładniejsze limity per endpoint/user. Ta warstwa zamyka
lukę, w której żądania odrzucone przez auth lub Pydantic nie dochodziły do
dekoratora SlowAPI i mogły być wysyłane bez ograniczeń.
"""

import logging
import time

from limits import parse
from limits.storage import storage_from_string
from limits.strategies import FixedWindowRateLimiter
from starlette.concurrency import run_in_threadpool

from services.app.core.config import settings
from services.app.core.errors import ErrorCode

logger = logging.getLogger(__name__)


class GlobalIpRateLimitMiddleware:
    """Cienki middleware ASGI; nie ufa nagłówkom X-Forwarded-For klienta."""

    def __init__(self, app) -> None:
        self.app = app
        self._storage = storage_from_string(settings.RATE_LIMIT_STORAGE_URI)
        self._strategy = FixedWindowRateLimiter(self._storage)
        self._limit = parse(settings.GLOBAL_IP_RATE_LIMIT)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        route_scope = scope.get("root_path", "")
        identifier = f"global-ip:{client_ip}:{route_scope}"

        try:
            allowed, reset_at = await run_in_threadpool(self._consume, identifier)
        except Exception:
            logger.exception("Backend globalnego rate limitera jest niedostępny")
            await _send_error(send, 503, ErrorCode.RATE_LIMIT_BACKEND_UNAVAILABLE)
            return

        if not allowed:
            retry_after = max(1, int(reset_at - time.time()))
            await _send_error(
                send,
                429,
                ErrorCode.RATE_LIMIT_EXCEEDED,
                retry_after=retry_after,
            )
            return

        await self.app(scope, receive, send)

    def _consume(self, identifier: str) -> tuple[bool, float]:
        allowed = self._strategy.hit(self._limit, identifier)
        reset_at, _remaining = self._strategy.get_window_stats(self._limit, identifier)
        return allowed, reset_at


async def _send_error(
    send, status_code: int, code: ErrorCode, retry_after: int | None = None
) -> None:
    import json

    body = json.dumps(
        {"detail": {"error_code": code.value}},
        separators=(",", ":"),
    ).encode("utf-8")
    headers = [(b"content-type", b"application/json")]
    if retry_after is not None:
        headers.append((b"retry-after", str(retry_after).encode("ascii")))
    await send({"type": "http.response.start", "status": status_code, "headers": headers})
    await send({"type": "http.response.body", "body": body})
