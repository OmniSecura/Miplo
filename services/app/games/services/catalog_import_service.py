"""Batchowy, idempotentny import katalogu BGG z CSV lub JSON."""

import csv
import io
import json
import logging
import unicodedata
from collections.abc import Iterator, Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile
from slugify import slugify
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.app.core.errors import ApiError, ErrorCode
from services.app.games.models import Game
from services.app.games.schemas import CatalogImportResult

logger = logging.getLogger(__name__)

MAX_IMPORT_FILE_SIZE = 32 * 1024 * 1024
MAX_IMPORT_ROWS = 250_000
BATCH_SIZE = 1_000
_ALLOWED_EXTENSIONS = {".csv", ".json"}
_BIDI_CONTROLS = frozenset("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


def _file_size(stream: BinaryIO) -> int:
    position = stream.tell()
    stream.seek(0, io.SEEK_END)
    size = stream.tell()
    stream.seek(position)
    return size


def _iter_csv(stream: BinaryIO) -> Iterator[Mapping[str, object]]:
    stream.seek(0)
    wrapper = io.TextIOWrapper(stream, encoding="utf-8-sig", errors="strict", newline="")
    try:
        reader = csv.DictReader(wrapper)
        required = {"id", "name"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ApiError.bad_request(
                ErrorCode.INVALID_IMPORT_FILE,
                details={"required_columns": sorted(required)},
            )
        yield from reader
    except UnicodeDecodeError:
        raise ApiError.bad_request(ErrorCode.INVALID_IMPORT_FILE)
    finally:
        wrapper.detach()


def _iter_json(stream: BinaryIO) -> Iterator[Mapping[str, object]]:
    stream.seek(0)
    wrapper = io.TextIOWrapper(stream, encoding="utf-8-sig", errors="strict")
    try:
        payload = json.load(wrapper)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ApiError.bad_request(ErrorCode.INVALID_IMPORT_FILE)
    finally:
        wrapper.detach()

    if isinstance(payload, dict):
        payload = payload.get("items", payload.get("games"))
    if not isinstance(payload, list):
        raise ApiError.bad_request(ErrorCode.INVALID_IMPORT_FILE)
    for item in payload:
        if isinstance(item, dict):
            yield item


def _optional_int(value: object, *, minimum: int = 0, maximum: int = 2_147_483_647) -> int | None:
    if value in (None, "", "NA", "N/A", "Not Ranked"):
        return None
    try:
        parsed = int(float(str(value)))
    except (TypeError, ValueError):
        return None
    return parsed if minimum <= parsed <= maximum else None


def _optional_decimal(value: object, *, maximum: Decimal) -> Decimal | None:
    if value in (None, "", "NA", "N/A"):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed.quantize(Decimal("0.01")) if Decimal("0") <= parsed <= maximum else None


def _boolean(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _normalize(row: Mapping[str, object]) -> dict[str, object] | None:
    bgg_id = _optional_int(row.get("id", row.get("bgg_id")), minimum=1)
    title = str(row.get("name", row.get("title", ""))).strip()
    if bgg_id is None or not (1 <= len(title) <= 200):
        return None
    if any(unicodedata.category(char) == "Cc" or char in _BIDI_CONTROLS for char in title):
        return None

    year = _optional_int(row.get("yearpublished", row.get("year_published")), minimum=1, maximum=32767)
    if year == 0:
        year = None

    return {
        "bgg_id": bgg_id,
        "title": title,
        "year_published": year,
        "bgg_rank": _optional_int(row.get("rank", row.get("bgg_rank")), minimum=1),
        "rating": _optional_decimal(row.get("average", row.get("rating")), maximum=Decimal("10")),
        "users_rated": _optional_int(row.get("usersrated", row.get("users_rated")), minimum=0),
        "is_expansion": _boolean(row.get("is_expansion", False)),
    }


def _next_slug(title: str, used: set[str]) -> str:
    base = slugify(title, max_length=180) or "game"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _upsert_batch(
    db: Session,
    rows: list[dict[str, object]],
    used_slugs: set[str],
) -> tuple[int, int]:
    # Ostatni rekord danego bgg_id w batchu wygrywa; wejściowy duplikat nie tworzy gry.
    unique_rows = {int(row["bgg_id"]): row for row in rows}
    existing = {
        game.bgg_id: game
        for game in db.scalars(select(Game).where(Game.bgg_id.in_(unique_rows))).all()
    }
    created = 0
    updated = 0
    for bgg_id, row in unique_rows.items():
        game = existing.get(bgg_id)
        if game is None:
            game = Game(
                bgg_id=bgg_id,
                slug=_next_slug(str(row["title"]), used_slugs),
                source="bgg",
                is_verified=True,
                cached_at=None,
            )
            db.add(game)
            created += 1
        else:
            updated += 1

        game.title = str(row["title"])
        game.year_published = row["year_published"]  # type: ignore[assignment]
        game.bgg_rank = row["bgg_rank"]  # type: ignore[assignment]
        game.rating = row["rating"]  # type: ignore[assignment]
        game.users_rated = row["users_rated"]  # type: ignore[assignment]
        game.is_expansion = bool(row["is_expansion"])
        game.source = "bgg"
        game.is_verified = True

    db.commit()
    return created, updated


def import_catalog(db: Session, file: UploadFile) -> CatalogImportResult:
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    if extension not in _ALLOWED_EXTENSIONS:
        raise ApiError.bad_request(ErrorCode.INVALID_IMPORT_FILE)
    if _file_size(file.file) > MAX_IMPORT_FILE_SIZE:
        raise ApiError.bad_request(
            ErrorCode.FILE_TOO_LARGE,
            details={"max_bytes": MAX_IMPORT_FILE_SIZE},
        )

    iterator = _iter_csv(file.file) if extension == ".csv" else _iter_json(file.file)
    used_slugs = set(db.scalars(select(Game.slug)).all())
    batch: list[dict[str, object]] = []
    total = created = updated = skipped = 0

    try:
        for raw in iterator:
            total += 1
            if total > MAX_IMPORT_ROWS:
                raise ApiError.bad_request(
                    ErrorCode.INVALID_IMPORT_FILE,
                    details={"max_rows": MAX_IMPORT_ROWS},
                )
            normalized = _normalize(raw)
            if normalized is None:
                skipped += 1
                continue
            batch.append(normalized)
            if len(batch) >= BATCH_SIZE:
                batch_created, batch_updated = _upsert_batch(db, batch, used_slugs)
                created += batch_created
                updated += batch_updated
                batch.clear()

        if batch:
            batch_created, batch_updated = _upsert_batch(db, batch, used_slugs)
            created += batch_created
            updated += batch_updated
    except ApiError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("Import katalogu gier nie powiódł się")
        raise ApiError(500, ErrorCode.CATALOG_IMPORT_FAILED)

    return CatalogImportResult(
        total_rows=total,
        created=created,
        updated=updated,
        skipped=skipped,
    )
