"""Idempotentna migracja lokalnego SQLite do modułu ratings.

Przed pierwszą zmianą tworzy odzyskiwalną kopię przez sqlite3.backup().
Nie modyfikuje ani nie usuwa istniejących gier, userów i półek.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, event

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.app.core.database import Base
from services.app.games.models import Game  # noqa: F401
from services.app.ratings.models import GameRating, ReviewReport
from services.app.shelf.models import ShelfItem  # noqa: F401
from services.app.users.models import User  # noqa: F401

_GAME_COLUMNS = {
    "miplo_rating": "NUMERIC(3, 1)",
    "miplo_ratings_count": "INTEGER NOT NULL DEFAULT 0",
    "miplo_reviews_count": "INTEGER NOT NULL DEFAULT 0",
}


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}


def _backup(connection: sqlite3.Connection, database_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = database_path.with_name(f"{database_path.name}.backup-ratings-{timestamp}")
    with sqlite3.connect(backup_path) as destination:
        connection.backup(destination)
    return backup_path


def migrate(database_path: Path) -> tuple[bool, Path | None]:
    database_path = database_path.resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"Nie znaleziono bazy SQLite: {database_path}")

    connection = sqlite3.connect(database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if "games" not in tables or "users" not in tables:
            raise RuntimeError("Baza nie zawiera wymaganych tabel games i users")
        missing_columns = set(_GAME_COLUMNS) - _columns(connection, "games")
        missing_tables = {"game_ratings", "review_reports"} - tables
        if not missing_columns and not missing_tables:
            return False, None

        backup_path = _backup(connection, database_path)
        for column in sorted(missing_columns):
            connection.execute(f'ALTER TABLE games ADD COLUMN "{column}" {_GAME_COLUMNS[column]}')
        connection.commit()
    finally:
        connection.close()

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    try:
        Base.metadata.create_all(
            engine,
            tables=[GameRating.__table__, ReviewReport.__table__],
            checkfirst=True,
        )
        with engine.connect() as check:
            violations = check.exec_driver_sql("PRAGMA foreign_key_check").all()
            if violations:
                raise RuntimeError(f"Naruszenia kluczy obcych: {violations[:5]}")
    finally:
        engine.dispose()
    return True, backup_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", nargs="?", default="local.db", type=Path)
    args = parser.parse_args()
    changed, backup = migrate(args.database)
    if changed:
        print(f"Migracja ratings zakończona. Kopia: {backup}")
    else:
        print("Schemat ratings jest już aktualny; bez zmian.")


if __name__ == "__main__":
    main()
