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

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Metadane aplikacji — stałe, nie konfiguracja środowiska ──────────────────

APP_NAME = "Miplo"
APP_DESCRIPTION = "Board game shelf & community app - 3D collection, local player matchmaking, and game lending."
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

    # dev: pamięć procesu; prod: redis://... (wspólny licznik dla wielu instancji)
    RATE_LIMIT_STORAGE_URI: str = "memory://"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _require_db_config_for_env(self) -> "Settings":
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
        return self


settings = Settings()
