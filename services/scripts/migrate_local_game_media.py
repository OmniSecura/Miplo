"""Jednorazowa, zachowująca dane migracja lokalnego SQLite dla mediów gier.

Użycie z katalogu repozytorium:
    services/.venv/Scripts/python services/scripts/migrate_local_game_media.py local.db

Skrypt dotyczy wyłącznie SQLite. Przed pierwszą zmianą wykonuje spójną kopię
przez sqlite3.Connection.backup(). Nie usuwa katalogu gier ani profili.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


GAME_COLUMNS = (
    "id",
    "bgg_id",
    "slug",
    "title",
    "description",
    "year_published",
    "min_players",
    "max_players",
    "playing_time",
    "rating",
    "weight",
    "cover_url",
    "cover_candidate_path",
    "instruction_url",
    "bgg_rank",
    "users_rated",
    "is_expansion",
    "box_width",
    "box_height",
    "box_depth",
    "model_3d_url",
    "model_status",
    "model_candidate_path",
    "model_job_id",
    "model_submitted_by_id",
    "model_is_verified",
    "model_submitted_at",
    "source",
    "is_verified",
    "community_contributions_enabled",
    "created_by_id",
    "cached_at",
    "created_at",
    "updated_at",
)


CREATE_GAMES = """
CREATE TABLE games_new (
    id INTEGER NOT NULL PRIMARY KEY,
    bgg_id INTEGER,
    slug VARCHAR(200) NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    year_published SMALLINT,
    min_players SMALLINT,
    max_players SMALLINT,
    playing_time SMALLINT,
    rating NUMERIC(4, 2),
    weight NUMERIC(3, 2),
    cover_url VARCHAR(500),
    cover_candidate_path VARCHAR(500),
    instruction_url VARCHAR(500),
    bgg_rank INTEGER,
    users_rated INTEGER,
    is_expansion BOOLEAN NOT NULL DEFAULT 0,
    box_width NUMERIC(5, 2),
    box_height NUMERIC(5, 2),
    box_depth NUMERIC(5, 2),
    model_3d_url VARCHAR(500),
    model_status VARCHAR(20),
    model_candidate_path VARCHAR(500),
    model_job_id VARCHAR(36),
    model_submitted_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    model_is_verified BOOLEAN NOT NULL DEFAULT 0,
    model_submitted_at DATETIME,
    source VARCHAR(10) NOT NULL DEFAULT 'bgg',
    is_verified BOOLEAN NOT NULL DEFAULT 1,
    community_contributions_enabled BOOLEAN NOT NULL DEFAULT 1,
    created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    cached_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_games_source CHECK (source IN ('bgg', 'custom')),
    CONSTRAINT ck_games_model_status CHECK (
        model_status IS NULL OR model_status IN (
            'pending', 'processing', 'awaiting_review', 'ready', 'failed'
        )
    ),
    CONSTRAINT ck_games_min_players CHECK (min_players IS NULL OR min_players >= 1),
    CONSTRAINT ck_games_players_range CHECK (
        max_players IS NULL OR min_players IS NULL OR max_players >= min_players
    ),
    CONSTRAINT ck_games_rating CHECK (rating IS NULL OR (rating >= 0 AND rating <= 10)),
    CONSTRAINT ck_games_weight CHECK (weight IS NULL OR (weight >= 0 AND weight <= 5))
)
"""


CREATE_GAME_IMAGES = """
CREATE TABLE IF NOT EXISTS game_images (
    id INTEGER NOT NULL PRIMARY KEY,
    public_id CHAR(32) NOT NULL,
    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    storage_path VARCHAR(500) NOT NULL,
    image_url VARCHAR(500),
    caption VARCHAR(120),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    is_verified BOOLEAN NOT NULL DEFAULT 0,
    created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_game_images_status CHECK (status IN ('pending', 'approved'))
)
"""


CREATE_GAME_BARCODES = """
CREATE TABLE IF NOT EXISTS game_barcodes (
    id INTEGER NOT NULL PRIMARY KEY,
    public_id CHAR(32) NOT NULL,
    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    barcode VARCHAR(13) NOT NULL,
    language_code VARCHAR(2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    is_verified BOOLEAN NOT NULL DEFAULT 0,
    source VARCHAR(20) NOT NULL DEFAULT 'community',
    created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    approved_at DATETIME,
    CONSTRAINT ck_game_barcodes_status CHECK (status IN ('pending', 'approved')),
    CONSTRAINT ck_game_barcodes_source CHECK (source IN ('community', 'legacy')),
    CONSTRAINT ck_game_barcodes_language CHECK (language_code IN ('pl', 'en')),
    CONSTRAINT ck_game_barcodes_format CHECK (
        length(barcode) IN (8, 12, 13)
        AND barcode NOT GLOB '*[^0-9]*'
    ),
    CONSTRAINT uq_game_barcodes_game_language_status
        UNIQUE (game_id, language_code, status)
)
"""

CREATE_GAME_BARCODES_NEW = CREATE_GAME_BARCODES.replace(
    "CREATE TABLE IF NOT EXISTS game_barcodes",
    "CREATE TABLE game_barcodes_new",
    1,
)


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}


def _table_sql(connection: sqlite3.Connection, table: str) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row[0] if row and row[0] else ""


def _backup(connection: sqlite3.Connection, database_path: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = database_path.with_name(f"{database_path.name}.backup-{timestamp}")
    with sqlite3.connect(backup_path) as destination:
        connection.backup(destination)
    return backup_path


def migrate(database_path: Path) -> tuple[bool, Path | None]:
    database_path = database_path.resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"Nie znaleziono bazy SQLite: {database_path}")

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA busy_timeout = 5000")
    try:
        if not _columns(connection, "games") or not _columns(connection, "users"):
            raise RuntimeError("Baza nie zawiera wymaganych tabel users i games")

        games_sql = _table_sql(connection, "games")
        needs_games_rebuild = (
            "community_contributions_enabled" not in _columns(connection, "games")
            or "awaiting_review" not in games_sql
            or "barcode" in _columns(connection, "games")
        )
        needs_admin = "is_admin" not in _columns(connection, "users")
        needs_images = not _columns(connection, "game_images")
        needs_barcodes = not _columns(connection, "game_barcodes")
        needs_barcode_enum = (
            not needs_barcodes
            and "language_code IN ('pl', 'en')"
            not in _table_sql(connection, "game_barcodes")
        )
        needs_barcode_format = (
            not needs_barcodes
            and (
                "length(barcode) IN (8, 12, 13)"
                not in _table_sql(connection, "game_barcodes")
                or "barcode NOT GLOB '*[^0-9]*'"
                not in _table_sql(connection, "game_barcodes")
            )
        )
        has_unclassified_barcodes = (
            "barcode" in _columns(connection, "games")
            and connection.execute(
                "SELECT EXISTS (SELECT 1 FROM games WHERE barcode IS NOT NULL)"
            ).fetchone()[0]
            == 1
        )
        has_unsupported_languages = (
            not needs_barcodes
            and connection.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM game_barcodes
                    WHERE language_code NOT IN ('pl', 'en')
                )
                """
            ).fetchone()[0]
            == 1
        )
        has_invalid_barcodes = (
            not needs_barcodes
            and connection.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM game_barcodes
                    WHERE length(barcode) NOT IN (8, 12, 13)
                       OR barcode GLOB '*[^0-9]*'
                )
                """
            ).fetchone()[0]
            == 1
        )
        if has_unclassified_barcodes or has_unsupported_languages or has_invalid_barcodes:
            raise RuntimeError(
                "Barcode wymaga ręcznej poprawy: dozwolone są pl/en oraz wyłącznie "
                "EAN-8, UPC-A i EAN-13"
            )

        if not (
            needs_games_rebuild
            or needs_admin
            or needs_images
            or needs_barcodes
            or needs_barcode_enum
            or needs_barcode_format
        ):
            return False, None

        backup_path = _backup(connection, database_path)
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("BEGIN IMMEDIATE")
        try:
            if needs_admin:
                connection.execute(
                    "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"
                )

            if needs_games_rebuild:
                old_columns = _columns(connection, "games")
                connection.execute("DROP TABLE IF EXISTS games_new")
                connection.execute(CREATE_GAMES)
                copied = [column for column in GAME_COLUMNS if column in old_columns]
                names = ", ".join(f'"{column}"' for column in copied)
                connection.execute(
                    # `copied` jest przecięciem ze stałą allowlistą GAME_COLUMNS;
                    # żaden fragment nie pochodzi od użytkownika.
                    f"INSERT INTO games_new ({names}) SELECT {names} FROM games"  # nosec B608
                )
                connection.execute("DROP TABLE games")
                connection.execute("ALTER TABLE games_new RENAME TO games")

            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_games_bgg_id ON games (bgg_id)"
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_games_slug ON games (slug)"
            )
            connection.execute("CREATE INDEX IF NOT EXISTS ix_games_title ON games (title)")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_games_is_expansion ON games (is_expansion)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_games_bgg_rank ON games (bgg_rank)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_games_model_job_id ON games (model_job_id)"
            )

            connection.execute(CREATE_GAME_IMAGES)
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_game_images_public_id "
                "ON game_images (public_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_game_images_game_id ON game_images (game_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_game_images_status ON game_images (status)"
            )

            if needs_barcode_enum or needs_barcode_format:
                connection.execute("DROP TABLE IF EXISTS game_barcodes_new")
                connection.execute(CREATE_GAME_BARCODES_NEW)
                connection.execute(
                    """
                    INSERT INTO game_barcodes_new (
                        id, public_id, game_id, barcode, language_code, status,
                        is_verified, source, created_by_id, created_at, approved_at
                    )
                    SELECT
                        id, public_id, game_id, barcode, language_code, status,
                        is_verified, source, created_by_id, created_at, approved_at
                    FROM game_barcodes
                    """
                )
                connection.execute("DROP TABLE game_barcodes")
                connection.execute(
                    "ALTER TABLE game_barcodes_new RENAME TO game_barcodes"
                )
            else:
                connection.execute(CREATE_GAME_BARCODES)
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_game_barcodes_public_id "
                "ON game_barcodes (public_id)"
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_game_barcodes_barcode "
                "ON game_barcodes (barcode)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_game_barcodes_game_id "
                "ON game_barcodes (game_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_game_barcodes_status "
                "ON game_barcodes (status)"
            )
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(f"Naruszenia kluczy obcych po migracji: {violations[:5]}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.execute("PRAGMA foreign_keys = ON")

        return True, backup_path
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", nargs="?", default="local.db", type=Path)
    args = parser.parse_args()
    changed, backup = migrate(args.database)
    if changed:
        print(f"Migracja zakończona. Kopia: {backup}")
    else:
        print("Schemat jest już aktualny; bez zmian.")


if __name__ == "__main__":
    main()
