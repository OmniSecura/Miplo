"""Walidacja i kontrakty odpowiedzi dla ocen i recenzji."""

import html
import unicodedata
from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
)

from services.app.ratings.enums import RatingSource, ReviewReportReason

_BIDI_CONTROLS = frozenset("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    cleaned = html.unescape("".join(parser.parts)).strip()
    for char in cleaned:
        if (unicodedata.category(char) == "Cc" and char not in "\n\t") or char in _BIDI_CONTROLS:
            raise ValueError("control characters are not allowed")
    return cleaned


RatingValue = Annotated[
    Decimal,
    Field(
        ge=Decimal("1.0"),
        le=Decimal("10.0"),
        multiple_of=Decimal("0.5"),
        max_digits=3,
        decimal_places=1,
        examples=[Decimal("8.5")],
    ),
]
ReviewText = Annotated[
    str,
    BeforeValidator(_plain_text),
    StringConstraints(strip_whitespace=True, min_length=10, max_length=5000),
]
ReportDetails = Annotated[
    str,
    BeforeValidator(_plain_text),
    StringConstraints(strip_whitespace=True, min_length=3, max_length=500),
]
ModerationReason = Annotated[
    str,
    BeforeValidator(_plain_text),
    StringConstraints(strip_whitespace=True, min_length=3, max_length=200),
]


class RatingCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "rating": "8.5",
                "review": "Świetna gra ekonomiczna dla czterech osób.",
                "contains_spoilers": False,
            }
        },
    )

    rating: RatingValue
    review: ReviewText | None = None
    contains_spoilers: bool = False


class RatingUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "rating": "9.0",
                "review": "Po kolejnych partiach oceniam ją jeszcze wyżej.",
                "contains_spoilers": False,
            }
        },
    )

    # Pominąć można, ale jawne null dla pól NOT NULL jest odrzucane.
    rating: RatingValue = None  # type: ignore[assignment]
    review: ReviewText | None = None
    contains_spoilers: bool = None  # type: ignore[assignment]


class RatingAuthor(BaseModel):
    tag: str
    display_name: str | None
    avatar_url: str | None


class RatingResponse(BaseModel):
    public_id: UUID
    game_slug: str
    rating: Decimal
    review: str | None
    contains_spoilers: bool
    source: RatingSource
    created_at: datetime
    updated_at: datetime
    author: RatingAuthor


class MyRatingResponse(BaseModel):
    public_id: UUID
    game_slug: str
    game_title: str
    game_cover_url: str | None
    rating: Decimal
    review: str | None
    contains_spoilers: bool
    source: RatingSource
    is_hidden: bool
    created_at: datetime
    updated_at: datetime


class PaginatedRatings(BaseModel):
    items: list[RatingResponse]
    total: int
    page: int
    size: int
    pages: int


class PaginatedMyRatings(BaseModel):
    items: list[MyRatingResponse]
    total: int
    page: int
    size: int
    pages: int


class RatingDistribution(BaseModel):
    rating_1_2: int
    rating_3_4: int
    rating_5_6: int
    rating_7_8: int
    rating_9_10: int


class GameRatingsSummary(BaseModel):
    bgg_rating: Decimal | None
    bgg_ratings_count: int | None
    bgg_rank: int | None
    miplo_rating: Decimal | None
    miplo_ratings_count: int
    miplo_reviews_count: int
    miplo_distribution: RatingDistribution | None
    combined_rating: Decimal | None
    my_rating: Decimal | None
    my_review: str | None
    has_game_on_shelf: bool


class UserRatingStats(BaseModel):
    total_ratings: int
    total_reviews: int
    avg_rating: Decimal | None
    most_generous_score: Decimal | None
    harshest_score: Decimal | None


class ReviewReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: ReviewReportReason
    details: ReportDetails | None = None


class ReviewReportItem(BaseModel):
    reason: ReviewReportReason
    details: str | None
    reporter_tag: str
    created_at: datetime


class ReportedReviewModeration(BaseModel):
    rating_public_id: UUID
    game_slug: str
    game_title: str
    rating: Decimal
    review: str
    contains_spoilers: bool
    author: RatingAuthor
    report_count: int
    reports: list[ReviewReportItem]
    created_at: datetime


class HideReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: ModerationReason
