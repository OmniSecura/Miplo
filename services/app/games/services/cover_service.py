"""Bezpieczne przetwarzanie okładek customowych gier."""

import io
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import UploadFile
from google.cloud.exceptions import NotFound
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from services.app.core.errors import ApiError, ErrorCode
from services.app.core.storage import get_bucket

logger = logging.getLogger(__name__)

MAX_COVER_SIZE = 2 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000
MAX_COVER_DIMENSION = 800
WEBP_QUALITY = 85
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
_CHUNK_SIZE = 64 * 1024


def _cover_path(game_id: int) -> str:
    return f"games/{game_id}/cover.webp"


def candidate_path(game_id: int) -> str:
    return f"games/{game_id}/submissions/covers/{uuid4()}.webp"


async def _read_limited(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_CHUNK_SIZE):
        total += len(chunk)
        if total > MAX_COVER_SIZE:
            raise ApiError.bad_request(
                ErrorCode.FILE_TOO_LARGE,
                details={"max_bytes": MAX_COVER_SIZE},
            )
        chunks.append(chunk)
    if not chunks:
        raise ApiError.bad_request(ErrorCode.INVALID_FILE_TYPE)
    return b"".join(chunks)


def _optimize(data: bytes) -> bytes:
    try:
        image = Image.open(io.BytesIO(data))
        if image.format not in ALLOWED_IMAGE_FORMATS:
            raise ApiError.bad_request(ErrorCode.INVALID_FILE_TYPE)
        width, height = image.size
        if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
            raise ApiError.bad_request(
                ErrorCode.FILE_TOO_LARGE,
                details={"max_pixels": MAX_IMAGE_PIXELS},
            )
        image.seek(0)
        image.load()
    except ApiError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise ApiError.bad_request(ErrorCode.INVALID_FILE_TYPE)

    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "PA") or (
        image.mode == "P" and "transparency" in image.info
    ):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        image = background
    else:
        image = image.convert("RGB")

    image.thumbnail((MAX_COVER_DIMENSION, MAX_COVER_DIMENSION), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="WEBP", quality=WEBP_QUALITY, method=6)
    return output.getvalue()


async def prepare_cover(file: UploadFile) -> bytes:
    """Waliduje trzy warstwy i zwraca wyłącznie bezpieczny, przepisany WEBP."""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise ApiError.bad_request(ErrorCode.INVALID_FILE_TYPE)
    raw = await _read_limited(file)
    return await run_in_threadpool(_optimize, raw)


def _upload(game_id: int, webp: bytes) -> str:
    blob = get_bucket().blob(_cover_path(game_id))
    blob.cache_control = "public, max-age=31536000"
    blob.upload_from_string(webp, content_type="image/webp")
    blob.make_public()
    version = int(datetime.now(timezone.utc).timestamp() * 1000)
    return f"{blob.public_url}?v={version}"


async def upload_cover(game_id: int, webp: bytes) -> str:
    try:
        return await run_in_threadpool(_upload, game_id, webp)
    except ApiError:
        raise
    except Exception:
        logger.exception("Nie udało się wysłać okładki gry %d", game_id)
        raise ApiError(502, ErrorCode.COVER_UPLOAD_FAILED)


def _upload_private(path: str, webp: bytes) -> None:
    blob = get_bucket().blob(path)
    blob.cache_control = "private, no-store"
    blob.upload_from_string(webp, content_type="image/webp")


async def upload_candidate(game_id: int, webp: bytes) -> str:
    path = candidate_path(game_id)
    try:
        await run_in_threadpool(_upload_private, path, webp)
    except Exception:
        logger.exception("Nie udało się wysłać okładki do stagingu gry %d", game_id)
        raise ApiError(502, ErrorCode.COVER_UPLOAD_FAILED)
    return path


def signed_preview_url(path: str) -> str:
    return get_bucket().blob(path).generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=15),
        method="GET",
    )


def publish_candidate(game_id: int, path: str) -> str:
    bucket = get_bucket()
    source = bucket.blob(path)
    destination = bucket.copy_blob(source, bucket, _cover_path(game_id))
    destination.cache_control = "public, max-age=31536000, immutable"
    destination.patch()
    destination.make_public()
    version = int(datetime.now(timezone.utc).timestamp() * 1000)
    return f"{destination.public_url}?v={version}"


def delete_path(path: str | None) -> None:
    if path:
        _delete(path)


def _delete(path: str) -> None:
    try:
        get_bucket().blob(path).delete()
    except NotFound:
        pass


def delete_cover(game_id: int) -> None:
    _delete(_cover_path(game_id))


def delete_game_assets(game_id: int) -> None:
    """Best-effort usuwa cały prefix gry: cover, galerię, staging i model."""
    try:
        blobs = list(get_bucket().list_blobs(prefix=f"games/{game_id}/"))
    except Exception:
        logger.warning("Nie udało się wylistować zasobów gry %d", game_id, exc_info=True)
        blobs = []
    for blob in blobs:
        try:
            blob.delete()
        except Exception:
            logger.warning("Nie udało się usunąć zasobu %s", blob.name, exc_info=True)
