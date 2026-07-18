"""Priorytetowa, budżetowana synchronizacja szczegółów gier z BGG."""

import asyncio
import logging
import math
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from services.app.core.config import settings
from services.app.core.errors import ApiError, ErrorCode
from services.app.games.models import Game
from services.app.games.services import game_service
from services.app.ratings.models import GameRating
from services.app.shelf.models import ShelfItem

logger = logging.getLogger(__name__)

_BATCH_SIZE = 20
_MIN_TIME_FOR_NEXT_BATCH = 1.0


def _has_user_activity():
    return or_(
        exists(select(1).where(ShelfItem.game_id == Game.id)),
        exists(select(1).where(GameRating.game_id == Game.id)),
    )


def _level_one_ids(db: Session, limit: int, excluded: set[int]) -> list[int]:
    """Gry używane przez userów, których `/thing` nigdy nie pobrano."""
    shelf_count = (
        select(func.count(ShelfItem.id))
        .where(ShelfItem.game_id == Game.id)
        .correlate(Game)
        .scalar_subquery()
    )
    query = (
        select(Game.bgg_id)
        .where(
            Game.bgg_id.is_not(None),
            Game.cached_at.is_(None),
            _has_user_activity(),
        )
        .order_by(shelf_count.desc(), Game.bgg_rank.is_(None), Game.bgg_rank)
        .limit(limit)
    )
    if excluded:
        query = query.where(Game.bgg_id.not_in(excluded))
    return [int(value) for value in db.scalars(query).all() if value is not None]


def _level_two_ids(db: Session, limit: int, excluded: set[int]) -> list[int]:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.BGG_CACHE_TTL_SECONDS)
    query = (
        select(Game.bgg_id)
        .where(
            Game.bgg_id.is_not(None),
            Game.cached_at.is_not(None),
            Game.cached_at < cutoff,
            _has_user_activity(),
        )
        .order_by(Game.cached_at.asc())
        .limit(limit)
    )
    if excluded:
        query = query.where(Game.bgg_id.not_in(excluded))
    return [int(value) for value in db.scalars(query).all() if value is not None]


def _level_three_ids(db: Session, limit: int, excluded: set[int]) -> list[int]:
    query = (
        select(Game.bgg_id)
        .where(
            Game.bgg_id.is_not(None),
            Game.cached_at.is_(None),
            Game.bgg_rank.is_not(None),
            Game.is_expansion.is_(False),
        )
        .order_by(Game.bgg_rank.asc())
        .limit(limit)
    )
    if excluded:
        query = query.where(Game.bgg_id.not_in(excluded))
    return [int(value) for value in db.scalars(query).all() if value is not None]


async def _sync_ids(
    db: Session,
    bgg_ids: list[int],
    remaining,
    processed: set[int],
) -> tuple[int, int, bool]:
    succeeded = failed = 0
    for offset in range(0, len(bgg_ids), _BATCH_SIZE):
        budget_left = remaining()
        if budget_left <= _MIN_TIME_FOR_NEXT_BATCH:
            return succeeded, failed, True
        batch = bgg_ids[offset : offset + _BATCH_SIZE]
        processed.update(batch)
        try:
            async with asyncio.timeout(budget_left):
                games = await game_service.get_or_fetch_games_batch(db, batch)
        except TimeoutError:
            db.rollback()
            return succeeded, failed, True
        except ApiError as exc:
            db.rollback()
            failed += len(batch)
            logger.warning("nightly_sync BGG batch failed ids=%s code=%s", batch, exc.detail)
            continue
        except Exception:
            db.rollback()
            failed += len(batch)
            logger.exception("nightly_sync batch failed ids=%s", batch)
            continue

        batch_succeeded = len(set(batch).intersection(games))
        succeeded += batch_succeeded
        failed += len(batch) - batch_succeeded
    return succeeded, failed, False


async def nightly_sync(db: Session, budget_seconds: int | None = None) -> dict[str, int | float | bool]:
    """Wzbogaca katalog w trzech priorytetach i nigdy nie przekracza budżetu."""
    if not settings.BGG_API_TOKEN:
        raise ApiError(503, ErrorCode.BGG_NOT_CONFIGURED)
    budget = budget_seconds or settings.NIGHTLY_SYNC_BUDGET
    if budget <= 0:
        raise ValueError("budget_seconds must be positive")
    started = time.monotonic()
    processed: set[int] = set()
    stats: dict[str, int | float | bool] = {
        "with_users": 0,
        "refreshed": 0,
        "by_rank": 0,
        "failed": 0,
        "budget_exhausted": False,
        "duration_seconds": 0.0,
    }

    def remaining() -> float:
        return max(0.0, budget - (time.monotonic() - started))

    levels = [
        (
            "with_users",
            lambda: _level_one_ids(db, settings.NIGHTLY_SYNC_LEVEL1_LIMIT, processed),
        ),
        (
            "refreshed",
            lambda: _level_two_ids(db, settings.NIGHTLY_SYNC_LEVEL2_LIMIT, processed),
        ),
    ]
    for key, load_ids in levels:
        if remaining() <= _MIN_TIME_FOR_NEXT_BATCH:
            stats["budget_exhausted"] = True
            break
        succeeded, failed, exhausted = await _sync_ids(db, load_ids(), remaining, processed)
        stats[key] = succeeded
        stats["failed"] = int(stats["failed"]) + failed
        if exhausted:
            stats["budget_exhausted"] = True
            break

    if not stats["budget_exhausted"] and remaining() > _MIN_TIME_FOR_NEXT_BATCH:
        estimated_requests = math.floor(remaining() / max(settings.BGG_MIN_REQUEST_INTERVAL, 0.1))
        level_three_limit = min(10_000, max(0, estimated_requests * _BATCH_SIZE))
        if level_three_limit:
            ids = _level_three_ids(db, level_three_limit, processed)
            succeeded, failed, exhausted = await _sync_ids(db, ids, remaining, processed)
            stats["by_rank"] = succeeded
            stats["failed"] = int(stats["failed"]) + failed
            stats["budget_exhausted"] = exhausted

    stats["duration_seconds"] = round(time.monotonic() - started, 3)
    logger.info("nightly_sync finished stats=%s", stats)
    return stats
