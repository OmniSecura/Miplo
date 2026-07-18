"""Publiczne i prywatne endpointy ocen oraz recenzji Miplo."""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.orm import Session

from services.app.core.auth import get_current_user, get_current_user_optional
from services.app.core.database import get_db
from services.app.core.errors import ApiError, ErrorCode
from services.app.core.messages import ApiMessage, MessageCode
from services.app.core.security.limiter import (
    DELETE_LIMIT,
    RATING_WRITE_LIMIT,
    READ_LIMIT,
    REVIEW_REPORT_LIMIT,
    limiter,
)
from services.app.ratings.enums import RatingSort
from services.app.ratings.schemas import (
    GameRatingsSummary,
    PaginatedMyRatings,
    PaginatedRatings,
    RatingCreate,
    RatingResponse,
    RatingUpdate,
    ReviewReportCreate,
    UserRatingStats,
)
from services.app.ratings.services import rating_service
from services.app.users.models import User

ratings_router = APIRouter(tags=["ratings"])


@ratings_router.get(
    "/games/{slug}/ratings/summary",
    response_model=GameRatingsSummary,
    summary="Pobierz podsumowanie ocen gry",
)
@limiter.limit(READ_LIMIT)
def ratings_summary(
    request: Request,
    response: Response,
    slug: str = Path(min_length=1, max_length=200),
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> GameRatingsSummary:
    return rating_service.get_ratings_summary(
        db,
        slug,
        current_user.id if current_user is not None else None,
    )


@ratings_router.get(
    "/games/{slug}/ratings",
    response_model=PaginatedRatings,
    summary="Pobierz oceny i recenzje gry",
)
@limiter.limit(READ_LIMIT)
def list_game_ratings(
    request: Request,
    response: Response,
    slug: str = Path(min_length=1, max_length=200),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
    with_review: bool | None = Query(default=None),
    min_rating: Decimal | None = Query(
        default=None, ge=Decimal("1"), le=Decimal("10"), multiple_of=Decimal("0.5")
    ),
    max_rating: Decimal | None = Query(
        default=None, ge=Decimal("1"), le=Decimal("10"), multiple_of=Decimal("0.5")
    ),
    sort: RatingSort = Query(default=RatingSort.NEWEST),
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> PaginatedRatings:
    if min_rating is not None and max_rating is not None and min_rating > max_rating:
        raise ApiError(422, ErrorCode.INVALID_RATING_VALUE)
    return rating_service.get_game_ratings(
        db,
        slug,
        page,
        size,
        with_review=with_review,
        min_rating=min_rating,
        max_rating=max_rating,
        sort=sort,
    )


@ratings_router.post(
    "/games/{slug}/ratings",
    response_model=RatingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Wystaw ocenę gry",
)
@limiter.limit(RATING_WRITE_LIMIT)
def rate_game(
    request: Request,
    response: Response,
    payload: RatingCreate,
    slug: str = Path(min_length=1, max_length=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RatingResponse:
    item = rating_service.rate_game(db, current_user.id, slug, payload)
    return rating_service.to_response(item)


@ratings_router.put(
    "/games/{slug}/ratings",
    response_model=RatingResponse,
    summary="Edytuj moją ocenę gry",
)
@limiter.limit(RATING_WRITE_LIMIT)
def update_rating(
    request: Request,
    response: Response,
    payload: RatingUpdate,
    slug: str = Path(min_length=1, max_length=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RatingResponse:
    item = rating_service.update_rating(db, current_user.id, slug, payload)
    return rating_service.to_response(item)


@ratings_router.delete(
    "/games/{slug}/ratings",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Usuń moją ocenę gry",
)
@limiter.limit(DELETE_LIMIT)
def delete_rating(
    request: Request,
    response: Response,
    slug: str = Path(min_length=1, max_length=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    rating_service.delete_rating(db, current_user.id, slug)


@ratings_router.post(
    "/games/{slug}/ratings/{rating_id}/report",
    response_model=ApiMessage,
    summary="Zgłoś recenzję po jej public_id",
)
@limiter.limit(REVIEW_REPORT_LIMIT)
def report_review(
    request: Request,
    response: Response,
    payload: ReviewReportCreate,
    slug: str = Path(min_length=1, max_length=200),
    rating_id: UUID = Path(
        description="Publiczne UUID oceny/recenzji (`public_id` z odpowiedzi API)."
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiMessage:
    rating_service.report_review(db, current_user.id, slug, rating_id, payload)
    return ApiMessage(message_code=MessageCode.REVIEW_REPORTED)


@ratings_router.get(
    "/me/ratings/stats",
    response_model=UserRatingStats,
    summary="Pobierz statystyki moich ocen",
)
@limiter.limit(READ_LIMIT)
def my_rating_stats(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserRatingStats:
    return rating_service.get_user_rating_stats(db, current_user.id)


@ratings_router.get(
    "/me/ratings",
    response_model=PaginatedMyRatings,
    summary="Pobierz moje oceny",
)
@limiter.limit(READ_LIMIT)
def my_ratings(
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
    with_review: bool | None = Query(default=None),
    sort: RatingSort = Query(default=RatingSort.NEWEST),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedMyRatings:
    return rating_service.get_my_ratings(
        db,
        current_user.id,
        page,
        size,
        with_review=with_review,
        sort=sort,
    )


@ratings_router.get(
    "/users/{tag}/ratings",
    response_model=PaginatedRatings,
    summary="Pobierz publiczne oceny usera",
)
@limiter.limit(READ_LIMIT)
def user_ratings(
    request: Request,
    response: Response,
    tag: str = Path(pattern=r"^[a-z0-9_]{3,30}$"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
    with_review: bool | None = Query(default=None),
    sort: RatingSort = Query(default=RatingSort.NEWEST),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedRatings:
    return rating_service.get_user_ratings(
        db,
        tag,
        page,
        size,
        with_review=with_review,
        sort=sort,
    )
