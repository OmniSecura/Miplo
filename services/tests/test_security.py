"""Regresje dla zabezpieczeń działających przed i wokół routerów."""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch

if "services.app.core.database" not in sys.modules:
    os.environ["ENV"] = "local"
    os.environ["SQLITE_PATH"] = os.path.join(tempfile.gettempdir(), "miplo-security-tests.db")
    os.environ.setdefault("FIREBASE_ADMIN_CREDENTIALS", "unused-in-unit-tests.json")
    os.environ.setdefault("FIREBASE_STORAGE_BUCKET", "unused-in-unit-tests")

from fastapi import Depends, FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from firebase_admin import auth as firebase_auth
from firebase_admin import exceptions as firebase_exceptions
from pydantic import ValidationError
from starlette.requests import Request

from services.app.core import auth
from services.app.core.config import Settings, settings
from services.app.core.errors import ApiError, ErrorCode, register_error_handlers
from services.app.core.security.global_limiter import GlobalIpRateLimitMiddleware
from services.app.core.security.headers import SecurityHeadersMiddleware
from services.app.users.models import User
from services.app.users.routers import router as users_router_module


class SecurityRegressionTests(unittest.TestCase):
    @staticmethod
    def _request() -> Request:
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/me",
                "headers": [],
                "client": ("127.0.0.1", 1234),
                "server": ("testserver", 80),
                "scheme": "http",
                "query_string": b"",
            }
        )

    def test_firebase_token_is_checked_for_revocation(self) -> None:
        user = User(firebase_uid="uid-1", tag="secure_user", is_active=True)
        bearer = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
        db = MagicMock()
        with (
            patch.object(
                auth.firebase_auth, "verify_id_token", return_value={"uid": "uid-1"}
            ) as verify,
            patch.object(auth.user_service, "get_by_firebase_uid", return_value=user),
        ):
            result = auth.get_current_user_allow_inactive(self._request(), bearer, db)
        self.assertIs(result, user)
        verify.assert_called_once_with("token", check_revoked=True)

    def test_revoked_firebase_token_has_stable_error_code(self) -> None:
        bearer = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
        with patch.object(
            auth.firebase_auth,
            "verify_id_token",
            side_effect=firebase_auth.RevokedIdTokenError("revoked"),
        ):
            with self.assertRaises(ApiError) as context:
                auth.get_current_user_allow_inactive(self._request(), bearer, MagicMock())
        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(context.exception.detail["error_code"], ErrorCode.TOKEN_REVOKED.value)

    def test_account_deletion_orders_firebase_and_database_safely(self) -> None:
        user = User(firebase_uid="uid-delete", tag="delete_user", is_active=True)
        db = MagicMock()
        parent = MagicMock()
        with (
            patch.object(users_router_module, "prepare_firebase_account_deletion", parent.prepare),
            patch.object(users_router_module.user_service, "delete_account", parent.delete_local),
            patch.object(
                users_router_module, "finalize_firebase_account_deletion", parent.finalize
            ),
        ):
            users_router_module.delete_my_account.__wrapped__(None, None, user, db)
        self.assertEqual(
            parent.mock_calls,
            [call.prepare("uid-delete"), call.delete_local(db, user), call.finalize("uid-delete")],
        )

    def test_failed_local_delete_reenables_firebase_account(self) -> None:
        user = User(firebase_uid="uid-delete", tag="delete_user", is_active=True)
        with (
            patch.object(users_router_module, "prepare_firebase_account_deletion"),
            patch.object(
                users_router_module.user_service, "delete_account", side_effect=RuntimeError
            ),
            patch.object(
                users_router_module, "restore_firebase_account_after_failed_deletion"
            ) as restore,
            patch.object(users_router_module, "finalize_firebase_account_deletion") as finalize,
        ):
            with self.assertRaises(RuntimeError):
                users_router_module.delete_my_account.__wrapped__(
                    None,
                    None,
                    user,
                    MagicMock(),
                )
        restore.assert_called_once_with("uid-delete")
        finalize.assert_not_called()

    def test_failed_token_revocation_rolls_back_firebase_disable(self) -> None:
        with (
            patch.object(auth.firebase_auth, "update_user") as update,
            patch.object(
                auth.firebase_auth,
                "revoke_refresh_tokens",
                side_effect=firebase_exceptions.UnavailableError("firebase down"),
            ),
        ):
            with self.assertRaises(ApiError) as context:
                auth.prepare_firebase_account_deletion("uid-delete")
        self.assertEqual(context.exception.status_code, 503)
        self.assertEqual(
            update.call_args_list,
            [call("uid-delete", disabled=True), call("uid-delete", disabled=False)],
        )

    def test_global_ip_limit_counts_requests_rejected_by_dependency(self) -> None:
        previous = settings.GLOBAL_IP_RATE_LIMIT
        settings.GLOBAL_IP_RATE_LIMIT = "2/minute"
        try:
            app = FastAPI()
            register_error_handlers(app)
            app.add_middleware(GlobalIpRateLimitMiddleware)

            def reject() -> None:
                raise ApiError.unauthorized()

            @app.get("/protected")
            def protected(_dependency=Depends(reject)) -> None:
                return None

            client = TestClient(app, raise_server_exceptions=False)
            try:
                statuses = [client.get("/protected").status_code for _ in range(3)]
            finally:
                client.close()
        finally:
            settings.GLOBAL_IP_RATE_LIMIT = previous
        self.assertEqual(statuses, [401, 401, 429])

    def test_production_rejects_process_local_rate_limit_storage(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                ENV="prod",
                DATABASE_URL="postgresql+psycopg://user:password@db:5432/miplo",
                FIREBASE_ADMIN_CREDENTIALS="/secret/firebase.json",
                FIREBASE_STORAGE_BUCKET="miplo.firebasestorage.app",
                RATE_LIMIT_STORAGE_URI="memory://",
                ALLOWED_HOSTS="api.miplo.app",
                ALLOWED_ORIGINS="https://miplo.app",
            )

    def test_private_response_gets_no_store_and_security_headers(self) -> None:
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/api/me")
        def private() -> dict:
            return {"ok": True}

        client = TestClient(app)
        try:
            response = client.get(
                "/api/me",
                headers={"Authorization": "Bearer test"},
            )
        finally:
            client.close()
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")


if __name__ == "__main__":
    unittest.main()
