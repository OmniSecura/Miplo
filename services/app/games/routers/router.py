"""Publiczny katalog gier oraz chronione operacje BGG/custom/import."""

import secrets
from typing import Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    Path,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from services.app.core.auth import get_current_user, get_current_user_optional
from services.app.core.config import settings
from services.app.core.database import get_db
from services.app.core.errors import ApiError, ErrorCode
from services.app.core.security.limiter import (
    CATALOG_IMPORT_LIMIT,
    CUSTOM_GAME_LIMIT,
    DELETE_LIMIT,
    GALLERY_UPLOAD_LIMIT,
    MODEL_UPLOAD_LIMIT,
    READ_LIMIT,
    WRITE_LIMIT,
    limiter,
)
from services.app.games.schemas import (
    BarcodeAssign,
    BarcodeSubmission,
    CatalogImportResult,
    GameCreate,
    GameDetail,
    GameListItem,
    GameSearchResult,
    GameUpdate,
    GalleryImageCreate,
    GameImageSubmission,
    PaginatedGames,
)
from services.app.games.services import (
    box_generator_service,
    catalog_import_service,
    game_service,
)
from services.app.users.models import User
from services.app.shelf.services import shelf_service

games_router = APIRouter()

TAG_GAMES = ["games"]
TAG_BGG_GAMES = ["BGG games"]
TAG_CUSTOM_GAMES = ["custom games"]
TAG_GAME_GALLERY = ["game gallery"]
TAG_3D_MODELS = ["3D models"]


@games_router.get(
    "/games/search",
    response_model=list[GameSearchResult],
    tags=TAG_GAMES,
)
@limiter.limit(READ_LIMIT)
async def search_games(
    request: Request,
    response: Response,
    q: str = Query(min_length=2, max_length=100),
    db: Session = Depends(get_db),
) -> list[GameSearchResult]:
    return await game_service.search_games(db, q)


@games_router.get(
    "/games/bgg/{bgg_id}",
    response_model=GameDetail,
    tags=TAG_BGG_GAMES,
)
@limiter.limit(WRITE_LIMIT)
async def fetch_game_from_bgg(
    request: Request,
    response: Response,
    bgg_id: int = Path(ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GameDetail:
    game = await game_service.get_or_fetch_game(db, bgg_id)
    return game_service.to_detail(game)


@games_router.get(
    "/games/by-barcode/{barcode}",
    response_model=GameListItem,
    tags=TAG_GAMES,
)
@limiter.limit(READ_LIMIT)
def get_game_by_barcode(
    request: Request,
    response: Response,
    barcode: str = Path(min_length=8, max_length=13),
    db: Session = Depends(get_db),
) -> GameListItem:
    game = game_service.get_game_by_barcode(db, barcode)
    if game is None:
        raise ApiError.not_found(ErrorCode.BARCODE_NOT_FOUND)
    return game_service.to_list_item(game)


@games_router.post(
    "/games/import",
    response_model=CatalogImportResult,
    tags=TAG_BGG_GAMES,
)
@limiter.limit(CATALOG_IMPORT_LIMIT)
def import_games_catalog(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    x_import_key: str = Header(..., alias="X-Import-Key", min_length=32, max_length=256),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CatalogImportResult:
    """Operatorski, idempotentny import dumpa BGG CSV/JSON w batchach po 1000."""
    if not settings.GAMES_IMPORT_KEY:
        raise ApiError(503, ErrorCode.IMPORT_NOT_CONFIGURED)
    if not secrets.compare_digest(x_import_key, settings.GAMES_IMPORT_KEY):
        raise ApiError.forbidden(ErrorCode.INVALID_IMPORT_KEY)
    return catalog_import_service.import_catalog(db, file)


@games_router.get("/games", response_model=PaginatedGames, tags=TAG_GAMES)
@limiter.limit(READ_LIMIT)
def list_games(
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, min_length=2, max_length=100),
    players: int | None = Query(default=None, ge=1, le=50),
    game_type: str | None = Query(default=None, min_length=2, max_length=100),
    source: str | None = Query(default=None, pattern=r"^(bgg|custom)$"),
    include_expansions: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> PaginatedGames:
    return game_service.list_games(
        db,
        page,
        size,
        search,
        players,
        game_type,
        source,
        True,
        include_expansions,
    )


@games_router.post(
    "/games",
    response_model=GameDetail,
    status_code=status.HTTP_201_CREATED,
    tags=TAG_CUSTOM_GAMES,
)
@limiter.limit(CUSTOM_GAME_LIMIT)
async def create_custom_game(
    request: Request,
    response: Response,
    payload: GameCreate = Depends(GameCreate.as_form),
    cover: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GameDetail:
    game = await game_service.create_custom_game(db, payload, cover, current_user)
    return game_service.to_detail(game)


@games_router.post(
    "/games/{slug}/images",
    response_model=GameImageSubmission,
    status_code=status.HTTP_202_ACCEPTED,
    tags=TAG_GAME_GALLERY,
)
@limiter.limit(GALLERY_UPLOAD_LIMIT)
async def submit_game_image(
    request: Request,
    response: Response,
    slug: str = Path(min_length=1, max_length=200),
    payload: GalleryImageCreate = Depends(GalleryImageCreate.as_form),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GameImageSubmission:
    return await game_service.submit_gallery_image(db, slug, payload, file, current_user)


@games_router.delete(
    "/games/{slug}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=TAG_GAME_GALLERY,
)
@limiter.limit(DELETE_LIMIT)
def delete_game_image(
    request: Request,
    response: Response,
    slug: str = Path(min_length=1, max_length=200),
    image_id: UUID = Path(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    game_service.delete_gallery_image(db, slug, image_id, current_user)


@games_router.post(
    "/games/{slug}/3d-model",
    response_model=GameDetail,
    status_code=status.HTTP_202_ACCEPTED,
    tags=TAG_3D_MODELS,
)
@limiter.limit(MODEL_UPLOAD_LIMIT)
async def submit_3d_model(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    slug: str = Path(min_length=1, max_length=200),
    file_front: UploadFile | None = File(None),
    file_back: UploadFile | None = File(None),
    file_left: UploadFile | None = File(None),
    file_right: UploadFile | None = File(None),
    file_top: UploadFile | None = File(None),
    file_bottom: UploadFile | None = File(None),
    # multipart/form-data przesyła wartości pól jako tekst. Literal[int]
    # odrzucał poprawne "0", dlatego walidujemy string i konwertujemy dopiero
    # po przejściu allowlisty.
    rotation_front: Literal["0", "90", "180", "270"] = Form("0"),
    rotation_back: Literal["0", "90", "180", "270"] = Form("0"),
    rotation_left: Literal["0", "90", "180", "270"] = Form("0"),
    rotation_right: Literal["0", "90", "180", "270"] = Form("0"),
    rotation_top: Literal["0", "90", "180", "270"] = Form("0"),
    rotation_bottom: Literal["0", "90", "180", "270"] = Form("0"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GameDetail:
    game = game_service.assert_model_submission_allowed(db, slug, current_user)
    raw_sides = await box_generator_service.read_validated_sides(
        {
            "front": file_front,
            "back": file_back,
            "left": file_left,
            "right": file_right,
            "top": file_top,
            "bottom": file_bottom,
        }
    )
    game, job_id = game_service.begin_model_submission(db, slug, current_user)
    dimensions = (
        float(game.box_width or 29.5),
        float(game.box_height or 29.5),
        float(game.box_depth or 7.0),
    )
    rotations = {
        "front": int(rotation_front),
        "back": int(rotation_back),
        "left": int(rotation_left),
        "right": int(rotation_right),
        "top": int(rotation_top),
        "bottom": int(rotation_bottom),
    }
    background_tasks.add_task(
        box_generator_service.generate_and_upload,
        game.id,
        job_id,
        raw_sides,
        dimensions,
        rotations,
    )
    return game_service.to_detail(game)


@games_router.delete(
    "/games/{slug}/3d-model",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=TAG_3D_MODELS,
)
@limiter.limit(DELETE_LIMIT)
def delete_3d_model(
    request: Request,
    response: Response,
    slug: str = Path(min_length=1, max_length=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    game_service.delete_model_submission(db, slug, current_user)


@games_router.post(
    "/games/{slug}/barcodes",
    response_model=BarcodeSubmission,
    status_code=status.HTTP_202_ACCEPTED,
    tags=TAG_GAMES,
)
@limiter.limit(WRITE_LIMIT)
def propose_barcode_for_game(
    request: Request,
    response: Response,
    payload: BarcodeAssign = Depends(BarcodeAssign.as_form),
    slug: str = Path(min_length=1, max_length=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BarcodeSubmission:
    return game_service.propose_barcode(
        db,
        slug,
        payload.barcode,
        payload.language_code,
        current_user,
    )


@games_router.put(
    "/games/{slug}",
    response_model=GameDetail,
    tags=TAG_CUSTOM_GAMES,
)
@limiter.limit(WRITE_LIMIT)
async def update_custom_game(
    request: Request,
    response: Response,
    payload: GameUpdate = Depends(GameUpdate.as_form),
    cover: UploadFile | None = File(None),
    slug: str = Path(min_length=1, max_length=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GameDetail:
    game = await game_service.update_custom_game(db, slug, payload, cover, current_user)
    return game_service.to_detail(game)


@games_router.delete(
    "/games/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=TAG_CUSTOM_GAMES,
)
@limiter.limit(DELETE_LIMIT)
def delete_custom_game(
    request: Request,
    response: Response,
    slug: str = Path(min_length=1, max_length=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    game_service.delete_custom_game(db, slug, current_user)


@games_router.get("/games/{slug}", response_model=GameDetail, tags=TAG_GAMES)
@limiter.limit(READ_LIMIT)
def get_game_detail(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    slug: str = Path(min_length=1, max_length=200),
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> GameDetail:
    # "Brass Birmingham" i "brass-birmingham" trafiają w ten sam slug.
    game = game_service.get_game_by_slug(db, slug)
    if game is None:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    if not game.is_verified:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    if game_service.is_stale(game):
        background_tasks.add_task(game_service.refresh_game_by_id, game.id)
    shelf_item = (
        shelf_service.is_on_shelf(db, current_user.id, game.id)
        if current_user is not None
        else None
    )
    return game_service.to_detail(game, shelf_item)
