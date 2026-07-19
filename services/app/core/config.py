"""Konfiguracja aplikacji — jedyne źródło ustawień.

Sekrety i parametry środowiska przychodzą wyłącznie z env / pliku .env
(na produkcji: GCP Secret Manager → zmienne środowiskowe). Nigdy z kodu.

ENV steruje wyborem bazy (szczegóły w core/database.py):
    local → SQLite, plik tworzy się sam przy starcie (zero konfiguracji)
    dev   → PostgreSQL, URL składany z części POSTGRES_*
    prod  → PostgreSQL, gotowy DATABASE_URL w całości (z Secret Managera)
"""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Metadane aplikacji — stałe, nie konfiguracja środowiska ──────────────────

APP_NAME = "Miplo"
APP_DESCRIPTION = (
    "Board game shelf & community app - 3D collection, local player matchmaking, and game lending."
)
APP_VERSION = "0.0.1"
APP_AUTHORS = "Bartosz Malujda"

# .env leży w services/ — ścieżka liczona od tego pliku, żeby działało
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Ustawienia z env/.env, walidowane przy starcie.

    Walidator na dole pilnuje kompletu zmiennych dla wybranego ENV —
    brak czegoś wywala proces na imporcie z czytelnym błędem, zamiast
    tajemniczego wyjątku dopiero przy pierwszym requeście.
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",  # .env może trzymać też zmienne innych narzędzi (BGG, Redis)
    )

    ENV: Literal["local", "dev", "prod"] = "local"

    # ── Baza per środowisko ───────────────────────────────────────────────────

    # ENV=local → SQLite
    SQLITE_PATH: str = "local.db"

    # ENV=dev → URL składany z części
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "miplo"
    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: str | None = None

    # ENV=prod → pełny URL w całości; wymuszamy sterownik psycopg3
    DATABASE_URL: str | None = Field(default=None, pattern=r"^postgresql\+psycopg://")

    DB_ECHO: bool = False

    # ── Firebase ──────────────────────────────────────────────────────────────

    # Ścieżka do klucza admina (sam plik NIGDY nie trafia do repo)
    FIREBASE_ADMIN_CREDENTIALS: str

    # Nazwa bucketa Firebase Storage (sama nazwa, bez prefiksu gs://)
    FIREBASE_STORAGE_BUCKET: str

    # ── HTTP ──────────────────────────────────────────────────────────────────

    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:4173"
    ALLOWED_HOSTS: str = "localhost,127.0.0.1,testserver"

    # dev: pamięć procesu; prod: redis://... (wspólny licznik dla wielu instancji)
    RATE_LIMIT_STORAGE_URI: str = "memory://"
    GLOBAL_IP_RATE_LIMIT: str = Field(
        default="120/minute",
        pattern=r"^[1-9][0-9]*/(second|minute|hour)$",
    )

    # ── BGG API ──────────────────────────────────────────────────────────────
    BGG_API_BASE: str = Field(
        default="https://boardgamegeek.com/xmlapi2",
        pattern=r"^https://[^\s]+$",
        max_length=300,
    )
    BGG_API_TOKEN: str | None = None
    # Szczegóły z /thing są prawie statyczne. Rankingi i liczby głosów
    # aktualizuje tygodniowy dump CSV, więc API nie musi odświeżać ich codziennie.
    BGG_CACHE_TTL_SECONDS: int = Field(default=2_592_000, ge=3600, le=31_536_000)
    BGG_MAX_CONCURRENT: int = Field(default=2, ge=1, le=5)
    BGG_MIN_REQUEST_INTERVAL: float = Field(default=5.0, ge=0.1, le=60.0)
    BGG_REFRESH_COOLDOWN: int = Field(default=60, ge=10, le=3600)
    BGG_MAX_PENDING_REFRESHES: int = Field(default=32, ge=1, le=500)

    # Cloud Run Job / ręcznie uruchamiany nightly sync.
    NIGHTLY_SYNC_BUDGET: int = Field(default=1800, ge=60, le=21_600)
    NIGHTLY_SYNC_LEVEL1_LIMIT: int = Field(default=200, ge=1, le=10_000)
    NIGHTLY_SYNC_LEVEL2_LIMIT: int = Field(default=100, ge=1, le=10_000)

    # Generowanie GLB pozostaje wewnątrz requestu (Cloud Run przydziela wtedy CPU),
    # z jawną granicą równoległości i czasu wykonania.
    MODEL_GENERATION_CONCURRENCY: int = Field(default=1, ge=1, le=4)
    MODEL_GENERATION_TIMEOUT_SECONDS: int = Field(default=90, ge=15, le=300)

    # Uniwersalny sekret operatorski dla endpointów /api/admin/*.
    # Jest alternatywą dla konta Firebase z is_admin=True, nigdy kluczem klienta.
    ADMIN_API_KEY: str | None = Field(default=None, min_length=32, max_length=256)

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()]

    @model_validator(mode="after")
    def _require_db_config_for_env(self) -> "Settings":
        bgg_url = urlsplit(self.BGG_API_BASE)
        if (
            bgg_url.scheme != "https"
            or (bgg_url.hostname or "").lower()
            not in {"boardgamegeek.com", "www.boardgamegeek.com"}
            or bgg_url.username
            or bgg_url.password
            or bgg_url.query
            or bgg_url.fragment
        ):
            raise ValueError("BGG_API_BASE musi wskazywać oficjalny host boardgamegeek.com")
        if self.ENV == "dev":
            missing = [
                name
                for name in ("POSTGRES_USER", "POSTGRES_PASSWORD")
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(f"ENV=dev wymaga zmiennych: {', '.join(missing)}")
        if self.ENV == "prod" and self.DATABASE_URL is None:
            raise ValueError("ENV=prod wymaga zmiennej DATABASE_URL")
        if self.ENV == "prod":
            if not self.RATE_LIMIT_STORAGE_URI.startswith(("redis://", "rediss://")):
                raise ValueError(
                    "ENV=prod wymaga współdzielonego RATE_LIMIT_STORAGE_URI redis:// lub rediss://"
                )
            if "*" in self.allowed_origins_list:
                raise ValueError("ENV=prod nie pozwala na wildcard w ALLOWED_ORIGINS")
            if not self.allowed_hosts_list or "*" in self.allowed_hosts_list:
                raise ValueError("ENV=prod wymaga jawnej listy ALLOWED_HOSTS")
        return self


settings = Settings()  # type: ignore[call-arg]  # values come from env/.env
