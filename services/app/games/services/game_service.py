"""Logika domenowa games: cache BGG, katalog i customowe gry."""

import json
import logging
import math
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import UploadFile
from slugify import slugify
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.app.core import bgg_client
from services.app.core.config import settings
from services.app.core.database import db_session
from services.app.core.errors import ApiError, ErrorCode
from services.app.games.enums import GameLanguage
from services.app.games.models import Game, GameBarcode, GameImage, GameType, game_game_types
from services.app.games.schemas import (
    BarcodeSubmission,
    GalleryImageCreate,
    GameBarcodePublic,
    GameCreate,
    GameDetail,
    GameImagePublic,
    GameImageSubmission,
    GameListItem,
    GameSearchResult,
    GameUpdate,
    PaginatedGames,
)
from services.app.games.services import cover_service, gallery_service
from services.app.ratings.constants import MIPLO_MIN_RATINGS_FOR_DISPLAY
from services.app.users.models import User

logger = logging.getLogger(__name__)

# Szczegóły odświeżane z `/thing` co 30 dni. Wartość None z BGG nie usuwa
# wcześniej poprawnej wartości lokalnej.
BGG_STATIC_UPDATABLE_FIELDS = frozenset(
    {
        "title",
        "description",
        "year_published",
        "min_players",
        "max_players",
        "playing_time",
        "weight",
        "cover_url",
    }
)

# Te pola aktualizuje tygodniowy CSV. API wypełnia je tylko przy pierwszym
# pobraniu gry spoza seedu, ale nigdy nie nadpisuje wartości już istniejącej.
BGG_API_FILL_ONLY_FIELDS = frozenset({"rating", "users_rated", "bgg_rank"})

_BGG_CATEGORY_MAP: dict[str, str] = {
    "Economic": "Euro",
    "Industry / Manufacturing": "Euro",
    "City Building": "Euro",
    "Civilization": "Euro",
    "Farming": "Euro",
    "Territory Building": "Euro",
    "Party Game": "Imprezowa",
    "Humor": "Imprezowa",
    "Card Game": "Karciana",
    "Dice": "Kościana",
    "Abstract Strategy": "Abstrakcyjna",
    "Wargame": "Wojenna",
    "Fighting": "Wojenna",
    "Adventure": "Przygodowa",
    "Exploration": "Przygodowa",
    "Fantasy": "Fantasy",
    "Science Fiction": "Sci-Fi",
    "Horror": "Horror",
    "Puzzle": "Logiczna",
    "Deduction": "Logiczna",
    "Children's Game": "Dla dzieci",
    "Family Game": "Familijna",
    "Trivia": "Quiz",
    "Word Game": "Słowna",
    "Sports": "Sportowa",
    "Racing": "Wyścigowa",
}

_refresh_lock = threading.Lock()
_refresh_cooldown: dict[int, float] = {}
_pending_refreshes: dict[int, float] = {}
_refresh_checks = 0


def normalize_slug(value: str) -> str:
    return slugify(value.strip(), max_length=180)


def _generate_slug(db: Session, title: str, *, exclude_game_id: int | None = None) -> str:
    base = normalize_slug(title) or "game"
    candidate = base
    suffix = 2
    while True:
        query = select(Game.id).where(Game.slug == candidate)
        if exclude_game_id is not None:
            query = query.where(Game.id != exclude_game_id)
        if db.scalar(query) is None:
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


def _get_or_create_game_type(db: Session, name: str) -> GameType:
    type_slug = slugify(name, max_length=80) or "other"
    existing = db.scalar(select(GameType).where(GameType.slug == type_slug))
    if existing is not None:
        return existing

    try:
        with db.begin_nested():
            created = GameType(name=name, slug=type_slug)
            db.add(created)
            db.flush()
        return created
    except IntegrityError:
        existing = db.scalar(select(GameType).where(GameType.slug == type_slug))
        if existing is None:
            raise
        return existing


def _resolve_types(db: Session, names: list[str], *, from_bgg: bool = False) -> list[GameType]:
    result: list[GameType] = []
    seen: set[str] = set()
    for raw_name in names:
        name = _BGG_CATEGORY_MAP.get(raw_name, raw_name) if from_bgg else raw_name
        type_slug = slugify(name, max_length=80)
        if not type_slug or type_slug in seen:
            continue
        seen.add(type_slug)
        result.append(_get_or_create_game_type(db, name))
    return result


def _parse_game_types(raw: str) -> list[str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise ApiError.bad_request(ErrorCode.INVALID_GAME_TYPES)
    if not isinstance(payload, list) or not 1 <= len(payload) <= 10:
        raise ApiError.bad_request(ErrorCode.INVALID_GAME_TYPES)

    result: list[str] = []
    seen: set[str] = set()
    for value in payload:
        if not isinstance(value, str):
            raise ApiError.bad_request(ErrorCode.INVALID_GAME_TYPES)
        name = value.strip()
        if not 2 <= len(name) <= 100 or "<" in name or ">" in name:
            raise ApiError.bad_request(ErrorCode.INVALID_GAME_TYPES)
        if any(unicodedata.category(char) == "Cc" for char in name):
            raise ApiError.bad_request(ErrorCode.INVALID_GAME_TYPES)
        normalized = slugify(name, max_length=80)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(name)
    if not result:
        raise ApiError.bad_request(ErrorCode.INVALID_GAME_TYPES)
    return result


def _is_valid_barcode(value: str) -> bool:
    if not value.isascii() or not value.isdigit() or len(value) not in {8, 12, 13}:
        return False
    body, supplied_check = value[:-1], int(value[-1])
    weighted_sum = sum(
        int(digit) * (3 if index % 2 == 0 else 1) for index, digit in enumerate(reversed(body))
    )
    expected_check = (10 - weighted_sum % 10) % 10
    return supplied_check == expected_check


def _validate_barcode(value: str | None) -> None:
    if value is not None and not _is_valid_barcode(value):
        raise ApiError.bad_request(ErrorCode.INVALID_BARCODE_FORMAT)


def to_list_item(game: Game) -> GameListItem:
    return GameListItem(
        id=game.id,
        bgg_id=game.bgg_id,
        slug=game.slug,
        title=game.title,
        year_published=game.year_published,
        min_players=game.min_players,
        max_players=game.max_players,
        rating=game.rating,
        cover_url=game.cover_url,
        game_types=[game_type.name for game_type in game.game_types],
        model_3d_url=game.model_3d_url,
        source=game.source,
        bgg_rank=game.bgg_rank,
        users_rated=game.users_rated,
        is_expansion=game.is_expansion,
        miplo_rating=(
            game.miplo_rating if game.miplo_ratings_count >= MIPLO_MIN_RATINGS_FOR_DISPLAY else None
        ),
        miplo_ratings_count=game.miplo_ratings_count,
        miplo_reviews_count=game.miplo_reviews_count,
    )


def to_detail(game: Game, my_shelf_item=None, my_rating=None) -> GameDetail:
    shelf_response = None
    if my_shelf_item is not None:
        # Lokalny import świadomie omija cykl games ↔ shelf. GameDetail jest
        # kompozycją publicznych danych gry i prywatnego kontekstu bieżącego usera.
        from services.app.shelf.services import shelf_service

        shelf_response = shelf_service.to_response(my_shelf_item)
    return GameDetail(
        **to_list_item(game).model_dump(),
        description=game.description,
        playing_time=game.playing_time,
        weight=game.weight,
        instruction_url=game.instruction_url,
        box_width=game.box_width,
        box_height=game.box_height,
        box_depth=game.box_depth,
        model_status=game.model_status,
        is_verified=game.is_verified,
        barcodes=[
            GameBarcodePublic(
                barcode=barcode.barcode,
                language_code=barcode.language_code,
            )
            for barcode in game.barcodes
            if barcode.is_verified and barcode.status == "approved"
        ],
        created_at=game.created_at,
        community_contributions_enabled=game.community_contributions_enabled,
        images=[
            GameImagePublic(
                public_id=image.public_id,
                image_url=image.image_url,
                caption=image.caption,
                created_at=image.created_at,
            )
            for image in game.images
            if image.is_verified and image.image_url is not None
        ],
        on_my_shelf=my_shelf_item is not None,
        my_shelf_item=shelf_response,
        my_rating=my_rating.rating if my_rating is not None else None,
        my_review=my_rating.review if my_rating is not None else None,
    )


def is_stale(game: Game) -> bool:
    if game.bgg_id is None:
        return False
    if game.cached_at is None:
        return True
    cached_at = game.cached_at
    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - cached_at > timedelta(
        seconds=settings.BGG_CACHE_TTL_SECONDS
    )


def should_schedule_refresh(game_id: int) -> bool:
    """Rezerwuje ograniczony slot na best-effort refresh starej gry.

    Cooldown deduplikuje kolejne wejścia w tę samą grę, a globalna granica
    pending chroni pamięć procesu przed kolejką utworzoną przez wiele slugów.
    """
    global _refresh_checks
    if game_id < 1 or not settings.BGG_API_TOKEN:
        return False
    now = time.monotonic()
    with _refresh_lock:
        _refresh_checks += 1
        if _refresh_checks % 100 == 0:
            oldest = now - (10 * settings.BGG_REFRESH_COOLDOWN)
            stale_keys = [key for key, timestamp in _refresh_cooldown.items() if timestamp < oldest]
            for key in stale_keys:
                _refresh_cooldown.pop(key, None)
            abandoned = [key for key, timestamp in _pending_refreshes.items() if timestamp < oldest]
            for key in abandoned:
                _pending_refreshes.pop(key, None)

        if game_id in _pending_refreshes:
            return False
        if len(_pending_refreshes) >= settings.BGG_MAX_PENDING_REFRESHES:
            return False
        last = _refresh_cooldown.get(game_id, 0.0)
        if now - last < settings.BGG_REFRESH_COOLDOWN:
            return False
        _refresh_cooldown[game_id] = now
        _pending_refreshes[game_id] = now
        return True


def _finish_scheduled_refresh(game_id: int) -> None:
    with _refresh_lock:
        _pending_refreshes.pop(game_id, None)


def _reset_refresh_state_for_tests() -> None:
    """Czyści wyłącznie nietrwały debounce procesu."""
    global _refresh_checks
    with _refresh_lock:
        _refresh_cooldown.clear()
        _pending_refreshes.clear()
        _refresh_checks = 0


async def refresh_game_by_id(game_id: int) -> None:
    """Odświeża rekord w osobnej sesji; błąd nie psuje publicznej odpowiedzi."""
    try:
        with db_session() as db:
            game = db.get(Game, game_id)
            if game is None or not is_stale(game):
                return
            await get_or_fetch_game(db, game.bgg_id)  # type: ignore[arg-type]
    except ApiError as exc:
        logger.warning("BGG background refresh failed game_id=%d code=%s", game_id, exc.detail)
    except Exception:
        logger.exception("BGG background refresh failed game_id=%d", game_id)
    finally:
        _finish_scheduled_refresh(game_id)


async def search_games(db: Session, query: str) -> list[GameSearchResult]:
    sanitized = " ".join(query.strip().split())[:100]
    if len(sanitized) < 2:
        return []

    local_games = db.scalars(
        select(Game)
        .where(
            func.lower(Game.title).contains(sanitized.lower(), autoescape=True),
            Game.is_verified.is_(True),
        )
        .order_by(Game.bgg_rank.is_(None), Game.bgg_rank, Game.title)
        .limit(50)
    ).all()
    if local_games:
        return [
            GameSearchResult(
                bgg_id=game.bgg_id,
                slug=game.slug,
                title=game.title,
                year_published=game.year_published,
                cover_url=game.cover_url,
                in_database=True,
            )
            for game in local_games
        ]

    remote = await bgg_client.search(sanitized)
    return [
        GameSearchResult(
            bgg_id=item.bgg_id,
            title=item.title,
            year_published=item.year_published,
            in_database=False,
        )
        for item in remote
    ]


def _apply_bgg_data(
    db: Session,
    data: bgg_client.BggGameData,
    game: Game | None = None,
) -> Game:
    types = _resolve_types(db, data.categories, from_bgg=True) if data.categories else None
    if game is None:
        game = Game(
            bgg_id=data.bgg_id,
            slug=_generate_slug(db, data.title),
            source="bgg",
            is_verified=True,
        )
        db.add(game)

    for field in BGG_STATIC_UPDATABLE_FIELDS:
        value = getattr(data, field)
        if value is not None:
            setattr(game, field, value)
    for field in BGG_API_FILL_ONLY_FIELDS:
        value = getattr(data, field)
        if getattr(game, field) is None and value is not None:
            setattr(game, field, value)
    game.cached_at = datetime.now(timezone.utc)
    if types is not None:
        game.game_types = types
    return game


async def get_or_fetch_game(db: Session, bgg_id: int) -> Game:
    game = db.scalar(select(Game).where(Game.bgg_id == bgg_id))
    if game is not None and not is_stale(game):
        return game

    data = await bgg_client.fetch_game_deduped(bgg_id)
    game = _apply_bgg_data(db, data, game)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raced = db.scalar(select(Game).where(Game.bgg_id == bgg_id))
        if raced is None:
            raise
        return raced
    db.refresh(game)
    return game


async def get_or_fetch_games_batch(
    db: Session,
    bgg_ids: list[int],
    *,
    commit: bool = True,
) -> dict[int, Game]:
    """Upsert maksymalnie 20 gier jednym requestem BGG.

    Przy ``commit=False`` pozostawia transakcję otwartą dla operacji złożonej,
    np. importu półki, który wykonuje jeden commit na samym końcu.
    """
    unique_ids = list(dict.fromkeys(bgg_ids))
    if not unique_ids or len(unique_ids) > 20 or any(item_id < 1 for item_id in unique_ids):
        raise ValueError("batch must contain from 1 to 20 positive BGG IDs")

    existing = db.scalars(select(Game).where(Game.bgg_id.in_(unique_ids))).all()
    result = {game.bgg_id: game for game in existing if game.bgg_id is not None}
    stale_ids = [
        item_id for item_id in unique_ids if item_id not in result or is_stale(result[item_id])
    ]
    if stale_ids:
        remote_games = await bgg_client.fetch_games(stale_ids)
        for data in remote_games:
            result[data.bgg_id] = _apply_bgg_data(db, data, result.get(data.bgg_id))

    try:
        db.flush()
        if commit:
            db.commit()
    except IntegrityError:
        db.rollback()
        if not commit:
            raise
        # Równoległy import mógł wstawić te same BGG IDs. Odczyt po rollbacku
        # zwraca zwycięskie rekordy bez dublowania katalogu.
        return {
            game.bgg_id: game
            for game in db.scalars(select(Game).where(Game.bgg_id.in_(unique_ids))).all()
            if game.bgg_id is not None
        }
    return result


def get_game_by_slug(db: Session, slug_or_title: str) -> Game | None:
    normalized = normalize_slug(slug_or_title)
    if not normalized:
        return None
    return db.scalar(select(Game).where(Game.slug == normalized))


def _get_game_by_slug_for_update(db: Session, slug_or_title: str) -> Game | None:
    normalized = normalize_slug(slug_or_title)
    if not normalized:
        return None
    return db.scalar(select(Game).where(Game.slug == normalized).with_for_update())


def get_game_by_barcode(db: Session, barcode: str) -> Game | None:
    _validate_barcode(barcode)
    return db.scalar(
        select(Game)
        .join(GameBarcode)
        .where(
            GameBarcode.barcode == barcode,
            GameBarcode.status == "approved",
            GameBarcode.is_verified.is_(True),
            Game.is_verified.is_(True),
        )
    )


def _assert_contributions_open(game: Game) -> None:
    if not game.community_contributions_enabled:
        raise ApiError.forbidden(ErrorCode.CONTRIBUTIONS_LOCKED)


def propose_barcode(
    db: Session,
    slug: str,
    barcode: str,
    language_code: GameLanguage,
    current_user: User,
) -> BarcodeSubmission:
    _validate_barcode(barcode)
    game = _get_game_by_slug_for_update(db, slug)
    if game is None:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    _assert_contributions_open(game)
    if not game.is_verified and game.created_by_id != current_user.id:
        raise ApiError.forbidden(ErrorCode.NOT_GAME_OWNER)
    if db.scalar(select(GameBarcode.id).where(GameBarcode.barcode == barcode)) is not None:
        raise ApiError.conflict(ErrorCode.GAME_BARCODE_EXISTS)
    pending = db.scalar(
        select(GameBarcode.id).where(
            GameBarcode.game_id == game.id,
            GameBarcode.language_code == language_code,
            GameBarcode.status == "pending",
        )
    )
    if pending is not None:
        raise ApiError.conflict(ErrorCode.BARCODE_PROPOSAL_PENDING)

    proposal = GameBarcode(
        game_id=game.id,
        barcode=barcode,
        language_code=language_code,
        status="pending",
        is_verified=False,
        source="community",
        created_by_id=current_user.id,
    )
    db.add(proposal)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError.conflict(ErrorCode.GAME_BARCODE_EXISTS)
    db.refresh(proposal)
    return BarcodeSubmission(
        public_id=proposal.public_id,
        barcode=proposal.barcode,
        language_code=proposal.language_code,
        status=proposal.status,
        created_at=proposal.created_at,
    )


def list_games(
    db: Session,
    page: int,
    size: int,
    search: str | None = None,
    players: int | None = None,
    game_type: str | None = None,
    source: str | None = None,
    is_verified: bool | None = True,
    include_expansions: bool = False,
) -> PaginatedGames:
    query = select(Game)
    if search:
        query = query.where(
            func.lower(Game.title).contains(
                search.strip()[:100].lower(),
                autoescape=True,
            )
        )
    if players is not None:
        query = query.where(Game.min_players <= players, Game.max_players >= players)
    if game_type:
        query = (
            query.join(game_game_types)
            .join(GameType)
            .where(GameType.slug == slugify(game_type, max_length=80))
        )
    if source:
        query = query.where(Game.source == source)
    if is_verified is not None:
        query = query.where(Game.is_verified.is_(is_verified))
    if not include_expansions:
        query = query.where(Game.is_expansion.is_(False))

    total = db.scalar(select(func.count()).select_from(query.distinct().subquery())) or 0
    games = (
        db.scalars(
            query.order_by(Game.bgg_rank.is_(None), Game.bgg_rank, Game.title)
            .offset((page - 1) * size)
            .limit(size)
        )
        .unique()
        .all()
    )
    return PaginatedGames(
        items=[to_list_item(game) for game in games],
        total=total,
        page=page,
        size=size,
        pages=math.ceil(total / size),
    )


def check_title_exists(db: Session, title: str, *, exclude_game_id: int | None = None) -> bool:
    query = select(Game.id).where(func.lower(Game.title) == title.strip().lower())
    if exclude_game_id is not None:
        query = query.where(Game.id != exclude_game_id)
    return db.scalar(query) is not None


def check_barcode_exists(db: Session, barcode: str, *, exclude_game_id: int | None = None) -> bool:
    query = select(GameBarcode.id).where(GameBarcode.barcode == barcode)
    if exclude_game_id is not None:
        query = query.where(GameBarcode.game_id != exclude_game_id)
    return db.scalar(query) is not None


def _raise_title_conflict() -> None:
    """Stabilny kod dla konfliktu zapisu customowej gry po IntegrityError."""
    raise ApiError.conflict(ErrorCode.GAME_TITLE_EXISTS)


async def create_custom_game(
    db: Session,
    data: GameCreate,
    cover: UploadFile | None,
    current_user: User,
) -> Game:
    if check_title_exists(db, data.title):
        raise ApiError.conflict(ErrorCode.GAME_TITLE_EXISTS)

    type_names = _parse_game_types(data.game_types)
    cover_webp = await cover_service.prepare_cover(cover) if cover is not None else None
    game = Game(
        slug=_generate_slug(db, data.title),
        title=data.title,
        description=data.description,
        min_players=data.min_players,
        max_players=data.max_players,
        playing_time=data.playing_time,
        box_width=data.box_width,
        box_height=data.box_height,
        box_depth=data.box_depth,
        year_published=data.year_published,
        instruction_url=data.instruction_url,
        source="custom",
        is_verified=False,
        created_by_id=current_user.id,
        cached_at=None,
        game_types=_resolve_types(db, type_names),
    )
    db.add(game)
    uploaded_path: str | None = None
    try:
        db.flush()
        if cover_webp is not None:
            uploaded_path = await cover_service.upload_candidate(game.id, cover_webp)
            game.cover_candidate_path = uploaded_path
        db.commit()
    except ApiError:
        db.rollback()
        cover_service.delete_path(uploaded_path)
        raise
    except IntegrityError:
        db.rollback()
        cover_service.delete_path(uploaded_path)
        _raise_title_conflict()
    except Exception:
        db.rollback()
        cover_service.delete_path(uploaded_path)
        raise
    db.refresh(game)
    return game


def _assert_custom_owner(game: Game, current_user: User) -> None:
    if game.source != "custom":
        raise ApiError.forbidden(ErrorCode.CANNOT_EDIT_BGG_GAME)
    if game.created_by_id != current_user.id:
        raise ApiError.forbidden(ErrorCode.NOT_GAME_OWNER)


async def update_custom_game(
    db: Session,
    slug: str,
    data: GameUpdate,
    cover: UploadFile | None,
    current_user: User,
) -> Game:
    game = get_game_by_slug(db, slug)
    if game is None:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    _assert_custom_owner(game, current_user)
    _assert_contributions_open(game)

    # Multipart nie rozróżnia wygodnie pola pominiętego od pustego; None oznacza
    # tu "bez zmiany". Osobne endpointy obsłużą jawne czyszczenie zasobów.
    changes = data.model_dump(exclude_none=True)
    new_min = changes.get("min_players", game.min_players)
    new_max = changes.get("max_players", game.max_players)
    if new_min is None or new_max is None or new_max < new_min:
        raise ApiError.bad_request(ErrorCode.INVALID_PLAYER_RANGE)

    new_title = changes.get("title")
    if new_title and check_title_exists(db, new_title, exclude_game_id=game.id):
        raise ApiError.conflict(ErrorCode.GAME_TITLE_EXISTS)
    type_names = None
    if "game_types" in changes:
        type_names = _parse_game_types(changes.pop("game_types"))
    cover_webp = await cover_service.prepare_cover(cover) if cover is not None else None

    if new_title and new_title != game.title:
        game.slug = _generate_slug(db, new_title, exclude_game_id=game.id)
    for field, value in changes.items():
        if value is not None:
            setattr(game, field, value)
    if type_names is not None:
        game.game_types = _resolve_types(db, type_names)
    old_cover_candidate = game.cover_candidate_path
    new_cover_candidate: str | None = None
    if cover_webp is not None:
        new_cover_candidate = await cover_service.upload_candidate(game.id, cover_webp)
        game.cover_candidate_path = new_cover_candidate

    # Każda zmiana społecznościowa ponownie trafia do moderacji.
    game.is_verified = False

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        cover_service.delete_path(new_cover_candidate)
        _raise_title_conflict()
    except Exception:
        db.rollback()
        cover_service.delete_path(new_cover_candidate)
        raise
    if new_cover_candidate:
        cover_service.delete_path(old_cover_candidate)
    db.refresh(game)
    return game


def delete_custom_game(db: Session, slug: str, current_user: User) -> None:
    game = get_game_by_slug(db, slug)
    if game is None:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    _assert_custom_owner(game, current_user)
    game_id = game.id
    db.delete(game)
    db.commit()
    # Baza jest źródłem prawdy. Awaria Storage nie może przywrócić usuniętej gry;
    # osierocony publiczny plik można bezpiecznie posprzątać później.
    cover_service.delete_game_assets(game_id)


async def submit_gallery_image(
    db: Session,
    slug: str,
    payload: GalleryImageCreate,
    file: UploadFile,
    current_user: User,
) -> GameImageSubmission:
    game = _get_game_by_slug_for_update(db, slug)
    if game is None:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    _assert_contributions_open(game)
    # Niezweryfikowaną customową grę zna i rozwija wyłącznie jej twórca.
    # Po publikacji galeria jest community-driven także dla BGG i custom.
    if not game.is_verified:
        _assert_custom_owner(game, current_user)

    image_count = (
        db.scalar(select(func.count()).select_from(GameImage).where(GameImage.game_id == game.id))
        or 0
    )
    if image_count >= 12:
        raise ApiError.conflict(
            ErrorCode.GALLERY_LIMIT_REACHED,
            details={"max_images": 12},
        )

    webp = await gallery_service.prepare_image(file)
    public_id = uuid4()
    storage_path = gallery_service.gallery_path(game.id, public_id)
    await gallery_service.upload_private(storage_path, webp)

    image = GameImage(
        public_id=public_id,
        game_id=game.id,
        storage_path=storage_path,
        caption=payload.caption,
        status="pending",
        is_verified=False,
        created_by_id=current_user.id,
    )
    db.add(image)
    try:
        db.commit()
    except Exception:
        db.rollback()
        gallery_service.delete(storage_path)
        raise
    db.refresh(image)
    return GameImageSubmission(
        public_id=image.public_id,
        status=image.status,
        caption=image.caption,
        created_at=image.created_at,
    )


def delete_gallery_image(
    db: Session,
    slug: str,
    public_id: UUID,
    current_user: User,
) -> None:
    game = get_game_by_slug(db, slug)
    if game is None:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    image = db.scalar(
        select(GameImage).where(
            GameImage.game_id == game.id,
            GameImage.public_id == public_id,
        )
    )
    if image is None:
        raise ApiError.not_found(ErrorCode.IMAGE_NOT_FOUND)
    allowed = (
        current_user.is_admin
        or image.created_by_id == current_user.id
        or (game.source == "custom" and game.created_by_id == current_user.id)
    )
    if not allowed:
        raise ApiError.forbidden(ErrorCode.NOT_GAME_OWNER)
    path = image.storage_path
    db.delete(image)
    db.commit()
    gallery_service.delete(path)


def begin_model_submission(db: Session, slug: str, current_user: User) -> tuple[Game, str]:
    game = _get_game_by_slug_for_update(db, slug)
    if game is None:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    _assert_contributions_open(game)
    if not game.is_verified and game.created_by_id != current_user.id:
        raise ApiError.forbidden(ErrorCode.NOT_GAME_OWNER)
    if _model_submission_blocks_new_job(game):
        raise ApiError.conflict(ErrorCode.MODEL_ALREADY_PROCESSING)

    job_id = str(uuid4())
    game.model_status = "pending"
    game.model_job_id = job_id
    game.model_candidate_path = None
    game.model_submitted_by_id = current_user.id
    game.model_submitted_at = datetime.now(timezone.utc)
    # Istniejący zaakceptowany model pozostaje publiczny podczas moderacji
    # potencjalnego zamiennika.
    game.model_is_verified = game.model_3d_url is not None
    db.commit()
    db.refresh(game)
    return game, job_id


def assert_model_submission_allowed(db: Session, slug: str, current_user: User) -> Game:
    """Tania kontrola uprawnień przed dekodowaniem sześciu obrazów."""
    game = get_game_by_slug(db, slug)
    if game is None:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    _assert_contributions_open(game)
    if not game.is_verified and game.created_by_id != current_user.id:
        raise ApiError.forbidden(ErrorCode.NOT_GAME_OWNER)
    if _model_submission_blocks_new_job(game):
        raise ApiError.conflict(ErrorCode.MODEL_ALREADY_PROCESSING)
    return game


def _model_submission_blocks_new_job(game: Game) -> bool:
    """Pozwala odzyskać grę po ubiciu procesu w trakcie generowania.

    Awaiting_review pozostaje zablokowane do decyzji moderatora. Pending lub
    processing starsze niż 15 minut uznajemy za osierocone; stary job nie może
    nadpisać nowego, bo generator porównuje również model_job_id.
    """
    if game.model_status == "awaiting_review":
        return True
    if game.model_status not in {"pending", "processing"}:
        return False
    submitted_at = game.model_submitted_at
    if submitted_at is None:
        return False
    if submitted_at.tzinfo is None:
        submitted_at = submitted_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - submitted_at <= timedelta(minutes=15)


def delete_model_submission(db: Session, slug: str, current_user: User) -> None:
    game = get_game_by_slug(db, slug)
    if game is None:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    has_proposal = game.model_status in {
        "pending",
        "processing",
        "awaiting_review",
        "failed",
    } and (game.model_job_id is not None or game.model_candidate_path is not None)
    if not has_proposal:
        raise ApiError.not_found(ErrorCode.MODEL_NOT_FOUND)
    allowed = (
        current_user.is_admin
        or game.model_submitted_by_id == current_user.id
        or (game.source == "custom" and game.created_by_id == current_user.id)
    )
    if not allowed:
        raise ApiError.forbidden(ErrorCode.NOT_GAME_OWNER)

    candidate_path = game.model_candidate_path
    public_model_exists = game.model_3d_url is not None
    game.model_status = "ready" if public_model_exists else None
    game.model_candidate_path = None
    game.model_job_id = None
    game.model_submitted_by_id = None
    game.model_submitted_at = None
    game.model_is_verified = public_model_exists
    db.commit()

    from services.app.games.services import box_generator_service

    # Autor propozycji może ją wycofać, ale nie może usunąć wcześniej
    # zaakceptowanego publicznego modelu całej społeczności.
    box_generator_service.delete_path(candidate_path)
