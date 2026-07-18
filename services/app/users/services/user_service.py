"""Warstwa service modułu users — JEDYNE miejsce operacji na bazie i commitów.

Routery i core/auth nie dotykają SQLAlchemy bezpośrednio. Inne moduły domenowe
(games, shelf, matchmaking...) też mają rozmawiać z users wyłącznie przez ten
plik — patrz docs/architecture.md.

Funkcje modyfikujące przyjmują obiekt User (a nie identyfikator) tam, gdzie
chodzi o "mojego" usera — obiekt pochodzi z get_current_user, więc nie da się
przez pomyłkę zoperować na cudzym koncie.
"""

import logging
import re
import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.app.core.errors import ApiError, ErrorCode
from services.app.users.models import User
from services.app.users.schemas import UserCreate, UserUpdate
from services.app.users.services import avatar_service

logger = logging.getLogger(__name__)

# ── Odczyty ───────────────────────────────────────────────────────────────────


def get_by_firebase_uid(db: Session, firebase_uid: str) -> User | None:
    """Używane przez get_current_user przy każdym requeście."""
    return db.scalar(select(User).where(User.firebase_uid == firebase_uid))


def get_by_tag(db: Session, tag: str) -> User | None:
    return db.scalar(select(User).where(User.tag == tag))


def get_public_profile(db: Session, tag: str) -> User | None:
    """Publiczny widok po tagu — nieaktywne konta są niewidoczne
    (router zwraca 404)."""
    return db.scalar(
        select(User).where(User.tag == tag, User.is_active.is_(True))
    )


# ── Tag: generowanie przy pierwszym logowaniu ─────────────────────────────────


def _generate_tag(db: Session, data: UserCreate) -> str:
    """Techniczny tag z danych tokenu: część maila przed @ albo
    display_name, znormalizowane do [a-z0-9_]. Kolizja → losowy sufiks.
    User może to potem zmienić przez PUT /me."""
    raw = (data.email or "").split("@")[0] or (data.display_name or "")
    raw = re.sub(r"[\s.\-]+", "_", raw.lower())  # spacje/kropki/myślniki → _
    base = re.sub(r"[^a-z0-9_]", "", raw)[:24]
    if len(base) < 3:
        base = f"gracz_{secrets.token_hex(3)}"

    candidate = base
    while get_by_tag(db, candidate) is not None:
        candidate = f"{base}_{secrets.token_hex(2)}"
    return candidate


# ── Zapisy (jedyne miejsce z commitami) ──────────────────────────────────────


def create_from_firebase(db: Session, data: UserCreate) -> User:
    """Pierwsze logowanie — zakłada lokalny rekord z danych tokenu."""
    # 3 podejścia: wyścig na tag (dwóch nowych userów bierze ten sam
    # wygenerowany tag naraz) rozwiązuje nowy losowy sufiks.
    for _ in range(3):
        user = User(**data.model_dump(), tag=_generate_tag(db, data))
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            # Wyścig dwóch równoległych "pierwszych" requestów TEGO SAMEGO
            # usera: przegrany bierze rekord założony przez wygranego.
            existing = get_by_firebase_uid(db, data.firebase_uid)
            if existing is not None:
                return existing
            continue  # kolizja tagu — losujemy nowy sufiks
        db.refresh(user)
        return user

    raise RuntimeError("Nie udało się wygenerować unikalnego tagu po 3 próbach")


def update_profile(db: Session, user: User, data: UserUpdate) -> User:
    # exclude_unset: pole nieobecne w payloadzie = bez zmian,
    # jawny null = wyczyszczenie pola (tag nie przyjmuje null — 422 w schemacie).
    changes = data.model_dump(exclude_unset=True)

    new_tag = changes.get("tag")
    if new_tag and new_tag != user.tag:
        if get_by_tag(db, new_tag) is not None:
            raise ApiError.conflict(ErrorCode.TAG_TAKEN)

    for field, value in changes.items():
        setattr(user, field, value)
    try:
        db.commit()
    except IntegrityError:
        # wyścig: ktoś zajął tag między SELECT a commitem
        db.rollback()
        raise ApiError.conflict(ErrorCode.TAG_TAKEN)
    db.refresh(user)
    return user


def deactivate(db: Session, user: User) -> User:
    """Soft delete — konto znika z widoków publicznych, dane zostają.
    Odwracalne przez activate()."""
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user


def activate(db: Session, user: User) -> User:
    """Reaktywacja po soft delete — konto wraca do widoków publicznych."""
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user


def update_avatar_url(db: Session, user: User, avatar_url: str | None) -> User:
    """Jedyna droga zmiany avatar_url — wołane wyłącznie przez endpointy
    avatara. URL zawsze pochodzi z naszego Storage, nigdy od usera."""
    user.avatar_url = avatar_url
    db.commit()
    db.refresh(user)
    return user


def delete_account(db: Session, user: User) -> None:
    """Twarde usunięcie danych lokalnych (RODO / wymóg Apple).

    Router przed tą operacją blokuje Firebase i odwołuje sesje, a po udanym
    commicie finalizuje usunięcie tożsamości Firebase.
    """
    # Avatar z bucketa: padnięcie Storage NIE blokuje usunięcia konta —
    # dane osobowe z bazy są ważniejsze niż osierocony plik (do posprzątania).
    try:
        avatar_service.delete_avatar(user.firebase_uid)
    except Exception:
        logger.warning(
            "Nie udało się usunąć avatara z Storage — plik osierocony",
            exc_info=True,
        )
    # ON DELETE CASCADE usuwa oceny, ale denormalizowane agregaty gier trzeba
    # przeliczyć po flushu, inaczej pozostałyby zawyżone po usunięciu konta.
    from services.app.ratings.models import GameRating
    from services.app.ratings.services import rating_service

    affected_game_ids = set(
        db.scalars(
            select(GameRating.game_id).where(GameRating.user_id == user.id)
        ).all()
    )
    db.delete(user)
    db.flush()
    rating_service.recalculate_batch(db, affected_game_ids)
    db.commit()
