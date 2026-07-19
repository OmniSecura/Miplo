"""Schematy wejściowe i wyjściowe modułu games."""

import html
import unicodedata
from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
from typing import Annotated, TypeVar
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Form
from fastapi.exceptions import RequestValidationError
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from services.app.games.enums import GameLanguage, GameTypeName
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


def _split_multipart_list(value: object) -> object:
    """Swagger UI serializuje multi-select w multipart jako jedno pole CSV.

    Akceptujemy oba formaty: powtórzone pola oraz "Euro,Strategia" w jednym.
    Pusta lista (np. `game_types=` z wygenerowanego curla) staje się None.
    """
    if isinstance(value, list | tuple):
        expanded: list[object] = []
        for item in value:
            if isinstance(item, str):
                expanded.extend(part.strip() for part in item.split(",") if part.strip())
            else:
                expanded.append(item)
        return expanded or None
    return value


def _blank_form_value_to_none(value: object) -> object:
    """Multipart nie rozróżnia pola pominiętego od pustego stringa.

    Swagger/curl wysyłają `pole=` dla niewypełnionych pól opcjonalnych;
    traktujemy to jako brak wartości zamiast błędu parsowania.
    """
    if isinstance(value, str) and not value.strip():
        return None
    return value


_BlankAsNone = BeforeValidator(_blank_form_value_to_none)
# Typy WYŁĄCZNIE dla parametrów as_form — model waliduje właściwe ograniczenia.
FormOptionalInt = Annotated[int | None, _BlankAsNone]
FormOptionalDecimal = Annotated[Decimal | None, _BlankAsNone]
FormOptionalStr = Annotated[str | None, _BlankAsNone]

# Multi-select z zamkniętego katalogu GameTypeName; duplikaty odrzuca serwis.
GameTypesList = Annotated[
    list[GameTypeName],
    BeforeValidator(_split_multipart_list),
    Field(min_length=1, max_length=10),
]

# FastAPI nie stosuje BeforeValidator na LISTOWYCH polach Form, więc as_form
# przyjmuje surowe stringi, a enum waliduje model. To schema przywraca
# multi-select w Swaggerze, którego typ list[str] by nie wygenerował.
_GAME_TYPES_FORM_SCHEMA = {
    "items": {
        "type": "string",
        "enum": [member.value for member in GameTypeName],
        "title": "GameTypeName",
    }
}


_FormModelT = TypeVar("_FormModelT", bound=BaseModel)


def _validated_form_model(cls: type[_FormModelT], **field_values: object) -> _FormModelT:
    """Konwertuje błąd modelu z as_form na standardowe 422 validation_error.

    Bez tego ValidationError podniesiony w ciele dependency omija handler
    RequestValidationError i kończy się jako 500 internal_error.
    """
    try:
        return cls(**field_values)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


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
    game_types: GameTypesList
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
        game_types: list[str] = Form(..., json_schema_extra=_GAME_TYPES_FORM_SCHEMA),
        description: FormOptionalStr = Form(None),
        playing_time: FormOptionalInt = Form(None),
        box_width: FormOptionalDecimal = Form(None),
        box_height: FormOptionalDecimal = Form(None),
        box_depth: FormOptionalDecimal = Form(None),
        year_published: FormOptionalInt = Form(None),
        instruction_url: FormOptionalStr = Form(None),
    ) -> "GameCreate":
        return _validated_form_model(
            cls,
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
    game_types: GameTypesList | None = None
    box_width: BoxDimension | None = None
    box_height: BoxDimension | None = None
    box_depth: BoxDimension | None = None
    year_published: int | None = Field(default=None, ge=1900, le=2030)
    instruction_url: HttpsUrl | None = None

    @classmethod
    def as_form(
        cls,
        title: FormOptionalStr = Form(None),
        description: FormOptionalStr = Form(None),
        min_players: FormOptionalInt = Form(None),
        max_players: FormOptionalInt = Form(None),
        playing_time: FormOptionalInt = Form(None),
        game_types: list[str] | None = Form(None, json_schema_extra=_GAME_TYPES_FORM_SCHEMA),
        box_width: FormOptionalDecimal = Form(None),
        box_height: FormOptionalDecimal = Form(None),
        box_depth: FormOptionalDecimal = Form(None),
        year_published: FormOptionalInt = Form(None),
        instruction_url: FormOptionalStr = Form(None),
    ) -> "GameUpdate":
        return _validated_form_model(
            cls,
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
    caption: (
        Annotated[
            str,
            BeforeValidator(_plain_single_line),
            StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
        ]
        | None
    ) = None

    @classmethod
    def as_form(cls, caption: FormOptionalStr = Form(None)) -> "GalleryImageCreate":
        return _validated_form_model(cls, caption=caption)


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
        return _validated_form_model(cls, barcode=barcode, language_code=language_code)


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
