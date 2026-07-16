import os

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from starlette.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware

from services.app.core.config import APP_NAME, APP_DESCRIPTION, APP_VERSION
from services.app.core.security.limiter.rate_limit import (
    limiter,
    RateLimitExceeded,
    _rate_limit_exceeded_handler,
)
from services.app.core.database import Base, _connector
from services.app.api_router import api_router


def create_app() -> FastAPI:
    app = FastAPI(
        title=APP_NAME,
        description=APP_DESCRIPTION,
        version=APP_VERSION,
        docs_url=None,
        redoc_url=None,
    )

    allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:4173").split(",")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in allowed_origins],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    @app.get("/", include_in_schema=False)
    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui():
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{APP_NAME} — Swagger UI",
        )

    @app.get("/health", tags=["System"])
    def health():
        return {
            "status": "ok",
            "database": "reachable" if _connector.ping() else "unreachable",
        }

    app.include_router(api_router)

    return app


app = create_app()


@app.on_event("startup")
def on_startup() -> None:
    # Szkielet: przy sqlite tworzymy tabele automatycznie.
    # Na Postgresie schemat zarządzany przez database/sql — wyłącz przez DB_CREATE_TABLES=false.
    if os.getenv("DB_CREATE_TABLES", "true").lower() == "true":
        from services.app.users.models import User  # noqa: F401 — rejestruje model w Base.metadata
        Base.metadata.create_all(bind=_connector.get_engine())
