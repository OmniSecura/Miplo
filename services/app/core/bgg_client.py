"""Asynchroniczny klient BoardGameGeek XML API 2."""

import asyncio
import html
import logging
import re
import time
import weakref
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import cast
from urllib.parse import urlsplit

# Import służy wyłącznie do typowania; wszystkie dane są parsowane przez defusedxml.
from xml.etree.ElementTree import Element  # nosec B405

import httpx
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from services.app.core.config import settings
from services.app.core.errors import ApiError, ErrorCode

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_RETRY_DELAYS = (2.0, 4.0, 8.0)
_MAX_SEARCH_RESULTS = 50
_MAX_XML_BYTES = 5 * 1024 * 1024


@dataclass(slots=True)
class _RuntimeState:
    """Stan ograniczeń przypisany do jednej pętli asyncio.

    Osobny stan per loop zapobiega błędom ``bound to a different event loop``
    w testach i skryptach, które wielokrotnie używają ``asyncio.run``. W jednym
    procesie uvicorn działa jedna główna pętla, więc limit pozostaje globalny
    dla wszystkich requestów obsługiwanych przez ten proces.
    """

    semaphore: asyncio.Semaphore
    interval_lock: asyncio.Lock
    in_flight_lock: asyncio.Lock
    in_flight: dict[int, asyncio.Task["BggGameData"]]
    last_request_at: float = 0.0


_runtime_states: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _RuntimeState] = (
    weakref.WeakKeyDictionary()
)


def _runtime_state() -> _RuntimeState:
    loop = asyncio.get_running_loop()
    state = _runtime_states.get(loop)
    if state is None:
        state = _RuntimeState(
            semaphore=asyncio.Semaphore(settings.BGG_MAX_CONCURRENT),
            interval_lock=asyncio.Lock(),
            in_flight_lock=asyncio.Lock(),
            in_flight={},
        )
        _runtime_states[loop] = state
    return state


def _reset_runtime_state_for_tests() -> None:
    """Czyści wyłącznie nietrwały stan procesu; pomocnicze dla testów."""
    _runtime_states.clear()


@dataclass(frozen=True, slots=True)
class BggSearchResult:
    bgg_id: int
    title: str
    year_published: int | None


@dataclass(frozen=True, slots=True)
class BggGameData:
    bgg_id: int
    title: str
    description: str | None
    year_published: int | None
    min_players: int | None
    max_players: int | None
    playing_time: int | None
    rating: Decimal | None
    weight: Decimal | None
    users_rated: int | None
    bgg_rank: int | None
    cover_url: str | None
    categories: list[str]


@dataclass(frozen=True, slots=True)
class BggCollectionItem:
    bgg_id: int
    title: str
    year_published: int | None
    user_rating: Decimal | None


def _require_token() -> None:
    if not settings.BGG_API_TOKEN:
        raise ApiError(503, ErrorCode.BGG_NOT_CONFIGURED)


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/xml",
        "Authorization": f"Bearer {settings.BGG_API_TOKEN}",
        "User-Agent": "Miplo/0.0.1 (BoardGameGeek cache proxy)",
    }


def _safe_int(element: Element | None, attr: str = "value") -> int | None:
    if element is None:
        return None
    raw = element.get(attr)
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _safe_decimal(element: Element | None, attr: str = "value") -> Decimal | None:
    if element is None:
        return None
    raw = element.get(attr)
    try:
        value = Decimal(raw) if raw is not None else None
    except (InvalidOperation, TypeError):
        return None
    return value if value is not None and value >= 0 else None


def _primary_name(item: Element) -> str:
    primary = item.find("name[@type='primary']")
    if primary is None:
        primary = item.find("name")
    return primary.get("value", "").strip() if primary is not None else ""


def _clean_description(raw: str | None) -> str | None:
    if not raw:
        return None
    text = html.unescape(raw)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:5000] or None


def _safe_cover_url(raw: str | None) -> str | None:
    """Akceptuje wyłącznie HTTPS z oficjalnych domen obrazów BGG."""
    if not raw:
        return None
    value = raw.strip()
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    allowed = host == "boardgamegeek.com" or host.endswith(".geekdo-images.com")
    if parsed.scheme != "https" or not allowed or parsed.username or parsed.password:
        logger.warning("BGG zwrócił niedozwolony URL okładki")
        return None
    return value[:1000]


async def _request_once(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, str],
) -> tuple[int, bytes]:
    """Wykonuje dokładnie jeden request i czyta wyłącznie poprawne XML-e."""
    async with client.stream(
        "GET",
        url,
        params=params,
        headers=_headers(),
    ) as response:
        if response.status_code != 200:
            return response.status_code, b""

        payload = bytearray()
        async for chunk in response.aiter_bytes():
            if len(payload) + len(chunk) > _MAX_XML_BYTES:
                logger.error("BGG XML przekroczył limit %d bajtów", _MAX_XML_BYTES)
                raise ApiError(502, ErrorCode.BGG_UNAVAILABLE)
            payload.extend(chunk)
        return response.status_code, bytes(payload)


async def _throttled_request_once(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, str],
) -> tuple[int, bytes]:
    """Ogranicza współbieżność i odstęp każdego fizycznego requestu do BGG."""
    state = _runtime_state()
    async with state.semaphore:
        async with state.interval_lock:
            # asyncio.sleep może obudzić coroutine minimalnie za wcześnie
            # (szczególnie na Windows). Pętla gwarantuje rzeczywisty minimalny
            # odstęp, a więc nie wypuszcza krótkich burstów do BGG.
            while True:
                elapsed = time.monotonic() - state.last_request_at
                wait = settings.BGG_MIN_REQUEST_INTERVAL - elapsed
                if wait <= 0:
                    break
                await asyncio.sleep(wait)
            state.last_request_at = time.monotonic()
        return await _request_once(client, url, params)


async def _throttled_get_xml(
    client: httpx.AsyncClient,
    path: str,
    params: dict[str, str],
    *,
    not_found_code: ErrorCode | None = None,
) -> Element:
    """Pobiera XML z retry; każda próba przechodzi przez globalny throttle."""
    url = f"{settings.BGG_API_BASE.rstrip('/')}/{path.lstrip('/')}"
    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            status_code, payload = await _throttled_request_once(client, url, params)
        except httpx.TimeoutException:
            # Params mogą zawierać nick kolekcji lub tekst wyszukiwania.
            logger.warning("BGG timeout: %s (attempt %d)", path, attempt + 1)
            if attempt == len(_RETRY_DELAYS):
                raise ApiError(502, ErrorCode.BGG_UNAVAILABLE)
            await asyncio.sleep(_RETRY_DELAYS[attempt])
            continue
        except ApiError:
            raise
        except httpx.HTTPError:
            logger.exception("Błąd transportu BGG: %s", path)
            if attempt == len(_RETRY_DELAYS):
                raise ApiError(502, ErrorCode.BGG_UNAVAILABLE)
            await asyncio.sleep(_RETRY_DELAYS[attempt])
            continue

        if status_code == 202:
            if attempt == len(_RETRY_DELAYS):
                break
            await asyncio.sleep(_RETRY_DELAYS[attempt])
            continue
        if status_code == 429:
            logger.warning("BGG odrzucił request limitem 429")
            raise ApiError(503, ErrorCode.BGG_RATE_LIMITED)
        if status_code == 404 and not_found_code is not None:
            raise ApiError.not_found(not_found_code)
        if status_code >= 500:
            logger.warning("BGG odpowiedział %d dla %s", status_code, path)
            if attempt == len(_RETRY_DELAYS):
                raise ApiError(502, ErrorCode.BGG_UNAVAILABLE)
            await asyncio.sleep(_RETRY_DELAYS[attempt])
            continue
        if status_code >= 400:
            logger.warning("BGG odpowiedział %d dla %s", status_code, path)
            raise ApiError(502, ErrorCode.BGG_UNAVAILABLE)
        if status_code != 200:
            # Redirectów celowo nie śledzimy: token Bearer nie może zostać
            # wysłany do hosta wskazanego przez odpowiedź.
            logger.warning("Nieoczekiwany status BGG %d", status_code)
            raise ApiError(502, ErrorCode.BGG_UNAVAILABLE)

        try:
            return cast(Element, ET.fromstring(payload))
        except (ET.ParseError, DefusedXmlException):
            logger.warning("BGG zwrócił niepoprawny XML dla %s", path)
            raise ApiError(502, ErrorCode.BGG_UNAVAILABLE)

    raise ApiError(502, ErrorCode.BGG_UNAVAILABLE)


async def _get_xml(
    client: httpx.AsyncClient,
    path: str,
    params: dict[str, str],
    *,
    not_found_code: ErrorCode | None = None,
) -> Element:
    """Kompatybilna nazwa wewnętrzna; nie omija throttlingu."""
    return await _throttled_get_xml(
        client,
        path,
        params,
        not_found_code=not_found_code,
    )


async def search(query: str) -> list[BggSearchResult]:
    _require_token()
    sanitized = " ".join(re.sub(r"[^\w\s\-:.!&']", "", query).split())[:100]
    if len(sanitized) < 2:
        return []
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
        root = await _get_xml(client, "search", {"query": sanitized, "type": "boardgame"})

    result: list[BggSearchResult] = []
    for item in root.findall(".//item"):
        try:
            bgg_id = int(item.get("id", ""))
        except ValueError:
            continue
        title = _primary_name(item)
        if not title:
            continue
        result.append(BggSearchResult(bgg_id, title, _safe_int(item.find("yearpublished"))))
        if len(result) >= _MAX_SEARCH_RESULTS:
            break
    return result


def _parse_game_item(item: Element) -> BggGameData | None:
    try:
        bgg_id = int(item.get("id", ""))
    except ValueError:
        return None
    title = _primary_name(item)
    if not title:
        return None

    description_element = item.find("description")
    image_element = item.find("image")
    ratings = item.find(".//statistics/ratings")
    boardgame_rank = ratings.find("ranks/rank[@name='boardgame']") if ratings is not None else None
    return BggGameData(
        bgg_id=bgg_id,
        title=title,
        description=_clean_description(
            description_element.text if description_element is not None else None
        ),
        year_published=_safe_int(item.find("yearpublished")),
        min_players=_safe_int(item.find("minplayers")),
        max_players=_safe_int(item.find("maxplayers")),
        playing_time=_safe_int(item.find("playingtime")),
        rating=_safe_decimal(ratings.find("average") if ratings is not None else None),
        weight=_safe_decimal(ratings.find("averageweight") if ratings is not None else None),
        users_rated=_safe_int(ratings.find("usersrated") if ratings is not None else None),
        bgg_rank=_safe_int(boardgame_rank),
        cover_url=_safe_cover_url(image_element.text if image_element is not None else None),
        categories=[
            link.get("value", "").strip()
            for link in item.findall("link[@type='boardgamecategory']")
            if link.get("value", "").strip()
        ],
    )


async def fetch_games(bgg_ids: list[int]) -> list[BggGameData]:
    """Pobiera maksymalnie 20 gier jednym requestem `/thing`."""
    _require_token()
    unique_ids = list(dict.fromkeys(bgg_ids))
    if not unique_ids or len(unique_ids) > 20 or any(item_id < 1 for item_id in unique_ids):
        raise ValueError("fetch_games accepts from 1 to 20 positive BGG IDs")
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
        root = await _get_xml(
            client,
            "thing",
            {"id": ",".join(str(item_id) for item_id in unique_ids), "stats": "1"},
        )
    parsed = (_parse_game_item(item) for item in root.findall(".//item"))
    return [item for item in parsed if item is not None]


async def fetch_game(bgg_id: int) -> BggGameData:
    games = await fetch_games([bgg_id])
    if not games:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    return games[0]


def _consume_task_exception(task: asyncio.Task[BggGameData]) -> None:
    """Odbiera wyjątek także wtedy, gdy wszyscy oczekujący zostali anulowani."""
    if not task.cancelled():
        task.exception()


async def fetch_game_deduped(bgg_id: int) -> BggGameData:
    """Współdzieli jeden request `/thing` między równoległych odbiorców gry."""
    if bgg_id < 1:
        raise ValueError("bgg_id must be positive")
    state = _runtime_state()
    async with state.in_flight_lock:
        task = state.in_flight.get(bgg_id)
        if task is None:

            async def fetch_and_cleanup() -> BggGameData:
                try:
                    return await fetch_game(bgg_id)
                finally:
                    state.in_flight.pop(bgg_id, None)

            task = asyncio.create_task(fetch_and_cleanup())
            task.add_done_callback(_consume_task_exception)
            state.in_flight[bgg_id] = task

    # Anulowanie jednego klienta nie anuluje requestu współdzielonego z innymi.
    return await asyncio.shield(task)


async def fetch_collection(username: str) -> list[BggCollectionItem]:
    """Pobiera posiadane gry; błędny nick odróżnia od pustej kolekcji."""
    sanitized = username.strip()
    # Nie naprawiamy ani nie obcinamy nicku, bo mogłoby to pobrać kolekcję
    # innego usera (np. "anna!" -> "anna"). Schemat endpointu sprawdza to samo,
    # a klient powtarza walidację jako defense in depth.
    if re.fullmatch(r"[a-zA-Z0-9_]{1,50}", sanitized) is None:
        raise ApiError.bad_request(ErrorCode.INVALID_BGG_USERNAME)
    _require_token()
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
        root = await _get_xml(
            client,
            "collection",
            {"username": sanitized, "own": "1", "subtype": "boardgame"},
            not_found_code=ErrorCode.INVALID_BGG_USERNAME,
        )

    if root.find(".//error") is not None or root.tag == "errors":
        raise ApiError.not_found(ErrorCode.INVALID_BGG_USERNAME)

    result: list[BggCollectionItem] = []
    for item in root.findall(".//item"):
        try:
            bgg_id = int(item.get("objectid", ""))
        except ValueError:
            continue
        name = item.findtext("name", default="").strip()
        if not name:
            continue
        year_raw = item.findtext("yearpublished", default="")
        year = int(year_raw) if year_raw.isdigit() else None
        rating_raw = item.find(".//stats/rating")
        result.append(
            BggCollectionItem(
                bgg_id=bgg_id,
                title=name,
                year_published=year,
                user_rating=_safe_decimal(rating_raw),
            )
        )
    return result
