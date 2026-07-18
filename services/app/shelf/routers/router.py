"""Endpointy własnej i publicznej półki użytkownika."""

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.orm import Session

from services.app.core.auth import get_current_user
from services.app.core.database import get_db
from services.app.core.security.limiter import (
    COLLECTION_IMPORT_LIMIT,
    DELETE_LIMIT,
    READ_LIMIT,
    WRITE_LIMIT,
    limiter,
)
from services.app.shelf.enums import ShelfCondition, ShelfSort
from services.app.shelf.schemas import (
    CollectionImportRequest,
    CollectionImportResult,
    PaginatedPublicShelf,
    PaginatedShelf,
    ShelfItemCreate,
    ShelfItemResponse,
    ShelfItemUpdate,
    ShelfStats,
)
from services.app.shelf.services import shelf_service
from services.app.users.models import User

shelf_router = APIRouter(tags=["shelf"])


@shelf_router.get("/me/shelf", response_model=PaginatedShelf)
@limiter.limit(READ_LIMIT)
def get_my_shelf(
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    lendable: bool | None = Query(default=None),
    search: str | None = Query(default=None, min_length=2, max_length=100),
    condition: ShelfCondition | None = Query(default=None),
    players: int | None = Query(default=None, ge=1, le=50),
    sort: ShelfSort = Query(default=ShelfSort.ADDED_AT),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedShelf:
    return shelf_service.get_my_shelf(
        db,
        current_user.id,
        page,
        size,
        lendable=lendable,
        search=search,
        condition=condition,
        players=players,
        sort=sort,
    )


@shelf_router.post(
    "/me/shelf",
    response_model=ShelfItemResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(WRITE_LIMIT)
def add_to_my_shelf(
    request: Request,
    response: Response,
    payload: ShelfItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShelfItemResponse:
    item = shelf_service.add_to_shelf(db, current_user.id, payload)
    return shelf_service.to_response(item)


@shelf_router.get("/me/shelf/stats", response_model=ShelfStats)
@limiter.limit(READ_LIMIT)
def get_my_shelf_stats(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShelfStats:
    return shelf_service.get_shelf_stats(db, current_user.id)


@shelf_router.post("/me/shelf/import", response_model=CollectionImportResult)
@limiter.limit(COLLECTION_IMPORT_LIMIT)
async def import_my_bgg_collection(
    request: Request,
    response: Response,
    payload: CollectionImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CollectionImportResult:
    return await shelf_service.import_bgg_collection(db, current_user.id, payload)


@shelf_router.put("/me/shelf/{game_slug}", response_model=ShelfItemResponse)
@limiter.limit(WRITE_LIMIT)
def update_my_shelf_item(
    request: Request,
    response: Response,
    payload: ShelfItemUpdate,
    game_slug: str = Path(
        min_length=1,
        max_length=200,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        examples=["brass-birmingham"],
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShelfItemResponse:
    item = shelf_service.update_shelf_item(db, current_user.id, game_slug, payload)
    return shelf_service.to_response(item)


@shelf_router.delete(
    "/me/shelf/{game_slug}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit(DELETE_LIMIT)
def remove_from_my_shelf(
    request: Request,
    response: Response,
    game_slug: str = Path(
        min_length=1,
        max_length=200,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        examples=["brass-birmingham"],
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    shelf_service.remove_from_shelf(db, current_user.id, game_slug)


@shelf_router.get("/users/{tag}/shelf", response_model=PaginatedPublicShelf)
@limiter.limit(READ_LIMIT)
def get_public_user_shelf(
    request: Request,
    response: Response,
    tag: str = Path(min_length=3, max_length=30, pattern=r"^[a-z0-9_]+$"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    lendable: bool | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedPublicShelf:
    return shelf_service.get_user_shelf(
        db,
        tag,
        page,
        size,
        lendable=lendable,
    )
