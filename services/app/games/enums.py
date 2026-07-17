"""Współdzielone enumy domeny games — jeden kontrakt dla ORM, Pydantic i OpenAPI."""

from enum import Enum


class GameLanguage(str, Enum):
    """Obsługiwane wersje językowe gier i ich kodów kreskowych."""

    POLISH = "pl"
    ENGLISH = "en"

