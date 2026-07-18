"""Jedyne miejsce w kodzie, które wie o istnieniu Firebase (decyzja 0001).

Reszta aplikacji dostaje z get_current_user gotowego, lokalnego Usera z bazy.
Tożsamość ZAWSZE pochodzi ze zweryfikowanego tokenu — nigdy z payloadu requestu.
"""

import logging
import secrets

import firebase_admin
from fastapi import Depends, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from firebase_admin import exceptions as firebase_exceptions
from pydantic import ValidationError
from sqlalchemy.orm import Session

from services.app.core.config import settings
from services.app.core.database import get_db
from services.app.core.errors import ApiError, ErrorCode
from services.app.users.models import User
from services.app.users.schemas import UserCreate
from services.app.users.services import user_service

logger = logging.getLogger(__name__)

# auto_error=False: brak nagłówka obsługujemy sami, bo domyślne zachowanie
# HTTPBearer to 403 — a brak tokenu to semantycznie 401.
_bearer_scheme = HTTPBearer(auto_error=False)
_admin_key_scheme = APIKeyHeader(name="X-Admin-Key", auto_error=False)


def init_firebase() -> None:
    """Inicjalizacja firebase-admin — wołana raz, przy starcie aplikacji (lifespan).

    Fail-fast: brak lub zły klucz wywala start serwera, nie pierwszy request.
    """
    if not firebase_admin._apps:
        cred = credentials.Certificate(settings.FIREBASE_ADMIN_CREDENTIALS)
        firebase_admin.initialize_app(cred)


def get_current_user_allow_inactive(
    request: Request,
    bearer: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Jak get_current_user, ale NIE odrzuca kont zdeaktywowanych.

    Wyłącznie dla endpointów, które muszą działać na nieaktywnym koncie
    (POST /me/activate — inaczej deaktywacja byłaby nieodwracalna).
    Wzorzec "znajdź albo utwórz": przy pierwszym logowaniu zakładamy rekord
    w naszej bazie na podstawie danych z tokenu — endpoint rejestracji nie istnieje.
    """
    if bearer is None:
        raise ApiError.unauthorized()  # brak tokenu → generyczne "unauthorized"

    try:
        # check_revoked=True jest kluczowe po wylogowaniu globalnym, blokadzie
        # lub usunięciu konta. Bez tego poprawnie podpisany token pozostałby
        # użyteczny aż do naturalnego wygaśnięcia.
        decoded = firebase_auth.verify_id_token(
            bearer.credentials,
            check_revoked=True,
        )
    except firebase_auth.ExpiredIdTokenError:
        # osobny kod — frontend wie, że wystarczy odświeżyć token przez SDK
        raise ApiError.unauthorized(ErrorCode.TOKEN_EXPIRED)
    except (
        firebase_auth.RevokedIdTokenError,
        firebase_auth.UserDisabledError,
        firebase_auth.UserNotFoundError,
    ):
        raise ApiError.unauthorized(ErrorCode.TOKEN_REVOKED)
    except (firebase_auth.InvalidIdTokenError, ValueError):
        # ValueError = token niebędący w ogóle JWT.
        raise ApiError.unauthorized(ErrorCode.INVALID_TOKEN)
    except firebase_exceptions.FirebaseError:
        logger.exception("Firebase Auth jest chwilowo niedostępny")
        raise ApiError(503, ErrorCode.AUTH_PROVIDER_UNAVAILABLE)

    firebase_uid: str = decoded["uid"]

    user = user_service.get_by_firebase_uid(db, firebase_uid)
    if user is None:
        # Firebase nie ogranicza długości "name" — przycinamy do rozmiaru kolumny.
        display_name = (decoded.get("name") or "").strip()[:80] or None
        try:
            payload = UserCreate(
                firebase_uid=firebase_uid,
                email=decoded.get("email"),
                display_name=display_name,
            )
        except ValidationError:
            # Zepsute dane w tokenie (dziwny email, znaki sterujące w name)
            # nie mogą blokować pierwszego logowania — konto powstaje puste,
            # user uzupełni profil przez PUT /me.
            payload = UserCreate(firebase_uid=firebase_uid)
        user = user_service.create_from_firebase(db, payload)

    # Klucz dla rate-limitera: zalogowani liczeni per konto, nie per IP.
    request.state.firebase_uid = firebase_uid
    return user


def get_current_user(
    user: User = Depends(get_current_user_allow_inactive),
) -> User:
    """Standardowa dependency dla endpointów: zweryfikowany, AKTYWNY user."""
    if not user.is_active:
        raise ApiError.forbidden(ErrorCode.USER_INACTIVE)
    return user


def get_current_user_optional(
    request: Request,
    bearer: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Opcjonalny kontekst aktywnego usera dla publicznych endpointów.

    Brak nagłówka oznacza anonimowego klienta. Podany, ale niepoprawny token nie
    jest ignorowany — przechodzi przez standardową walidację i zwraca 401.
    """
    if bearer is None:
        if request.headers.get("authorization"):
            raise ApiError.unauthorized(ErrorCode.INVALID_TOKEN)
        return None
    user = get_current_user_allow_inactive(request, bearer, db)
    if not user.is_active:
        raise ApiError.forbidden(ErrorCode.USER_INACTIVE)
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Aktywny lokalny administrator; roli nie da się ustawić przez API."""
    if not user.is_admin:
        raise ApiError.forbidden(ErrorCode.ADMIN_REQUIRED)
    return user


def get_admin_access(
    request: Request,
    api_key: str | None = Depends(_admin_key_scheme),
    bearer: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Administrator przez X-Admin-Key albo aktywne konto Firebase z is_admin.

    Podany klucz ma pierwszeństwo: błędnego klucza nie wolno „ratować” drugim
    mechanizmem, bo maskowałoby to pomyłki i utrudniało wykrywanie ataków.
    Zwracane ``None`` oznacza autoryzację kluczem operatorskim.
    """
    if api_key is not None:
        configured_key = settings.ADMIN_API_KEY
        if configured_key is None:
            raise ApiError(503, ErrorCode.ADMIN_API_KEY_NOT_CONFIGURED)
        if not secrets.compare_digest(api_key, configured_key):
            raise ApiError(401, ErrorCode.INVALID_ADMIN_API_KEY)

        # Stabilny, niejawny identyfikator dla rate limitera. Nigdy sam sekret.
        request.state.firebase_uid = "admin-api-key"
        request.state.admin_actor = "shared-api-key"
        return None

    user = get_current_user_allow_inactive(request, bearer, db)
    if not user.is_active:
        raise ApiError.forbidden(ErrorCode.USER_INACTIVE)
    admin = get_current_admin(user)
    request.state.admin_actor = f"user:{admin.tag}"
    return admin


def prepare_firebase_account_deletion(firebase_uid: str) -> None:
    """Najpierw blokuje konto i unieważnia refresh tokeny.

    Dzięki temu żaden istniejący token nie odtworzy lokalnego profilu w oknie
    między usunięciem danych SQL a finalnym usunięciem konta Firebase.
    """
    disabled = False
    try:
        firebase_auth.update_user(firebase_uid, disabled=True)
        disabled = True
        firebase_auth.revoke_refresh_tokens(firebase_uid)
    except firebase_auth.UserNotFoundError:
        return
    except firebase_exceptions.FirebaseError:
        logger.exception("Nie udało się przygotować konta Firebase do usunięcia")
        if disabled:
            # Nie zostawiamy usera z danymi SQL i przypadkowo zablokowanym
            # kontem, gdy drugi krok przygotowania zawiódł.
            restore_firebase_account_after_failed_deletion(firebase_uid)
        raise ApiError(503, ErrorCode.AUTH_PROVIDER_UNAVAILABLE)


def restore_firebase_account_after_failed_deletion(firebase_uid: str) -> None:
    """Best-effort rollback blokady, jeśli usunięcie danych SQL nie powiodło się."""
    try:
        firebase_auth.update_user(firebase_uid, disabled=False)
    except firebase_auth.UserNotFoundError:
        return
    except firebase_exceptions.FirebaseError:
        logger.exception("Nie udało się cofnąć blokady konta Firebase")


def finalize_firebase_account_deletion(firebase_uid: str) -> None:
    """Finalnie usuwa tożsamość; brak konta jest sukcesem idempotentnym.

    Awaria po trwałym usunięciu SQL jest logowana, ale konto pozostaje disabled,
    a jego tokeny są odwołane, więc nie może odtworzyć lokalnego użytkownika.
    """
    try:
        firebase_auth.delete_user(firebase_uid)
    except firebase_auth.UserNotFoundError:
        return
    except firebase_exceptions.FirebaseError:
        logger.exception("Nie udało się finalnie usunąć konta Firebase")
