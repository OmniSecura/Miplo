"""Chroniona kolejka moderacji gier, galerii, modeli 3D i barcode."""

from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.orm import Session

from services.app.core.auth import get_admin_access
from services.app.core.database import get_db
from services.app.core.security.limiter import MODERATION_LIMIT, limiter
from services.app.games.schemas import (
    GameDetail,
    PendingBarcodeModeration,
    PendingImageModeration,
    PendingGameModeration,
    PendingModelModeration,
)
from services.app.games.services import moderation_service
from services.app.users.models import User

moderation_router = APIRouter(prefix="/admin/moderation", tags=["moderation"])


@moderation_router.get(
    "/games",
    response_model=list[PendingGameModeration],
    summary="Pobierz gry oczekujące na moderację",
)
@limiter.limit(MODERATION_LIMIT)
def pending_games(
    request: Request,
    response: Response,
    limit: int = Query(default=100, ge=1, le=100),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> list[PendingGameModeration]:
    return moderation_service.list_pending_games(db, limit)


@moderation_router.post(
    "/games/{slug}/approve",
    response_model=GameDetail,
    summary="Zaakceptuj grę",
)
@limiter.limit(MODERATION_LIMIT)
def approve_game(
    request: Request,
    response: Response,
    slug: str = Path(min_length=1, max_length=200),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> GameDetail:
    return moderation_service.approve_game(db, slug)


@moderation_router.delete(
    "/games/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Odrzuć grę",
)
@limiter.limit(MODERATION_LIMIT)
def reject_game(
    request: Request,
    response: Response,
    slug: str = Path(min_length=1, max_length=200),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> None:
    moderation_service.reject_game(db, slug)


@moderation_router.post(
    "/games/{slug}/contributions/lock",
    response_model=GameDetail,
    summary="Zablokuj kontrybucje do gry",
)
@limiter.limit(MODERATION_LIMIT)
def lock_contributions(
    request: Request,
    response: Response,
    slug: str = Path(min_length=1, max_length=200),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> GameDetail:
    return moderation_service.set_contributions_enabled(db, slug, False)


@moderation_router.post(
    "/games/{slug}/contributions/unlock",
    response_model=GameDetail,
    summary="Odblokuj kontrybucje do gry",
)
@limiter.limit(MODERATION_LIMIT)
def unlock_contributions(
    request: Request,
    response: Response,
    slug: str = Path(min_length=1, max_length=200),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> GameDetail:
    return moderation_service.set_contributions_enabled(db, slug, True)


@moderation_router.get(
    "/images",
    response_model=list[PendingImageModeration],
    summary="Pobierz zdjęcia oczekujące na moderację",
)
@limiter.limit(MODERATION_LIMIT)
def pending_images(
    request: Request,
    response: Response,
    limit: int = Query(default=100, ge=1, le=100),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> list[PendingImageModeration]:
    return moderation_service.list_pending_images(db, limit)


@moderation_router.post(
    "/images/{image_id}/approve",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Zaakceptuj zdjęcie gry",
)
@limiter.limit(MODERATION_LIMIT)
def approve_image(
    request: Request,
    response: Response,
    image_id: UUID = Path(),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> None:
    moderation_service.approve_image(db, image_id)


@moderation_router.delete(
    "/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Odrzuć zdjęcie gry",
)
@limiter.limit(MODERATION_LIMIT)
def reject_image(
    request: Request,
    response: Response,
    image_id: UUID = Path(),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> None:
    moderation_service.reject_image(db, image_id)


@moderation_router.get(
    "/barcodes",
    response_model=list[PendingBarcodeModeration],
    summary="Pobierz barcode oczekujące na moderację",
)
@limiter.limit(MODERATION_LIMIT)
def pending_barcodes(
    request: Request,
    response: Response,
    limit: int = Query(default=100, ge=1, le=100),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> list[PendingBarcodeModeration]:
    return moderation_service.list_pending_barcodes(db, limit)


@moderation_router.post(
    "/barcodes/{barcode_id}/approve",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Zaakceptuj barcode gry",
)
@limiter.limit(MODERATION_LIMIT)
def approve_barcode(
    request: Request,
    response: Response,
    barcode_id: UUID = Path(),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> None:
    moderation_service.approve_barcode(db, barcode_id)


@moderation_router.delete(
    "/barcodes/{barcode_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Odrzuć barcode gry",
)
@limiter.limit(MODERATION_LIMIT)
def reject_barcode(
    request: Request,
    response: Response,
    barcode_id: UUID = Path(),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> None:
    moderation_service.reject_barcode(db, barcode_id)


@moderation_router.get(
    "/models",
    response_model=list[PendingModelModeration],
    summary="Pobierz modele 3D oczekujące na moderację",
)
@limiter.limit(MODERATION_LIMIT)
def pending_models(
    request: Request,
    response: Response,
    limit: int = Query(default=100, ge=1, le=100),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> list[PendingModelModeration]:
    return moderation_service.list_pending_models(db, limit)


@moderation_router.post(
    "/models/{slug}/approve",
    response_model=GameDetail,
    summary="Zaakceptuj model 3D gry",
)
@limiter.limit(MODERATION_LIMIT)
def approve_model(
    request: Request,
    response: Response,
    slug: str = Path(min_length=1, max_length=200),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> GameDetail:
    return moderation_service.approve_model(db, slug)


@moderation_router.delete(
    "/models/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Odrzuć model 3D gry",
)
@limiter.limit(MODERATION_LIMIT)
def reject_model(
    request: Request,
    response: Response,
    slug: str = Path(min_length=1, max_length=200),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> None:
    moderation_service.reject_model(db, slug)
