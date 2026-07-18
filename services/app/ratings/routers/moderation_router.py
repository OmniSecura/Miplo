"""Administracyjna kolejka zgłoszonych recenzji."""

from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.orm import Session

from services.app.core.auth import get_admin_access
from services.app.core.database import get_db
from services.app.core.security.limiter import MODERATION_LIMIT, limiter
from services.app.ratings.schemas import HideReviewRequest, ReportedReviewModeration
from services.app.ratings.services import rating_service
from services.app.users.models import User

ratings_moderation_router = APIRouter(
    prefix="/admin/moderation/reviews",
    tags=["moderation"],
)


@ratings_moderation_router.get(
    "",
    response_model=list[ReportedReviewModeration],
    summary="Pobierz zgłoszone recenzje",
)
@limiter.limit(MODERATION_LIMIT)
def pending_reviews(
    request: Request,
    response: Response,
    limit: int = Query(default=100, ge=1, le=100),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> list[ReportedReviewModeration]:
    return rating_service.list_reported_reviews(db, limit)


@ratings_moderation_router.post(
    "/{rating_id}/hide",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Ukryj zgłoszoną ocenę",
)
@limiter.limit(MODERATION_LIMIT)
def hide_review(
    request: Request,
    response: Response,
    payload: HideReviewRequest,
    rating_id: UUID = Path(
        description="Publiczne UUID oceny/recenzji (`public_id` z odpowiedzi API)."
    ),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> None:
    rating_service.hide_rating(db, rating_id, payload)


@ratings_moderation_router.post(
    "/{rating_id}/restore",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Przywróć ocenę lub odrzuć zgłoszenie",
)
@limiter.limit(MODERATION_LIMIT)
def restore_review(
    request: Request,
    response: Response,
    rating_id: UUID = Path(
        description="Publiczne UUID oceny/recenzji (`public_id` z odpowiedzi API)."
    ),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> None:
    rating_service.restore_rating(db, rating_id)
