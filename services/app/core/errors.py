"""Błędy API — zawsze kody, nigdy teksty.

API zwraca {"detail": {"error_code": "...", "details": {...}?}}.
Tłumaczenie kodu na komunikat w języku usera to zadanie frontendu (i18n).
Kod raz opublikowany jest wieczny — zmiana brzmienia komunikatu nie dotyka API.
"""

from enum import Enum

from fastapi import HTTPException


class ErrorCode(str, Enum):
    """Wszystkie kody błędów API w jednym miejscu — kontrakt z frontendem."""

    # ── Auth ──────────────────────────────────────────────────────────
    INVALID_TOKEN = "invalid_token"
    TOKEN_EXPIRED = "token_expired"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"

    # ── Users ─────────────────────────────────────────────────────────
    USER_NOT_FOUND = "user_not_found"
    USER_INACTIVE = "user_inactive"
    TAG_TAKEN = "tag_taken"
    CANNOT_EDIT_OTHER_USER = "cannot_edit_other_user"
    DISPLAY_NAME_TOO_LONG = "display_name_too_long"
    CITY_REQUIRED = "city_required"

    # ── Rate limiting ─────────────────────────────────────────────────
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"

    # ── Ogólne ────────────────────────────────────────────────────────
    VALIDATION_ERROR = "validation_error"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    LENGTH_REQUIRED = "length_required"
    INTERNAL_ERROR = "internal_error"


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
