"""Schematy wejściowe i wyjściowe półki użytkownika."""

import unicodedata
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from services.app.shelf.enums import ShelfCondition

_BIDI_CONTROLS = frozenset("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


def _safe_note(value: str) -> str:
    for char in value:
        if (unicodedata.category(char) == "Cc" and char not in "\n\t") or char in _BIDI_CONTROLS:
            raise ValueError("control characters are not allowed")
    return value


ShelfNotes = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=500),
    AfterValidator(_safe_note),
]
Deposit = Annotated[
    Decimal,
    Field(ge=Decimal("0"), le=Decimal("9999"), max_digits=6, decimal_places=2),
]
GameSlug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=200,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
    Field(
        description="Unikalny slug gry zwrócony przez katalog Miplo.",
        examples=["brass-birmingham"],
    ),
]


class _EmptyTextAsNone(BaseModel):
    @field_validator("lending_notes", "notes", mode="before", check_fields=False)
    @classmethod
    def normalize_empty_text(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ShelfItemCreate(_EmptyTextAsNone):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "game_slug": "brass-birmingham",
                "lendable": True,
                "lending_deposit": "50.00",
                "lending_notes": "Odbiór osobisty, maksymalnie tydzień.",
                "condition": "good",
                "notes": "Mój egzemplarz ma polską instrukcję.",
            }
        },
    )

    game_slug: GameSlug
    lendable: bool = False
    lending_deposit: Deposit | None = None
    lending_notes: ShelfNotes | None = Field(
        default=None,
        description="Opcjonalne publiczne warunki wypożyczenia.",
    )
    condition: ShelfCondition | None = None
    notes: ShelfNotes | None = Field(
        default=None,
        description="Opcjonalna prywatna notatka widoczna tylko właścicielowi.",
    )


class ShelfItemUpdate(_EmptyTextAsNone):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "lendable": True,
                "lending_deposit": "50.00",
                "lending_notes": "Odbiór osobisty, maksymalnie tydzień.",
                "condition": "good",
                "notes": "Mój egzemplarz ma polską instrukcję.",
            }
        },
    )

    # Pole można pominąć, ale jawne null nie może trafić do NOT NULL w bazie.
    lendable: bool = None  # type: ignore[assignment]
    lending_deposit: Deposit | None = None
    lending_notes: ShelfNotes | None = Field(
        default=None,
        description="Opcjonalne publiczne warunki wypożyczenia.",
    )
    condition: ShelfCondition | None = None
    notes: ShelfNotes | None = Field(
        default=None,
        description="Opcjonalna prywatna notatka widoczna tylko właścicielowi.",
    )


class ShelfItemResponse(BaseModel):
    lendable: bool
    lending_deposit: Decimal | None
    lending_notes: str | None
    condition: ShelfCondition | None
    notes: str | None
    added_at: datetime

    game_slug: str
    game_title: str
    game_cover_url: str | None
    game_min_players: int | None
    game_max_players: int | None
    game_playing_time: int | None
    game_rating: Decimal | None
    game_miplo_rating: Decimal | None = None
    game_model_3d_url: str | None


class ShelfPublicItem(BaseModel):
    lendable: bool
    lending_deposit: Decimal | None
    lending_notes: str | None
    condition: ShelfCondition | None
    added_at: datetime

    game_slug: str
    game_title: str
    game_cover_url: str | None
    game_min_players: int | None
    game_max_players: int | None
    game_playing_time: int | None
    game_rating: Decimal | None
    game_miplo_rating: Decimal | None = None
    game_model_3d_url: str | None


class PaginatedShelf(BaseModel):
    items: list[ShelfItemResponse]
    total: int
    page: int
    size: int
    pages: int


class PaginatedPublicShelf(BaseModel):
    items: list[ShelfPublicItem]
    total: int
    page: int
    size: int
    pages: int


class ShelfStats(BaseModel):
    total_games: int
    lendable_games: int
    total_playing_time: int | None


class CollectionImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bgg_username: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=50,
            pattern=r"^[a-zA-Z0-9_]+$",
        ),
    ]
    import_ratings: bool = False


class CollectionImportResult(BaseModel):
    imported: int
    skipped: int
    failed: int
    ratings_imported: int
    total_in_bgg: int
