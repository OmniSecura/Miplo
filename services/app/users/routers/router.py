"""Endpointy modułu users. Zero SQLAlchemy — wszystko przez user_service.

Endpointy /me operują wyłącznie na userze zdjętym z tokenu (get_current_user),
więc cudzych danych nie da się tknąć nawet celowo — żaden payload nie zawiera
identyfikatora konta.
"""

from fastapi import APIRouter, Depends, File, Path, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from services.app.core.auth import (
    delete_firebase_account,
    get_current_user,
    get_current_user_allow_inactive,
)
from services.app.core.database import get_db
from services.app.core.errors import ApiError, ErrorCode
from services.app.core.security.limiter import (
    DELETE_LIMIT,
    READ_LIMIT,
    UPLOAD_LIMIT,
    WRITE_LIMIT,
    limiter,
)
from services.app.users.models import User
from services.app.users.schemas import UserProfile, UserPublic, UserUpdate
from services.app.users.services import avatar_service, user_service

users_router = APIRouter(tags=["users"])


@users_router.get("/me", response_model=UserProfile)
@limiter.limit(READ_LIMIT)
def get_my_profile(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


@users_router.put("/me", response_model=UserProfile)
@limiter.limit(WRITE_LIMIT)
def update_my_profile(
    request: Request,
    response: Response,
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    return user_service.update_profile(db, current_user, payload)


@users_router.post("/me/avatar", response_model=UserProfile)
@limiter.limit(UPLOAD_LIMIT)
async def upload_my_avatar(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Upload avatara (multipart/form-data, pole `file`).

    Celowo osobno od PUT /me (JSON): avatar_url NIE jest edytowalny przez
    JSON — zawsze pochodzi z naszego Storage, ustawiany przez backend.
    """
    avatar_url = await avatar_service.upload_avatar(file, current_user.firebase_uid)
    return user_service.update_avatar_url(db, current_user, avatar_url)


@users_router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(WRITE_LIMIT)
def delete_my_avatar(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Usuwa avatar: blob z bucketa (idempotentnie) + avatar_url = NULL."""
    avatar_service.delete_avatar(current_user.firebase_uid)
    user_service.update_avatar_url(db, current_user, None)


@users_router.post("/me/deactivate", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(DELETE_LIMIT)
def deactivate_my_account(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Soft delete (tymczasowy): tylko flaga is_active. Konto znika z widoków
    publicznych, dane zostają. Powrót: POST /me/activate."""
    user_service.deactivate(db, current_user)


@users_router.post("/me/activate", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(WRITE_LIMIT)
def activate_my_account(
    request: Request,
    response: Response,
    # celowo wariant allow_inactive — zwykła dependency rzuca 403 dla
    # nieaktywnych i reaktywacja byłaby niemożliwa
    current_user: User = Depends(get_current_user_allow_inactive),
    db: Session = Depends(get_db),
) -> None:
    """Reaktywacja konta po soft delete. Tożsamość z tokenu — user może
    reaktywować wyłącznie samego siebie."""
    user_service.activate(db, current_user)


@users_router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(DELETE_LIMIT)
def delete_my_account(
    request: Request,
    response: Response,
    # allow_inactive: prawo do bycia zapomnianym (RODO) działa też dla kont
    # zdeaktywowanych — 403 nie może blokować usunięcia danych
    current_user: User = Depends(get_current_user_allow_inactive),
    db: Session = Depends(get_db),
) -> None:
    """Twarde usunięcie konta (RODO/Apple): najpierw nasza baza, potem Firebase.

    Gdyby usunięcie w Firebase padło, dane osobowe z naszej bazy są już
    usunięte, a user przy następnym logowaniu dostanie świeży, pusty profil.
    """
    firebase_uid = current_user.firebase_uid
    user_service.delete_account(db, current_user)
    delete_firebase_account(firebase_uid)


@users_router.get("/users/{tag}", response_model=UserPublic)
@limiter.limit(READ_LIMIT)
def get_user_public_profile(
    request: Request,
    response: Response,
    tag: str = Path(pattern=r"^[a-z0-9_]{3,30}$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Publiczny profil innego gracza — po technicznym tagu
    (miplo.app/u/omnisecura), nigdy po wewnętrznym id."""
    user = user_service.get_public_profile(db, tag)
    if user is None:
        raise ApiError.not_found(ErrorCode.USER_NOT_FOUND)
    return user
