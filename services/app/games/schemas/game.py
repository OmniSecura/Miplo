"""Schematy wejściowe i wyjściowe modułu games."""

import html
import unicodedata
from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Form
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from services.app.games.enums import GameLanguage
from services.app.shelf.schemas import ShelfItemResponse


_BIDI_CONTROLS = frozenset("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(value: str) -> str:
    """Usuwa tagi HTML i znaki sterujące; wynik jest zwykłym tekstem."""
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    cleaned = html.unescape("".join(parser.parts)).strip()
    for char in cleaned:
        if (unicodedata.category(char) == "Cc" and char not in "\n\t") or char in _BIDI_CONTROLS:
            raise ValueError("control characters are not allowed")
    return cleaned


def _plain_single_line(value: str) -> str:
    cleaned = _plain_text(value)
    if "\n" in cleaned or "\t" in cleaned:
        raise ValueError("new lines and tabs are not allowed")
    return cleaned


def _safe_https_url(value: str) -> str:
    value = value.strip()
    if len(value) > 500 or any(char.isspace() for char in value):
        raise ValueError("invalid HTTPS URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("invalid HTTPS URL")
    return value


GameTitle = Annotated[
    str,
    BeforeValidator(_plain_single_line),
    StringConstraints(strip_whitespace=True, min_length=2, max_length=150),
]
GameDescription = Annotated[
    str,
    BeforeValidator(_plain_text),
    StringConstraints(strip_whitespace=True, max_length=2000),
]
GameTypesJson = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=2000)]
BarcodeText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=8,
        max_length=13,
        pattern=r"^(?:[0-9]{8}|[0-9]{12}|[0-9]{13})$",
    ),
]


def _normalize_language_code(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("language code must be a string")
    return value.strip().lower().replace("_", "-")


LanguageCode = Annotated[
    GameLanguage,
    BeforeValidator(_normalize_language_code),
]
HttpsUrl = Annotated[
    str,
    BeforeValidator(_safe_https_url),
    StringConstraints(strip_whitespace=True, max_length=500),
]
BoxDimension = Annotated[Decimal, Field(ge=Decimal("2.0"), le=Decimal("100.0"))]


class GameCreate(BaseModel):
    """Pola formularza tworzenia customowej gry."""

    model_config = ConfigDict(extra="forbid")

    title: GameTitle
    description: GameDescription | None = None
    min_players: int = Field(ge=1, le=20)
    max_players: int = Field(ge=1, le=50)
    playing_time: int | None = Field(default=None, ge=1, le=1440)
    game_types: GameTypesJson
    box_width: BoxDimension | None = None
    box_height: BoxDimension | None = None
    box_depth: BoxDimension | None = None
    year_published: int | None = Field(default=None, ge=1900, le=2030)
    instruction_url: HttpsUrl | None = None

    @model_validator(mode="after")
    def validate_player_range(self) -> "GameCreate":
        if self.max_players < self.min_players:
            raise ValueError("max_players must be greater than or equal to min_players")
        return self

    @classmethod
    def as_form(
        cls,
        title: str = Form(...),
        min_players: int = Form(...),
        max_players: int = Form(...),
        game_types: str = Form(...),
        description: str | None = Form(None),
        playing_time: int | None = Form(None),
        box_width: Decimal | None = Form(None),
        box_height: Decimal | None = Form(None),
        box_depth: Decimal | None = Form(None),
        year_published: int | None = Form(None),
        instruction_url: str | None = Form(None),
    ) -> "GameCreate":
        return cls(
            title=title,
            description=description,
            min_players=min_players,
            max_players=max_players,
            playing_time=playing_time,
            game_types=game_types,
            box_width=box_width,
            box_height=box_height,
            box_depth=box_depth,
            year_published=year_published,
            instruction_url=instruction_url,
        )


class GameUpdate(BaseModel):
    """Częściowa aktualizacja customowej gry; brak pola oznacza brak zmiany."""

    model_config = ConfigDict(extra="forbid")

    title: GameTitle | None = None
    description: GameDescription | None = None
    min_players: int | None = Field(default=None, ge=1, le=20)
    max_players: int | None = Field(default=None, ge=1, le=50)
    playing_time: int | None = Field(default=None, ge=1, le=1440)
    game_types: GameTypesJson | None = None
    box_width: BoxDimension | None = None
    box_height: BoxDimension | None = None
    box_depth: BoxDimension | None = None
    year_published: int | None = Field(default=None, ge=1900, le=2030)
    instruction_url: HttpsUrl | None = None

    @classmethod
    def as_form(
        cls,
        title: str | None = Form(None),
        description: str | None = Form(None),
        min_players: int | None = Form(None),
        max_players: int | None = Form(None),
        playing_time: int | None = Form(None),
        game_types: str | None = Form(None),
        box_width: Decimal | None = Form(None),
        box_height: Decimal | None = Form(None),
        box_depth: Decimal | None = Form(None),
        year_published: int | None = Form(None),
        instruction_url: str | None = Form(None),
    ) -> "GameUpdate":
        return cls(
            title=title,
            description=description,
            min_players=min_players,
            max_players=max_players,
            playing_time=playing_time,
            game_types=game_types,
            box_width=box_width,
            box_height=box_height,
            box_depth=box_depth,
            year_published=year_published,
            instruction_url=instruction_url,
        )


class GalleryImageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    caption: Annotated[
        str,
        BeforeValidator(_plain_single_line),
        StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    ] | None = None

    @classmethod
    def as_form(cls, caption: str | None = Form(None)) -> "GalleryImageCreate":
        return cls(caption=caption)


class GameSearchResult(BaseModel):
    bgg_id: int | None = None
    slug: str | None = None
    title: str
    year_published: int | None = None
    cover_url: str | None = None
    in_database: bool = False


class GameListItem(BaseModel):
    id: int
    bgg_id: int | None = None
    slug: str
    title: str
    year_published: int | None = None
    min_players: int | None = None
    max_players: int | None = None
    rating: Decimal | None = None
    cover_url: str | None = None
    game_types: list[str] = Field(default_factory=list)
    model_3d_url: str | None = None
    source: str
    bgg_rank: int | None = None
    users_rated: int | None = None
    is_expansion: bool = False
    miplo_rating: Decimal | None = None
    miplo_ratings_count: int = 0
    miplo_reviews_count: int = 0


class GameImagePublic(BaseModel):
    public_id: UUID
    image_url: str
    caption: str | None = None
    created_at: datetime


class GameImageSubmission(BaseModel):
    public_id: UUID
    status: str
    caption: str | None = None
    created_at: datetime


class GameBarcodePublic(BaseModel):
    barcode: str
    language_code: GameLanguage


class BarcodeSubmission(BaseModel):
    public_id: UUID
    barcode: str
    language_code: GameLanguage
    status: str
    created_at: datetime


class GameDetail(GameListItem):
    description: str | None = None
    playing_time: int | None = None
    weight: Decimal | None = None
    instruction_url: str | None = None
    box_width: Decimal | None = None
    box_height: Decimal | None = None
    box_depth: Decimal | None = None
    model_status: str | None = None
    is_verified: bool
    barcodes: list[GameBarcodePublic] = Field(default_factory=list)
    created_at: datetime
    community_contributions_enabled: bool
    images: list[GameImagePublic] = Field(default_factory=list)
    on_my_shelf: bool = False
    my_shelf_item: ShelfItemResponse | None = None
    my_rating: Decimal | None = None
    my_review: str | None = None


class PaginatedGames(BaseModel):
    items: list[GameListItem]
    total: int
    page: int
    size: int
    pages: int


class BarcodeAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    barcode: BarcodeText
    language_code: LanguageCode

    @classmethod
    def as_form(
        cls,
        barcode: str = Form(...),
        language_code: GameLanguage = Form(...),
    ) -> "BarcodeAssign":
        return cls(barcode=barcode, language_code=language_code)


class CatalogImportResult(BaseModel):
    mode: str
    total_rows: int
    inserted: int
    updated: int
    skipped: int
    errors: int
    duration_seconds: float


class PendingImageModeration(BaseModel):
    public_id: UUID
    game_slug: str
    game_title: str
    caption: str | None = None
    preview_url: str
    submitted_by_tag: str | None = None
    created_at: datetime


class PendingGameModeration(BaseModel):
    game: GameDetail
    cover_preview_url: str | None = None


class PendingModelModeration(BaseModel):
    game_slug: str
    game_title: str
    model_status: str
    preview_url: str
    submitted_by_tag: str | None = None
    submitted_at: datetime | None = None


class PendingBarcodeModeration(BaseModel):
    public_id: UUID
    game_slug: str
    game_title: str
    barcode: str
    language_code: GameLanguage
    replaces_barcode: str | None = None
    submitted_by_tag: str | None = None
    created_at: datetime
