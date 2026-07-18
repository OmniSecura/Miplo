"""Bezpieczny, batchowy import oficjalnego dumpa rankingów BGG."""

import csv
import io
import logging
import threading
import time
import unicodedata
from collections.abc import Iterator, Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile
from slugify import slugify
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.app.core.errors import ApiError, ErrorCode
from services.app.games.enums import CatalogImportMode
from services.app.games.models import Game
from services.app.games.schemas import CatalogImportResult

logger = logging.getLogger(__name__)

MAX_IMPORT_FILE_SIZE = 50 * 1024 * 1024
MAX_IMPORT_ROWS = 250_000
BATCH_SIZE = 1_000
PROGRESS_EVERY = 10_000
ALLOWED_CONTENT_TYPES = frozenset({"text/csv", "application/vnd.ms-excel"})
REQUIRED_COLUMNS = frozenset(
    {
        "id",
        "name",
        "yearpublished",
        "rank",
        "bayesaverage",
        "average",
        "usersrated",
        "is_expansion",
    }
)

# Te whitelisty są granicą zaufania między dumpem BGG a danymi Miplo.
CSV_UPDATE_FIELDS = frozenset(
    {"rating", "bgg_rank", "users_rated", "year_published"}
)
CSV_FULL_FIELDS = CSV_UPDATE_FIELDS | frozenset({"title", "is_expansion"})

_BIDI_CONTROLS = frozenset("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
_import_lock = threading.Lock()
_POSTGRES_IMPORT_LOCK_ID = int.from_bytes(b"MIPLOBGG", byteorder="big", signed=False)


def _file_size(stream: BinaryIO) -> int:
    try:
        position = stream.tell()
        stream.seek(0, io.SEEK_END)
        size = stream.tell()
        stream.seek(position)
        return size
    except (OSError, ValueError):
        raise ApiError.bad_request(ErrorCode.INVALID_CSV_FORMAT)


def _iter_csv(stream: BinaryIO) -> Iterator[Mapping[str, object]]:
    stream.seek(0)
    wrapper = io.TextIOWrapper(stream, encoding="utf-8-sig", errors="strict", newline="")
    try:
        reader = csv.DictReader(wrapper)
        if not reader.fieldnames:
            raise ApiError.bad_request(ErrorCode.INVALID_CSV_FORMAT)
        normalized_headers = [header.strip().lower() for header in reader.fieldnames]
        if len(normalized_headers) != len(set(normalized_headers)):
            raise ApiError.bad_request(ErrorCode.INVALID_CSV_FORMAT)
        if not REQUIRED_COLUMNS.issubset(normalized_headers):
            raise ApiError.bad_request(
                ErrorCode.INVALID_CSV_FORMAT,
                details={"required_columns": sorted(REQUIRED_COLUMNS)},
            )
        reader.fieldnames = normalized_headers
        for row in reader:
            # DictReader zapisuje nadmiarowe wartości pod kluczem None.
            if None in row:
                yield {}
            else:
                yield row
    except UnicodeDecodeError:
        raise ApiError.bad_request(ErrorCode.INVALID_CSV_FORMAT)
    finally:
        wrapper.detach()


def _optional_int(
    value: object,
    *,
    minimum: int = 0,
    maximum: int = 2_147_483_647,
) -> int | None:
    if value in (None, "", "NA", "N/A", "Not Ranked"):
        return None
    try:
        # Dump bywa generowany przez narzędzia zapisujące liczby jako "1.0".
        parsed_decimal = Decimal(str(value).strip())
        if parsed_decimal != parsed_decimal.to_integral_value():
            return None
        parsed = int(parsed_decimal)
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if minimum <= parsed <= maximum else None


def _optional_decimal(value: object, *, maximum: Decimal) -> Decimal | None:
    if value in (None, "", "NA", "N/A"):
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not parsed.is_finite() or not Decimal("0") <= parsed <= maximum:
        return None
    return parsed.quantize(Decimal("0.01"))


def _boolean(value: object) -> bool | None:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return None


def _normalize(row: Mapping[str, object]) -> dict[str, object] | None:
    bgg_id = _optional_int(row.get("id"), minimum=1)
    title = " ".join(str(row.get("name", "")).strip().split())
    is_expansion = _boolean(row.get("is_expansion"))
    if bgg_id is None or is_expansion is None or not (1 <= len(title) <= 200):
        return None
    if any(unicodedata.category(char) == "Cc" or char in _BIDI_CONTROLS for char in title):
        return None

    year_raw = row.get("yearpublished")
    rank_raw = row.get("rank")
    rating_raw = row.get("average")
    users_rated_raw = row.get("usersrated")
    year = _optional_int(year_raw, minimum=1, maximum=32767)
    rank = _optional_int(rank_raw, minimum=1)
    rating = _optional_decimal(rating_raw, maximum=Decimal("10"))
    users_rated = _optional_int(users_rated_raw, minimum=0)
    if year is None and str(year_raw or "").strip() not in {"", "0", "NA", "N/A"}:
        return None
    if rank is None and str(rank_raw or "").strip() not in {"", "NA", "N/A", "Not Ranked"}:
        return None
    if rating is None and str(rating_raw or "").strip() not in {"", "NA", "N/A"}:
        return None
    if users_rated is None and str(users_rated_raw or "").strip() not in {"", "NA", "N/A"}:
        return None
    return {
        "bgg_id": bgg_id,
        "title": title,
        "year_published": year,
        "bgg_rank": rank,
        "rating": rating,
        "users_rated": users_rated,
        "is_expansion": is_expansion,
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


def _dialect_insert(db: Session, values: list[dict[str, object]]):
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        return postgresql_insert(Game).values(values)
    if dialect == "sqlite":
        return sqlite_insert(Game).values(values)
    raise RuntimeError(f"unsupported import dialect: {dialect}")


def _upsert_batch(
    db: Session,
    rows: list[dict[str, object]],
    used_slugs: set[str],
    mode: CatalogImportMode,
) -> tuple[int, int]:
    unique_rows = {int(row["bgg_id"]): row for row in rows}
    existing = {
        game.bgg_id: game
        for game in db.scalars(select(Game).where(Game.bgg_id.in_(unique_rows))).all()
    }
    values: list[dict[str, object]] = []
    inserted = updated = 0
    for bgg_id, row in unique_rows.items():
        game = existing.get(bgg_id)
        if game is None:
            slug = _next_slug(str(row["title"]), used_slugs)
            inserted += 1
        else:
            slug = game.slug
            updated += 1
        values.append(
            {
                **row,
                "slug": slug,
                "source": "bgg",
                "is_verified": True,
                # Dump nie oznacza pobrania szczegółów `/thing`.
                "cached_at": game.cached_at if game is not None else None,
            }
        )

    statement = _dialect_insert(db, values)
    allowed_fields = CSV_FULL_FIELDS if mode is CatalogImportMode.FULL else CSV_UPDATE_FIELDS
    update_values = {
        field: getattr(statement.excluded, field)
        for field in allowed_fields
    }
    update_values["updated_at"] = func.now()
    statement = statement.on_conflict_do_update(
        index_elements=[Game.bgg_id],
        set_=update_values,
    )
    db.execute(statement)
    return inserted, updated


def _acquire_database_lock(db: Session) -> None:
    """PostgreSQL: jedna transakcja importu w całym klastrze aplikacji."""
    if db.get_bind().dialect.name != "postgresql":
        return
    acquired = db.scalar(
        text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
        {"lock_id": _POSTGRES_IMPORT_LOCK_ID},
    )
    if not acquired:
        db.rollback()
        raise ApiError.conflict(ErrorCode.IMPORT_ALREADY_RUNNING)


def _validate_upload(file: UploadFile) -> None:
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if Path(file.filename or "").suffix.lower() != ".csv":
        raise ApiError.bad_request(ErrorCode.INVALID_CSV_FORMAT)
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ApiError.bad_request(ErrorCode.INVALID_CSV_FORMAT)
    if _file_size(file.file) > MAX_IMPORT_FILE_SIZE:
        raise ApiError(
            413,
            ErrorCode.CSV_TOO_LARGE,
            details={"max_bytes": MAX_IMPORT_FILE_SIZE},
        )


def import_catalog(
    db: Session,
    file: UploadFile,
    mode: CatalogImportMode = CatalogImportMode.UPDATE,
) -> CatalogImportResult:
    """Importuje dump z białą listą pól i blokadą jednego joba per proces."""
    _validate_upload(file)
    if not _import_lock.acquire(blocking=False):
        raise ApiError.conflict(ErrorCode.IMPORT_ALREADY_RUNNING)

    started = time.monotonic()
    total = inserted = updated = skipped = errors = 0
    try:
        _acquire_database_lock(db)
        used_slugs = set(db.scalars(select(Game.slug)).all())
        seen_bgg_ids: set[int] = set()
        batch: list[dict[str, object]] = []

        for raw in _iter_csv(file.file):
            total += 1
            if total > MAX_IMPORT_ROWS:
                raise ApiError.bad_request(
                    ErrorCode.INVALID_CSV_FORMAT,
                    details={"max_rows": MAX_IMPORT_ROWS},
                )
            normalized = _normalize(raw)
            if normalized is None:
                errors += 1
                continue
            bgg_id = int(normalized["bgg_id"])
            if bgg_id in seen_bgg_ids:
                skipped += 1
                continue
            seen_bgg_ids.add(bgg_id)
            batch.append(normalized)

            if len(batch) >= BATCH_SIZE:
                batch_inserted, batch_updated = _upsert_batch(db, batch, used_slugs, mode)
                inserted += batch_inserted
                updated += batch_updated
                batch.clear()
            if total % PROGRESS_EVERY == 0:
                logger.info(
                    "BGG CSV import progress mode=%s rows=%d inserted=%d updated=%d errors=%d",
                    mode.value,
                    total,
                    inserted,
                    updated,
                    errors,
                )

        if batch:
            batch_inserted, batch_updated = _upsert_batch(db, batch, used_slugs, mode)
            inserted += batch_inserted
            updated += batch_updated
        db.commit()
    except ApiError:
        db.rollback()
        raise
    except (IntegrityError, OSError, csv.Error):
        db.rollback()
        logger.exception("Import katalogu BGG nie powiódł się")
        raise ApiError(500, ErrorCode.CATALOG_IMPORT_FAILED)
    except Exception:
        db.rollback()
        logger.exception("Nieoczekiwany błąd importu katalogu BGG")
        raise ApiError(500, ErrorCode.CATALOG_IMPORT_FAILED)
    finally:
        _import_lock.release()

    duration = round(time.monotonic() - started, 3)
    logger.info(
        "BGG CSV import finished mode=%s rows=%d inserted=%d updated=%d skipped=%d errors=%d duration=%.3f",
        mode.value,
        total,
        inserted,
        updated,
        skipped,
        errors,
        duration,
    )
    return CatalogImportResult(
        mode=mode.value,
        total_rows=total,
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        errors=errors,
        duration_seconds=duration,
    )
