"""Stabilne enumy półki współdzielone przez Pydantic i OpenAPI."""

from enum import Enum


class ShelfCondition(str, Enum):
    NEW = "new"
    GOOD = "good"
    USED = "used"
    DAMAGED = "damaged"


class ShelfSort(str, Enum):
    ADDED_AT = "added_at"
    TITLE = "title"
    GAME_RATING = "game_rating"
    MIPLO_RATING = "miplo_rating"
