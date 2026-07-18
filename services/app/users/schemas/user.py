"""Schematy Pydantic modułu users.

Wejściowe (UserCreate, UserUpdate) są ostre: limity długości zgodne z kolumnami
w models/User.py, extra="forbid" (nieznane pole w payloadzie → 422, nie ciche
zignorowanie). id i firebase_uid NIE występują w ŻADNYM schemacie — ani
wejściowym (nie da się ich ustawić), ani wyjściowym (nie da się ich zobaczyć).
Wewnętrzne identyfikatory nie opuszczają backendu; tożsamość zawsze z tokenu.

Wyjściowe rozdzielają widoki: UserProfile (właściciel) vs UserPublic (inni gracze).
"""

import unicodedata
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, EmailStr, StringConstraints

# ── Typy pól — jedna definicja ograniczeń na pole ─────────────────────────────

def _lowercase(value: object) -> object:
    return value.lower() if isinstance(value, str) else value


# Znaki przejmujące kierunek tekstu (RTL override itd.) — pozwalają wizualnie
# spoofować wizualny kierunek nazwy, więc blokujemy je twardo.
_BIDI_CONTROLS = frozenset(
    "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)


def _reject_control_chars(value: str) -> str:
    """Kategoria Cc (w tym \\x00, który wywala Postgresa) i znaki bidi → 422.
    Emoji, ZWJ i inne "zwykłe" Unicode przechodzą."""
    for ch in value:
        if unicodedata.category(ch) == "Cc" or ch in _BIDI_CONTROLS:
            raise ValueError("control characters are not allowed")
    return value


def _reject_control_chars_multiline(value: str) -> str:
    """Jak wyżej, ale \\n i \\t są legalne (bio może mieć akapity)."""
    for ch in value:
        if (unicodedata.category(ch) == "Cc" and ch not in "\n\t") or ch in _BIDI_CONTROLS:
            raise ValueError("control characters are not allowed")
    return value


# Techniczny identyfikator publiczny (tag): tylko [a-z0-9_], 3–30 znaków.
# BeforeValidator normalizuje wielkość liter PRZED patternem —
# "OmniSecura" przechodzi i ląduje jako "omnisecura".
Tag = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[a-z0-9_]{3,30}$"),
    BeforeValidator(_lowercase),
]
DisplayName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=80),
    AfterValidator(_reject_control_chars),
]
City = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=120),
    AfterValidator(_reject_control_chars),
]
Bio = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=2000),
    AfterValidator(_reject_control_chars_multiline),
]
# avatar_url celowo NIE ma typu wejściowego: zmiana avatara wyłącznie przez
# POST /me/avatar (upload) i DELETE /me/avatar — URL zawsze buduje backend
# ze swojego Storage, user nigdy nie wpisuje go sam.


class UserCreate(BaseModel):
    """WEWNĘTRZNY (core/auth → user_service) — pierwszy login.
    Nie jest wystawiony przez żaden endpoint."""

    model_config = ConfigDict(extra="forbid")

    firebase_uid: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    email: EmailStr | None = None
    # luźniejszy niż DisplayName (nazwy z Firebase bywają jednoznakowe),
    # ale znaki sterujące/bidi odpadają tak samo
    display_name: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
            AfterValidator(_reject_control_chars),
        ]
        | None
    ) = None


class UserUpdate(BaseModel):
    """Pola, które user może zmienić w SWOIM profilu (PUT /me).

    Pole pominięte w payloadzie = bez zmian; jawny null = wyczyszczenie pola
    (user_service używa model_dump(exclude_unset=True))."""

    model_config = ConfigDict(extra="forbid")

    # tag jest not-null w bazie — jawny null w payloadzie też ma być 422,
    # dlatego bez "| None"; pominięcie pola = bez zmian (exclude_unset).
    tag: Tag = None  # type: ignore[assignment]
    display_name: DisplayName | None = None
    city: City | None = None
    bio: Bio | None = None


class UserProfile(BaseModel):
    """Pełny profil — widzi wyłącznie właściciel (GET /me).

    Bez pól czysto backendowych: id, firebase_uid, is_active — one nie
    opuszczają bazy; is_active objawia się klientowi wyłącznie skutkami
    (403 user_inactive / 404 na publicznym profilu)."""

    model_config = ConfigDict(from_attributes=True)

    tag: str
    email: str | None
    display_name: str | None
    city: str | None
    bio: str | None
    avatar_url: str | None
    created_at: datetime  # "dołączył(a) X" we froncie


class UserPublic(BaseModel):
    """Profil widziany przez innych graczy — bez id, emaila i flag konta."""

    model_config = ConfigDict(from_attributes=True)

    tag: str
    display_name: str | None
    city: str | None
    bio: str | None
    avatar_url: str | None
    created_at: datetime  # "dołączył(a) X" we froncie
