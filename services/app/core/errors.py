"""Błędy API — zawsze kody, nigdy teksty.

API zwraca {"detail": {"error_code": "...", "details": {...}?}}.
Tłumaczenie kodu na komunikat w języku usera to zadanie frontendu (i18n).
Kod raz opublikowany jest wieczny — zmiana brzmienia komunikatu nie dotyka API.
"""

import logging
from enum import Enum

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorCode(str, Enum):
    """Wszystkie kody błędów API w jednym miejscu — kontrakt z frontendem."""

    # ── Auth ──────────────────────────────────────────────────────────
    # Te wartości są publicznymi kodami kontraktu API, a nie sekretami.
    INVALID_TOKEN = "invalid_token"  # nosec B105
    TOKEN_EXPIRED = "token_expired"  # nosec B105
    TOKEN_REVOKED = "token_revoked"  # nosec B105
    AUTH_PROVIDER_UNAVAILABLE = "auth_provider_unavailable"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    ADMIN_REQUIRED = "admin_required"
    ADMIN_API_KEY_NOT_CONFIGURED = "admin_api_key_not_configured"
    INVALID_ADMIN_API_KEY = "invalid_admin_api_key"

    # ── Users ─────────────────────────────────────────────────────────
    USER_NOT_FOUND = "user_not_found"
    USER_INACTIVE = "user_inactive"
    TAG_TAKEN = "tag_taken"
    CANNOT_EDIT_OTHER_USER = "cannot_edit_other_user"
    DISPLAY_NAME_TOO_LONG = "display_name_too_long"
    CITY_REQUIRED = "city_required"

    # ── Games / BGG ──────────────────────────────────────────────────
    GAME_NOT_FOUND = "game_not_found"
    BGG_NOT_CONFIGURED = "bgg_not_configured"
    BGG_UNAVAILABLE = "bgg_unavailable"
    BGG_RATE_LIMITED = "bgg_rate_limited"
    COLLECTION_IMPORT_FAILED = "collection_import_failed"
    INVALID_BGG_USERNAME = "invalid_bgg_username"
    BARCODE_NOT_FOUND = "barcode_not_found"
    GAME_BARCODE_EXISTS = "game_barcode_exists"
    GAME_ALREADY_HAS_BARCODE = "game_already_has_barcode"
    INVALID_BARCODE_FORMAT = "invalid_barcode_format"
    BARCODE_PROPOSAL_PENDING = "barcode_proposal_pending"
    BARCODE_PROPOSAL_NOT_FOUND = "barcode_proposal_not_found"
    BARCODE_NOT_PENDING = "barcode_not_pending"
    GAME_TITLE_EXISTS = "game_title_exists"
    CANNOT_EDIT_BGG_GAME = "cannot_edit_bgg_game"
    NOT_GAME_OWNER = "not_game_owner"
    INVALID_GAME_TYPES = "invalid_game_types"
    INVALID_PLAYER_RANGE = "invalid_player_range"
    INVALID_IMPORT_FILE = "invalid_import_file"
    INVALID_CSV_FORMAT = "invalid_csv_format"
    CSV_TOO_LARGE = "csv_too_large"
    IMPORT_ALREADY_RUNNING = "import_already_running"
    CATALOG_IMPORT_FAILED = "catalog_import_failed"
    IMPORT_NOT_CONFIGURED = "import_not_configured"
    INVALID_IMPORT_KEY = "invalid_import_key"

    # ── Shelf ─────────────────────────────────────────────────────────
    GAME_ALREADY_ON_SHELF = "game_already_on_shelf"
    GAME_NOT_ON_SHELF = "game_not_on_shelf"
    COLLECTION_IMPORT_TIMEOUT = "collection_import_timeout"
    INVALID_CONDITION = "invalid_condition"
    RATINGS_NOT_AVAILABLE = "ratings_not_available"

    # Ratings / reviews
    ALREADY_RATED = "already_rated"
    NOT_RATED_YET = "not_rated_yet"
    INVALID_RATING_VALUE = "invalid_rating_value"
    REVIEW_TOO_SHORT = "review_too_short"
    REVIEW_ALREADY_REPORTED = "review_already_reported"
    CANNOT_REPORT_OWN_REVIEW = "cannot_report_own_review"
    RATING_HIDDEN = "rating_hidden"
    RATING_NOT_FOUND = "rating_not_found"

    # ── Pliki / upload ────────────────────────────────────────────────
    FILE_TOO_LARGE = "file_too_large"
    INVALID_FILE_TYPE = "invalid_file_type"
    AVATAR_UPLOAD_FAILED = "avatar_upload_failed"
    COVER_UPLOAD_FAILED = "cover_upload_failed"
    GALLERY_LIMIT_REACHED = "gallery_limit_reached"
    IMAGE_NOT_FOUND = "image_not_found"
    IMAGE_UPLOAD_FAILED = "image_upload_failed"
    MODEL_GENERATION_FAILED = "model_generation_failed"
    MODEL_ALREADY_PROCESSING = "model_already_processing"
    MODEL_NOT_FOUND = "model_not_found"
    MODEL_NOT_READY_FOR_REVIEW = "model_not_ready_for_review"
    ALL_SIDES_REQUIRED = "all_sides_required"
    MEDIA_NOT_PENDING = "media_not_pending"
    CONTRIBUTIONS_LOCKED = "contributions_locked"

    # ── Rate limiting ─────────────────────────────────────────────────
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    RATE_LIMIT_BACKEND_UNAVAILABLE = "rate_limit_backend_unavailable"

    # ── Ogólne ────────────────────────────────────────────────────────
    VALIDATION_ERROR = "validation_error"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    LENGTH_REQUIRED = "length_required"
    INTERNAL_ERROR = "internal_error"
    ROUTE_NOT_FOUND = "route_not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"


class ApiError(HTTPException):
    """HTTPException z ustrukturyzowanym ciałem {error_code, details?}.

    Zawsze używaj tego zamiast HTTPException — dzięki temu odpowiedzi API
    mają jednolity kształt, a frontend tłumaczy kody na komunikaty.
    """

    def __init__(
        self,
        status_code: int,
        error_code: ErrorCode,
        details: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        detail: dict = {"error_code": error_code.value}
        if details:
            detail["details"] = details
        super().__init__(status_code=status_code, detail=detail, headers=headers)

    # ── Skróty na najczęstsze przypadki ──────────────────────────────

    @classmethod
    def unauthorized(cls, error_code: ErrorCode = ErrorCode.UNAUTHORIZED) -> "ApiError":
        # WWW-Authenticate jest wymagane przy 401 (RFC 9110) i podpowiada
        # klientowi, jakiego schematu auth oczekujemy.
        return cls(401, error_code, headers={"WWW-Authenticate": "Bearer"})

    @classmethod
    def forbidden(cls, error_code: ErrorCode = ErrorCode.FORBIDDEN) -> "ApiError":
        return cls(403, error_code)

    @classmethod
    def not_found(cls, error_code: ErrorCode) -> "ApiError":
        return cls(404, error_code)

    @classmethod
    def conflict(cls, error_code: ErrorCode, details: dict | None = None) -> "ApiError":
        return cls(409, error_code, details)

    @classmethod
    def bad_request(cls, error_code: ErrorCode, details: dict | None = None) -> "ApiError":
        return cls(400, error_code, details)

    @classmethod
    def too_many_requests(cls, retry_after: int | None = None) -> "ApiError":
        headers = {"Retry-After": str(retry_after)} if retry_after else None
        details = {"retry_after": retry_after} if retry_after else None
        return cls(429, ErrorCode.RATE_LIMIT_EXCEEDED, details=details, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    """Nieobsłużone wyjątki też mówią kontraktem: 500 {"error_code": "internal_error"}.

    Traceback ląduje TYLKO w logach — nigdy w odpowiedzi. Wołane w create_app().
    """

    async def _internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Nieobsłużony wyjątek w %s %s", request.method, request.url.path, exc_info=exc
        )
        return JSONResponse(
            status_code=500,
            content={"detail": {"error_code": ErrorCode.INTERNAL_ERROR.value}},
        )

    async def _validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = []
        for issue in exc.errors():
            location = [str(part) for part in issue.get("loc", ()) if part != "body"]
            errors.append(
                {
                    "field": ".".join(location) or "request",
                    "rule": str(issue.get("type", "validation_error")),
                }
            )
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "error_code": ErrorCode.VALIDATION_ERROR.value,
                    "details": {"errors": errors},
                }
            },
        )

    async def _http_error_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error_code" in exc.detail:
            detail = exc.detail
        else:
            code_by_status = {
                400: ErrorCode.VALIDATION_ERROR,
                401: ErrorCode.UNAUTHORIZED,
                403: ErrorCode.FORBIDDEN,
                404: ErrorCode.ROUTE_NOT_FOUND,
                405: ErrorCode.METHOD_NOT_ALLOWED,
                413: ErrorCode.PAYLOAD_TOO_LARGE,
                422: ErrorCode.VALIDATION_ERROR,
                429: ErrorCode.RATE_LIMIT_EXCEEDED,
            }
            fallback = (
                ErrorCode.INTERNAL_ERROR if exc.status_code >= 500 else ErrorCode.VALIDATION_ERROR
            )
            detail = {"error_code": code_by_status.get(exc.status_code, fallback).value}
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": detail},
            headers=exc.headers,
        )

    # Starlette types handlers contravariantly as Exception, while runtime dispatch
    # intentionally provides the concrete registered exception class.
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _internal_error_handler)
