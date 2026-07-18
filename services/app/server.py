from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.openapi.docs import get_swagger_ui_html
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from services.app.api_router import api_router
from services.app.core.auth import init_firebase
from services.app.core.config import APP_DESCRIPTION, APP_NAME, APP_VERSION, settings
from services.app.core.database import create_all_for_local, ping
from services.app.core.errors import register_error_handlers
from services.app.core.security.body_limit import BodySizeLimitMiddleware
from services.app.core.security.audit_log import AdminAuditLogMiddleware
from services.app.core.security.global_limiter import GlobalIpRateLimitMiddleware
from services.app.core.security.headers import SecurityHeadersMiddleware
from services.app.core.security.limiter import READ_LIMIT, limiter, register_rate_limiting
from services.app.core.storage import init_storage


OPENAPI_TAGS = [
    {"name": "system", "description": "Stan aplikacji i zależności."},
    {"name": "users", "description": "Profil, konto i avatar użytkownika."},
    {
        "name": "ratings",
        "description": "Oceny i recenzje społeczności Miplo, niezależne od BGG.",
    },
    {"name": "games", "description": "Wspólny publiczny katalog gier."},
    {
        "name": "BGG games",
        "description": "Pobieranie oraz operatorski import danych BoardGameGeek.",
    },
    {
        "name": "custom games",
        "description": "Tworzenie i zarządzanie grami dodanymi przez społeczność.",
    },
    {
        "name": "game gallery",
        "description": "Moderowane zdjęcia wnętrza i komponentów gier BGG oraz custom.",
    },
    {
        "name": "3D models",
        "description": "Społecznościowe generowanie teksturowanych modeli pudełek GLB.",
    },
    {
        "name": "shelf",
        "description": "Własna i publiczna półka gier oraz import kolekcji BGG.",
    },
    {
        "name": "moderation",
        "description": "Kolejki oraz decyzje dostępne wyłącznie administratorom.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail-fast: brak/zły klucz Firebase wywala start serwera, nie pierwszy request.
    init_firebase()
    # Storage wymaga zainicjalizowanej appki Firebase — kolejność ma znaczenie.
    init_storage()
    # ENV=local: SQLite + tabele tworzą się same; na dev/prod nic nie robi.
    create_all_for_local()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=APP_NAME,
        description=APP_DESCRIPTION,
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_tags=OPENAPI_TAGS,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Admin-Key", "X-Import-Key"],
        expose_headers=["Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
        allow_credentials=False,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)

    register_rate_limiting(app)
    register_error_handlers(app)

    app.add_middleware(GlobalIpRateLimitMiddleware)
    app.add_middleware(AdminAuditLogMiddleware)

    # Body limit nadal działa przed routingiem/auth i nie buforuje treści.
    app.add_middleware(BodySizeLimitMiddleware)
    # Najbardziej zewnętrzna, żeby także 411/413/429 dostały nagłówki ochronne.
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/", include_in_schema=False)
    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui():
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{APP_NAME} — Swagger UI",
        )

    # Jedyny endpoint bez auth, a dotyka bazy — limit per IP, żeby flood
    # nie wysycał puli połączeń.
    @app.get("/health", tags=["system"], summary="Sprawdź stan backendu")
    @limiter.limit(READ_LIMIT)
    def health(request: Request, response: Response):
        return {
            "status": "ok",
            "database": "reachable" if ping() else "unreachable",
            "attribution": {
                "name": "Powered by BoardGameGeek data",
                "url": "https://boardgamegeek.com",
            },
        }

    app.include_router(api_router)

    return app


app = create_app()
