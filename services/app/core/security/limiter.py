"""Rate limiting — cała konfiguracja w JEDNYM miejscu.

Użycie w endpointach (dekorator NAD funkcją, POD dekoratorem routera).
UWAGA: slowapi wymaga w sygnaturze endpointu OBU parametrów `request: Request`
i `response: Response` (do wstrzyknięcia nagłówków X-RateLimit-*) — bez
`response` endpoint wywala 500 przy headers_enabled=True:

    from services.app.core.security.limiter import limiter, WRITE_LIMIT

    @router.put("/me")
    @limiter.limit(WRITE_LIMIT)
    def update_me(request: Request, response: Response, ...): ...

Rejestracja w aplikacji: register_rate_limiting(app) w create_app() (server.py).
"""

from typing import cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from services.app.core.config import settings
from services.app.core.errors import ErrorCode

# ── Nazwane limity — importuj i nakładaj dekoratorem ─────────────────────────
# KAŻDY endpoint /api MUSI dostać dekorator. Nie ma globalnej siatki
# bezpieczeństwa: SlowAPIMiddleware (default_limits) nie widzi endpointów
# w FastAPI ≥0.139 (nowy routing `_IncludedRouter`) — sprawdzone empirycznie,
# limit z middleware po prostu nie działał. Egzekwują wyłącznie dekoratory.

READ_LIMIT = "60/minute"  # odczyty (GET)
BGG_SEARCH_LIMIT = "10/minute"  # publiczny endpoint może wywołać zewnętrzne BGG
BGG_FETCH_LIMIT = "30/hour"  # klik wyniku może odświeżyć zewnętrzne BGG
WRITE_LIMIT = "20/minute"  # zapisy (PUT/POST)
UPLOAD_LIMIT = "5/minute"  # upload plików (CPU na optymalizację + transfer)
DELETE_LIMIT = "5/hour"  # operacje destrukcyjne (DELETE /me)
CUSTOM_GAME_LIMIT = "5/hour"  # community content / ochrona przed spamem
CATALOG_IMPORT_LIMIT = "20/day"  # ciężki, operatorski import pełnego dumpa CSV
GALLERY_UPLOAD_LIMIT = "10/hour"  # zdjęcia wnętrza customowej gry
MODEL_UPLOAD_LIMIT = "3/hour"  # sześć tekstur + generowanie GLB
MODERATION_LIMIT = "60/minute"  # chronione operacje administratora
COLLECTION_IMPORT_LIMIT = "2/hour"  # BGG collection: kosztowne requesty batch
RATING_WRITE_LIMIT = "20/hour"  # ochrona przed masowym ocenianiem
REVIEW_REPORT_LIMIT = "10/hour"  # ochrona przed masowym zgłaszaniem


def _key_func(request: Request) -> str:
    """Zalogowany user liczony per konto (firebase_uid ze state, ustawia go
    get_current_user), anonim per IP. Dzięki temu limit nie łapie wszystkich
    userów za wspólnym NAT-em naraz."""
    firebase_uid = getattr(request.state, "firebase_uid", None)
    if firebase_uid:
        return f"user:{firebase_uid}"
    return get_remote_address(request)


limiter = Limiter(
    key_func=_key_func,
    storage_uri=settings.RATE_LIMIT_STORAGE_URI,
    headers_enabled=True,  # X-RateLimit-* + Retry-After w odpowiedziach
)


def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    # 429 też mówi kodem, nie tekstem — spójnie z core/errors.ApiError.
    response = JSONResponse(
        status_code=429,
        content={"detail": {"error_code": ErrorCode.RATE_LIMIT_EXCEEDED.value}},
    )
    # dokłada Retry-After i X-RateLimit-* wyliczone dla przekroczonego limitu
    return cast(
        JSONResponse,
        request.app.state.limiter._inject_headers(response, request.state.view_rate_limit),
    )


def register_rate_limiting(app: FastAPI) -> None:
    """Podpina limiter pod aplikację — wołane raz w create_app().

    Dekoratory potrzebują tylko app.state.limiter + handlera 429;
    middleware slowapi celowo NIE jest używany (patrz komentarz wyżej).
    """
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)  # type: ignore[arg-type]
