"""Warstwa bazy danych — URL budowany według settings.ENV.

    local → SQLite (plik; tabele tworzą się same przy starcie — bez migracji)
    dev   → PostgreSQL, URL składany z części POSTGRES_* (psycopg3)
    prod  → PostgreSQL, gotowy DATABASE_URL (GCP Secret Manager)

Produkcyjną bazą jest wyłącznie PostgreSQL (decyzja 0003) — SQLite to
wygoda lokalnego developmentu, nie wspierany backend.

create_engine nie otwiera połączenia — pierwsze połączenie leci przy pierwszym
zapytaniu, więc import modułu nie wymaga działającej bazy.
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from services.app.core.config import settings


class Base(DeclarativeBase):
    """Wspólna baza deklaratywna — wszystkie modele ORM dziedziczą stąd."""


def _build_url() -> URL | str:
    if settings.ENV == "local":
        return f"sqlite:///{settings.SQLITE_PATH}"

    if settings.ENV == "dev":
        return URL.create(
            drivername="postgresql+psycopg",
            username=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            database=settings.POSTGRES_DB,
        )

    # prod — URL w całości z Secret Managera (komplet pilnowany w config.py)
    return settings.DATABASE_URL


_is_sqlite = settings.ENV == "local"

engine = create_engine(
    _build_url(),
    # Weryfikuj, że połączenie żyje, zanim pula je wyda (Cloud SQL ucina bezczynne).
    pool_pre_ping=True,
    echo=settings.DB_ECHO,
    **(
        # SQLite: lokalny plik — bez tuningu puli; check_same_thread=False,
        # bo FastAPI obsługuje sync endpointy w puli wątków.
        {"connect_args": {"check_same_thread": False}}
        if _is_sqlite
        # PostgreSQL: mała stała pula + zapas na skoki ruchu; odświeżanie
        # połączeń starszych niż 1h unika martwych TCP po stronie proxy.
        else {"pool_size": 5, "max_overflow": 10, "pool_recycle": 3600}
    ),
)


if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        """SQLite domyślnie ignoruje FK; local ma zachowywać CASCADE jak Postgres."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def create_all_for_local() -> None:
    """ENV=local: tabele tworzą się same przy starcie (wołane z lifespanu).

    Na dev/prod schemat jest zarządzany przez database/sql (docelowo Alembic) —
    tam ta funkcja świadomie nic nie robi.
    """
    if settings.ENV != "local":
        return
    from services.app.users import models  # noqa: F401 — rejestruje modele w Base.metadata
    from services.app.games import models as _game_models  # noqa: F401
    from services.app.shelf import models as _shelf_models  # noqa: F401
    from services.app.ratings import models as _rating_models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: sesja per request.

    Celowo NIE commituje — commit należy do warstwy service, żeby transakcja
    kończyła się dokładnie tam, gdzie kończy się operacja domenowa.
    """
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Do użytku poza FastAPI (skrypty, workery). Te same zasady co get_db:
    commit robisz jawnie (najlepiej przez warstwę service)."""
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping() -> bool:
    """True, jeśli baza odpowiada — używane przez /health."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
