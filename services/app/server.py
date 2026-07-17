from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.openapi.docs import get_swagger_ui_html
from starlette.middleware.cors import CORSMiddleware

from services.app.api_router import api_router
from services.app.core.auth import init_firebase
from services.app.core.config import APP_DESCRIPTION, APP_NAME, APP_VERSION, settings
from services.app.core.database import create_all_for_local, ping
from services.app.core.security.body_limit import BodySizeLimitMiddleware
from services.app.core.security.limiter import READ_LIMIT, limiter, register_rate_limiting


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail-fast: brak/zły klucz Firebase wywala start serwera, nie pierwszy request.
    init_firebase()
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
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    register_rate_limiting(app)

    # Ostatni add_middleware = najbardziej zewnętrzna warstwa: limit wielkości
    # body tnie za duże requesty zanim cokolwiek innego je dotknie.
    app.add_middleware(BodySizeLimitMiddleware)

    @app.get("/", include_in_schema=False)
    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui():
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{APP_NAME} — Swagger UI",
        )

    # Jedyny endpoint bez auth, a dotyka bazy — limit per IP, żeby flood
    # nie wysycał puli połączeń.
    @app.get("/health", tags=["system"])
    @limiter.limit(READ_LIMIT)
    def health(request: Request, response: Response):
        return {
            "status": "ok",
            "database": "reachable" if ping() else "unreachable",
        }

    app.include_router(api_router)

    return app


app = create_app()
