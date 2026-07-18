"""CRUD półki, statystyki i import kolekcji BGG — jedyne miejsce commitów."""

import asyncio
import logging
import math

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager

from services.app.core import bgg_client
from services.app.core.errors import ApiError, ErrorCode
from services.app.games.models import Game
from services.app.games.services import game_service
from services.app.shelf.enums import ShelfCondition, ShelfSort
from services.app.shelf.models import ShelfItem
from services.app.shelf.schemas import (
    CollectionImportRequest,
    CollectionImportResult,
    PaginatedPublicShelf,
    PaginatedShelf,
    ShelfItemCreate,
    ShelfItemResponse,
    ShelfItemUpdate,
    ShelfPublicItem,
    ShelfStats,
)
from services.app.users.models import User

logger = logging.getLogger(__name__)

_IMPORT_BATCH_SIZE = 20
_IMPORT_BATCH_DELAY_SECONDS = 5
_IMPORT_TIMEOUT_SECONDS = 180


def to_response(item: ShelfItem) -> ShelfItemResponse:
    game = item.game
    return ShelfItemResponse(
        lendable=item.lendable,
        lending_deposit=item.lending_deposit,
        lending_notes=item.lending_notes,
        condition=item.condition,
        notes=item.notes,
        added_at=item.added_at,
        game_slug=game.slug,
        game_title=game.title,
        game_cover_url=game.cover_url,
        game_min_players=game.min_players,
        game_max_players=game.max_players,
        game_playing_time=game.playing_time,
        game_rating=game.rating,
        game_miplo_rating=None,
        game_model_3d_url=game.model_3d_url,
    )


def to_public_response(item: ShelfItem) -> ShelfPublicItem:
    game = item.game
    # Warunki są publiczną ofertą tylko wtedy, gdy egzemplarz jest wypożyczalny.
    return ShelfPublicItem(
        lendable=item.lendable,
        lending_deposit=item.lending_deposit if item.lendable else None,
        lending_notes=item.lending_notes if item.lendable else None,
        condition=item.condition,
        added_at=item.added_at,
        game_slug=game.slug,
        game_title=game.title,
        game_cover_url=game.cover_url,
        game_min_players=game.min_players,
        game_max_players=game.max_players,
        game_playing_time=game.playing_time,
        game_rating=game.rating,
        game_miplo_rating=None,
        game_model_3d_url=game.model_3d_url,
    )


def _items_query():
    # Game ma kilka relacji `selectin`, których półka nie potrzebuje. Jawne noload
    # utrzymuje listowanie jako jeden JOIN niezależnie od liczby pozycji.
    eager_game = contains_eager(ShelfItem.game)
    return (
        select(ShelfItem)
        .join(ShelfItem.game)
        .options(
            eager_game.noload(Game.game_types),
            eager_game.noload(Game.images),
            eager_game.noload(Game.barcodes),
            eager_game.noload(Game.shelf_items),
        )
    )


def _apply_filters(query, *, lendable, search, condition, players):
    if lendable is not None:
        query = query.where(ShelfItem.lendable.is_(lendable))
    if search:
        query = query.where(func.lower(Game.title).like(f"%{search.strip()[:100].lower()}%"))
    if condition is not None:
        query = query.where(ShelfItem.condition == condition.value)
    if players is not None:
        query = query.where(Game.min_players <= players, Game.max_players >= players)
    return query


def _apply_sort(query, sort: ShelfSort):
    if sort is ShelfSort.TITLE:
        return query.order_by(Game.title.asc(), ShelfItem.id.asc())
    if sort is ShelfSort.GAME_RATING:
        return query.order_by(
            Game.rating.is_(None),
            Game.rating.desc(),
            Game.title.asc(),
        )
    if sort is ShelfSort.MIPLO_RATING:
        raise ApiError(501, ErrorCode.RATINGS_NOT_AVAILABLE)
    return query.order_by(ShelfItem.added_at.desc(), ShelfItem.id.desc())


def get_my_shelf(
    db: Session,
    user_id: int,
    page: int,
    size: int,
    *,
    lendable: bool | None = None,
    search: str | None = None,
    condition: ShelfCondition | None = None,
    players: int | None = None,
    sort: ShelfSort = ShelfSort.ADDED_AT,
) -> PaginatedShelf:
    base = _apply_filters(
        select(ShelfItem.id).join(ShelfItem.game).where(ShelfItem.user_id == user_id),
        lendable=lendable,
        search=search,
        condition=condition,
        players=players,
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    query = _apply_filters(
        _items_query().where(ShelfItem.user_id == user_id),
        lendable=lendable,
        search=search,
        condition=condition,
        players=players,
    )
    items = db.scalars(
        _apply_sort(query, sort).offset((page - 1) * size).limit(size)
    ).unique().all()
    return PaginatedShelf(
        items=[to_response(item) for item in items],
        total=total,
        page=page,
        size=size,
        pages=math.ceil(total / size),
    )


def get_user_shelf(
    db: Session,
    tag: str,
    page: int,
    size: int,
    *,
    lendable: bool | None = None,
) -> PaginatedPublicShelf:
    user = db.scalar(select(User).where(User.tag == tag, User.is_active.is_(True)))
    if user is None:
        raise ApiError.not_found(ErrorCode.USER_NOT_FOUND)

    filters = [ShelfItem.user_id == user.id, Game.is_verified.is_(True)]
    if lendable is not None:
        filters.append(ShelfItem.lendable.is_(lendable))
    total = db.scalar(
        select(func.count(ShelfItem.id)).join(ShelfItem.game).where(*filters)
    ) or 0
    items = db.scalars(
        _items_query()
        .where(*filters)
        .order_by(ShelfItem.added_at.desc(), ShelfItem.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).unique().all()
    return PaginatedPublicShelf(
        items=[to_public_response(item) for item in items],
        total=total,
        page=page,
        size=size,
        pages=math.ceil(total / size),
    )


def _get_item(db: Session, user_id: int, game_id: int) -> ShelfItem | None:
    return db.scalar(
        _items_query().where(
            ShelfItem.user_id == user_id,
            ShelfItem.game_id == game_id,
        )
    )


def _get_item_by_slug(db: Session, user_id: int, game_slug: str) -> ShelfItem | None:
    normalized = game_service.normalize_slug(game_slug)
    if not normalized:
        return None
    return db.scalar(
        _items_query().where(
            ShelfItem.user_id == user_id,
            Game.slug == normalized,
        )
    )


def add_to_shelf(db: Session, user_id: int, data: ShelfItemCreate) -> ShelfItem:
    game = db.scalar(
        select(Game).where(
            Game.slug == data.game_slug,
            Game.is_verified.is_(True),
        )
    )
    if game is None:
        # Nie ujawniamy niezweryfikowanych customowych wpisów przez półkę.
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    if _get_item(db, user_id, game.id) is not None:
        raise ApiError.conflict(ErrorCode.GAME_ALREADY_ON_SHELF)

    values = data.model_dump(exclude={"game_slug"})
    if isinstance(values.get("condition"), ShelfCondition):
        values["condition"] = values["condition"].value
    item = ShelfItem(user_id=user_id, game_id=game.id, **values)
    item.game = game
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError.conflict(ErrorCode.GAME_ALREADY_ON_SHELF)
    db.refresh(item)
    return _get_item(db, user_id, game.id) or item


def update_shelf_item(
    db: Session,
    user_id: int,
    game_slug: str,
    data: ShelfItemUpdate,
) -> ShelfItem:
    item = _get_item_by_slug(db, user_id, game_slug)
    if item is None:
        raise ApiError.not_found(ErrorCode.GAME_NOT_ON_SHELF)
    changes = data.model_dump(exclude_unset=True)
    if isinstance(changes.get("condition"), ShelfCondition):
        changes["condition"] = changes["condition"].value
    for field, value in changes.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return _get_item(db, user_id, item.game_id) or item


def remove_from_shelf(db: Session, user_id: int, game_slug: str) -> None:
    item = _get_item_by_slug(db, user_id, game_slug)
    if item is None:
        raise ApiError.not_found(ErrorCode.GAME_NOT_ON_SHELF)
    db.delete(item)
    db.commit()


def is_on_shelf(db: Session, user_id: int, game_id: int) -> ShelfItem | None:
    return _get_item(db, user_id, game_id)


def get_shelf_stats(db: Session, user_id: int) -> ShelfStats:
    row = db.execute(
        select(
            func.count(ShelfItem.id),
            func.sum(case((ShelfItem.lendable.is_(True), 1), else_=0)),
            func.sum(Game.playing_time),
        )
        .select_from(ShelfItem)
        .join(ShelfItem.game)
        .where(ShelfItem.user_id == user_id)
    ).one()
    return ShelfStats(
        total_games=int(row[0] or 0),
        lendable_games=int(row[1] or 0),
        total_playing_time=int(row[2]) if row[2] is not None else None,
    )


async def import_bgg_collection(
    db: Session,
    user_id: int,
    data: CollectionImportRequest,
) -> CollectionImportResult:
    if data.import_ratings:
        # Oceny należą do osobnej domeny i nie mogą być pozornie „zaimportowane”.
        raise ApiError(501, ErrorCode.RATINGS_NOT_AVAILABLE)

    imported = skipped = failed = 0
    collection: list[bgg_client.BggCollectionItem] = []
    processed_ids: set[int] = set()
    try:
        async with asyncio.timeout(_IMPORT_TIMEOUT_SECONDS):
            collection = await bgg_client.fetch_collection(data.bgg_username)
            unique_ids = list(dict.fromkeys(item.bgg_id for item in collection))
            existing_game_ids = set(
                db.scalars(
                    select(ShelfItem.game_id).where(ShelfItem.user_id == user_id)
                ).all()
            )

            for offset in range(0, len(unique_ids), _IMPORT_BATCH_SIZE):
                batch = unique_ids[offset : offset + _IMPORT_BATCH_SIZE]
                try:
                    games = await game_service.get_or_fetch_games_batch(
                        db,
                        batch,
                        commit=False,
                    )
                except ApiError as exc:
                    logger.warning(
                        "BGG batch import failed for %s: %s",
                        batch,
                        exc.detail,
                    )
                    failed += len(batch)
                    processed_ids.update(batch)
                    if exc.detail["error_code"] == ErrorCode.BGG_RATE_LIMITED.value:
                        failed += len(unique_ids) - len(processed_ids)
                        break
                    if offset + _IMPORT_BATCH_SIZE < len(unique_ids):
                        await asyncio.sleep(_IMPORT_BATCH_DELAY_SECONDS)
                    continue

                for bgg_id in batch:
                    processed_ids.add(bgg_id)
                    game = games.get(bgg_id)
                    if game is None:
                        failed += 1
                        continue
                    if game.id in existing_game_ids:
                        skipped += 1
                        continue
                    try:
                        # SAVEPOINT rozwiązuje wyścig z równoległym „Dodaj na półkę”
                        # bez utraty wcześniejszych pozycji całego importu.
                        with db.begin_nested():
                            item = ShelfItem(
                                user_id=user_id,
                                game_id=game.id,
                                lendable=False,
                            )
                            db.add(item)
                            db.flush()
                    except IntegrityError:
                        skipped += 1
                    else:
                        existing_game_ids.add(game.id)
                        imported += 1

                if offset + _IMPORT_BATCH_SIZE < len(unique_ids):
                    await asyncio.sleep(_IMPORT_BATCH_DELAY_SECONDS)
    except TimeoutError:
        remaining = len({item.bgg_id for item in collection}) - len(processed_ids)
        failed += max(0, remaining)
        logger.warning("Import kolekcji BGG przekroczył %d sekund", _IMPORT_TIMEOUT_SECONDS)
    except ApiError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("Import kolekcji BGG nie powiódł się")
        raise ApiError(502, ErrorCode.COLLECTION_IMPORT_FAILED)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Najbezpieczniej nie raportować niezatwierdzonych liczników po wyścigu.
        raise ApiError.conflict(ErrorCode.GAME_ALREADY_ON_SHELF)
    return CollectionImportResult(
        imported=imported,
        skipped=skipped,
        failed=failed,
        ratings_imported=0,
        total_in_bgg=len(collection),
    )
