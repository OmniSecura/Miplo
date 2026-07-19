"""Współdzielone enumy domeny games — jeden kontrakt dla ORM, Pydantic i OpenAPI."""

from enum import Enum


class GameLanguage(str, Enum):
    """Obsługiwane wersje językowe gier i ich kodów kreskowych."""

    POLISH = "pl"
    ENGLISH = "en"


class CatalogImportMode(str, Enum):
    """Zakres aktualizacji wykonywanej przez operatorski import BGG."""

    UPDATE = "update"
    FULL = "full"


class GameTypeName(str, Enum):
    """Zamknięty katalog typów gier — jedyne wartości przyjmowane przez API.

    Swagger renderuje ten enum jako multi-select w formularzu custom gry,
    a mapa kategorii BGG tłumaczy się wyłącznie na te wartości.
    """

    STRATEGIA = "Strategia"
    EURO = "Euro"
    EKONOMICZNA = "Ekonomiczna"
    FAMILIJNA = "Familijna"
    IMPREZOWA = "Imprezowa"
    KARCIANA = "Karciana"
    KOSCIANA = "Kościana"
    ABSTRAKCYJNA = "Abstrakcyjna"
    WOJENNA = "Wojenna"
    BITEWNA = "Bitewna"
    PRZYGODOWA = "Przygodowa"
    EKSPLORACJA = "Eksploracja"
    KOOPERACYJNA = "Kooperacyjna"
    FANTASY = "Fantasy"
    SCI_FI = "Sci-Fi"
    HORROR = "Horror"
    LOGICZNA = "Logiczna"
    DEDUKCJA = "Dedukcja"
    DLA_DZIECI = "Dla dzieci"
    QUIZ = "Quiz"
    SLOWNA = "Słowna"
    SPORTOWA = "Sportowa"
    WYSCIGOWA = "Wyścigowa"
    HUMOR = "Humor"
    CYWILIZACJA = "Cywilizacja"
    ROLNICTWO = "Rolnictwo"
    PRZEMYSL_PRODUKCJA = "Przemysł / Produkcja"
    BUDOWA_MIASTA = "Budowa Miasta"
    BUDOWA_TERYTORIUM = "Budowa Terytorium"
