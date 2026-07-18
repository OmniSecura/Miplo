"""Minimalny, bezsekretowy dziennik operacji administratorskich."""

import logging

logger = logging.getLogger("miplo.audit")


class AdminAuditLogMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/admin/"):
            await self.app(scope, receive, send)
            return

        status_code = 500

        async def capture_status(message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            state = scope.get("state") or {}
            actor = state.get("admin_actor", "unauthenticated")
            client = scope.get("client")
            client_ip = client[0] if client else "unknown"
            logger.info(
                "admin_action actor=%s method=%s path=%s status=%d ip=%s",
                actor,
                scope.get("method", ""),
                scope.get("path", ""),
                status_code,
                client_ip,
            )
