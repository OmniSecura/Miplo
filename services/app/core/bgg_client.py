"""Asynchroniczny klient BoardGameGeek XML API 2."""

import asyncio
import html
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

import httpx

from services.app.core.config import settings
from services.app.core.errors import ApiError, ErrorCode

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_RETRY_DELAYS = (2.0, 4.0, 8.0)
_MAX_SEARCH_RESULTS = 50
_MAX_XML_BYTES = 5 * 1024 * 1024


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


def _safe_int(element: ET.Element | None, attr: str = "value") -> int | None:
    if element is None:
        return None
    raw = element.get(attr)
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _safe_decimal(element: ET.Element | None, attr: str = "value") -> Decimal | None:
    if element is None:
        return None
    raw = element.get(attr)
    try:
        value = Decimal(raw) if raw is not None else None
    except (InvalidOperation, TypeError):
        return None
    return value if value is not None and value >= 0 else None


def _primary_name(item: ET.Element) -> str:
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


async def _get_xml(client: httpx.AsyncClient, path: str, params: dict[str, str]) -> ET.Element:
    url = f"{settings.BGG_API_BASE.rstrip('/')}/{path.lstrip('/')}"
    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            response = await client.get(url, params=params, headers=_headers())
        except httpx.TimeoutException:
            logger.warning("BGG timeout: %s %s (attempt %d)", path, params, attempt + 1)
            if attempt == len(_RETRY_DELAYS):
                raise ApiError(502, ErrorCode.BGG_UNAVAILABLE)
            await asyncio.sleep(_RETRY_DELAYS[attempt])
            continue
        except httpx.HTTPError:
            logger.exception("Błąd transportu BGG: %s", path)
            raise ApiError(502, ErrorCode.BGG_UNAVAILABLE)

        if response.status_code == 202:
            if attempt == len(_RETRY_DELAYS):
                break
            await asyncio.sleep(_RETRY_DELAYS[attempt])
            continue
        if response.status_code == 429:
            logger.warning("BGG odrzucił request limitem 429")
            raise ApiError(503, ErrorCode.BGG_RATE_LIMITED)
        if response.status_code >= 400:
            logger.warning("BGG odpowiedział %d dla %s", response.status_code, path)
            raise ApiError(502, ErrorCode.BGG_UNAVAILABLE)
        if len(response.content) > _MAX_XML_BYTES:
            logger.error("BGG XML przekroczył limit %d bajtów", _MAX_XML_BYTES)
            raise ApiError(502, ErrorCode.BGG_UNAVAILABLE)
        try:
            return ET.fromstring(response.content)
        except ET.ParseError:
            logger.warning("BGG zwrócił niepoprawny XML dla %s", path)
            raise ApiError(502, ErrorCode.BGG_UNAVAILABLE)

    raise ApiError(502, ErrorCode.BGG_UNAVAILABLE)


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


async def fetch_game(bgg_id: int) -> BggGameData:
    _require_token()
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
        root = await _get_xml(client, "thing", {"id": str(bgg_id), "stats": "1"})

    item = root.find(".//item")
    if item is None:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    title = _primary_name(item)
    if not title:
        raise ApiError(502, ErrorCode.BGG_UNAVAILABLE)

    description_element = item.find("description")
    image_element = item.find("image")
    ratings = item.find(".//statistics/ratings")
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
        weight=_safe_decimal(
            ratings.find("averageweight") if ratings is not None else None
        ),
        cover_url=(
            image_element.text.strip()
            if image_element is not None and image_element.text
            else None
        ),
        categories=[
            link.get("value", "").strip()
            for link in item.findall("link[@type='boardgamecategory']")
            if link.get("value", "").strip()
        ],
    )


async def fetch_collection(username: str) -> list[BggCollectionItem]:
    """Pozostaje funkcją integracyjną; publiczny endpoint importu usunięto."""
    _require_token()
    sanitized = re.sub(r"[^\w\-.]", "", username.strip())[:50]
    if not sanitized:
        raise ApiError.bad_request(ErrorCode.INVALID_BGG_USERNAME)
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
        root = await _get_xml(
            client,
            "collection",
            {"username": sanitized, "own": "1", "subtype": "boardgame"},
        )

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
