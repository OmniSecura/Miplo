"""Walidacja i prywatny staging zdjęć galerii customowych gier."""

import io
import logging
from datetime import timedelta
from uuid import UUID

from fastapi import UploadFile
from google.cloud.exceptions import NotFound
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from services.app.core.errors import ApiError, ErrorCode
from services.app.core.storage import get_bucket

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000
MAX_IMAGE_DIMENSION = 1600
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
_CHUNK_SIZE = 64 * 1024


def gallery_path(game_id: int, public_id: UUID) -> str:
    return f"games/{game_id}/gallery/{public_id}.webp"


async def _read_limited(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_CHUNK_SIZE):
        total += len(chunk)
        if total > MAX_IMAGE_BYTES:
            raise ApiError.bad_request(
                ErrorCode.FILE_TOO_LARGE,
                details={"max_bytes": MAX_IMAGE_BYTES},
            )
        chunks.append(chunk)
    if not chunks:
        raise ApiError.bad_request(ErrorCode.INVALID_FILE_TYPE)
    return b"".join(chunks)


def _optimize(raw: bytes) -> bytes:
    try:
        image = Image.open(io.BytesIO(raw))
        if image.format not in ALLOWED_FORMATS:
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
    if image.mode in {"RGBA", "LA", "PA"} or (
        image.mode == "P" and "transparency" in image.info
    ):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        image = background
    else:
        image = image.convert("RGB")
    image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)

    output = io.BytesIO()
    image.save(output, "WEBP", quality=85, method=6)
    return output.getvalue()


async def prepare_image(file: UploadFile) -> bytes:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise ApiError.bad_request(ErrorCode.INVALID_FILE_TYPE)
    return await run_in_threadpool(_optimize, await _read_limited(file))


def _upload_private(path: str, webp: bytes) -> None:
    blob = get_bucket().blob(path)
    blob.cache_control = "private, no-store"
    blob.upload_from_string(webp, content_type="image/webp")


async def upload_private(path: str, webp: bytes) -> None:
    try:
        await run_in_threadpool(_upload_private, path, webp)
    except Exception:
        logger.exception("Upload zdjęcia galerii do stagingu nie powiódł się")
        raise ApiError(502, ErrorCode.IMAGE_UPLOAD_FAILED)


def make_public(path: str) -> str:
    blob = get_bucket().blob(path)
    blob.cache_control = "public, max-age=31536000, immutable"
    blob.patch()
    blob.make_public()
    return blob.public_url


def signed_preview_url(path: str) -> str:
    return get_bucket().blob(path).generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=15),
        method="GET",
    )


def delete(path: str) -> None:
    try:
        get_bucket().blob(path).delete()
    except NotFound:
        pass
