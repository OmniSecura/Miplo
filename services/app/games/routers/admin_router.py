"""Operatorskie operacje katalogu BGG — nigdy część zwykłego frontendu."""

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from sqlalchemy.orm import Session

from services.app.core.auth import get_admin_access
from services.app.core.database import get_db
from services.app.core.security.limiter import CATALOG_IMPORT_LIMIT, limiter
from services.app.games.enums import CatalogImportMode
from services.app.games.schemas import CatalogImportResult
from services.app.games.services import catalog_import_service
from services.app.users.models import User

admin_games_router = APIRouter(prefix="/admin/games", tags=["administration"])


@admin_games_router.post(
    "/import",
    response_model=CatalogImportResult,
    summary="Zaimportuj lub zaktualizuj katalog BGG z CSV",
)
@limiter.limit(CATALOG_IMPORT_LIMIT)
def import_games_catalog(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    mode: CatalogImportMode = Form(default=CatalogImportMode.UPDATE),
    admin: User | None = Depends(get_admin_access),
    db: Session = Depends(get_db),
) -> CatalogImportResult:
    """Admin-only import dumpa BGG; tryb update nie dotyka danych Miplo."""
    return catalog_import_service.import_catalog(db, file, mode)
