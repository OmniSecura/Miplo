"""Wspólne ustawienia pytest — żadnych prawdziwych usług Firebase ani BGG."""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

if "services.app.core.database" not in sys.modules:
    os.environ.setdefault("ENV", "local")
    os.environ.setdefault(
        "SQLITE_PATH",
        os.path.join(tempfile.gettempdir(), "miplo-pytest.db"),
    )
    os.environ.setdefault("FIREBASE_ADMIN_CREDENTIALS", "unused-in-tests.json")
    os.environ.setdefault("FIREBASE_STORAGE_BUCKET", "unused-in-tests")
    os.environ.setdefault("BGG_API_TOKEN", "")

# Import przed kolekcją modułów testowych blokuje ich lokalne fallbacki ENV.
from services.app.core.database import Base, SessionLocal, engine  # noqa: E402
from services.app.games import models as _game_models  # noqa: E402,F401
from services.app.ratings import models as _rating_models  # noqa: E402,F401
from services.app.shelf import models as _shelf_models  # noqa: E402,F401
from services.app.users import models as _user_models  # noqa: E402,F401


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Izolowana baza dla testów funkcyjnych uruchamianych przez pytest."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(engine)
