"""Avatar: walidacja, optymalizacja (Pillow → webp) i Firebase Storage.

Walidacja pliku — TRZY warstwy (defense in depth), wszystkie muszą przejść:
    1. rozmiar czytany chunkami z limitem PRZED wczytaniem całości do RAM,
    2. Content-Type części multipart (fałszowalny, ale odcina przypadki),
    3. Pillow parsuje bajty — nie-obraz odpada niezależnie od nagłówków.

Avatary to dane publiczne: stały URL bez tokenów, cache busting przez ?v=.
Ścieżka w buckecie: avatars/{firebase_uid}/avatar.webp — firebase_uid jest
stały i globalnie unikalny; wewnętrznego users.id nie ujawniamy w URL-ach.
"""

import io
import logging
from datetime import datetime, timezone

from fastapi import UploadFile
from google.cloud.exceptions import NotFound
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from services.app.core.errors import ApiError, ErrorCode
from services.app.core.storage import get_bucket

logger = logging.getLogger(__name__)

MAX_AVATAR_SIZE = 2 * 1024 * 1024  # 2 MB przed optymalizacją
# Bomba pikselowa: jednokolorowy PNG 10000×10000 waży <100 KB, ale dekoduje się
# do ~300 MB RAM. Domyślny limit Pillow rzuca dopiero przy ~178 Mpx, więc tniemy
# sami — 24 Mpx starcza na zdjęcie z każdego telefonu (typowo 12–16 Mpx).
MAX_IMAGE_PIXELS = 24_000_000
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
AVATAR_SIZE = (400, 400)
WEBP_QUALITY = 85
_CHUNK_SIZE = 64 * 1024


def _blob_path(firebase_uid: str) -> str:
    return f"avatars/{firebase_uid}/avatar.webp"


# ── Warstwa 1: rozmiar (chunkami, zanim całość trafi do RAM) ─────────────────


async def _read_limited(file: UploadFile) -> bytes:
    """NIGDY `await file.read()` bez limitu — 500 MB uploadu zalałoby RAM.
    Czytamy porcjami i tniemy przy pierwszym przekroczeniu."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_CHUNK_SIZE):
        total += len(chunk)
        if total > MAX_AVATAR_SIZE:
            raise ApiError.bad_request(
                ErrorCode.FILE_TOO_LARGE, details={"max_bytes": MAX_AVATAR_SIZE}
            )
        chunks.append(chunk)
    return b"".join(chunks)


# ── Warstwa 3 + optymalizacja: Pillow (CPU-bound → wołane przez threadpool) ──


def _optimize_to_webp(data: bytes) -> bytes:
    try:
        # Image.open czyta tylko nagłówek — wymiary znamy BEZ dekodowania,
        # więc bombę pikselową odrzucamy zanim zaalokuje RAM.
        img = Image.open(io.BytesIO(data))
        width, height = img.size
        if width * height > MAX_IMAGE_PIXELS:
            raise ApiError.bad_request(
                ErrorCode.FILE_TOO_LARGE, details={"max_pixels": MAX_IMAGE_PIXELS}
            )
        img.load()  # wymusza pełne zdekodowanie — wykrywa ucięte/podrobione pliki
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        # DecompressionBombError zostaje jako pas bezpieczeństwa (limit Pillow)
        raise ApiError.bad_request(ErrorCode.INVALID_FILE_TYPE)

    # Obrót wg EXIF, zanim metadane przepadną. Save() niżej NIE zapisuje EXIF —
    # celowo: publiczny plik nie może nieść GPS-a ani modelu telefonu autora.
    img = ImageOps.exif_transpose(img)

    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        # przezroczystość → białe tło (webp lossy + jednolity wygląd w UI)
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        img = background
    else:
        img = img.convert("RGB")

    # kwadrat 400×400: skaluje i kadruje środek (jednolite avatary w UI)
    img = ImageOps.fit(img, AVATAR_SIZE)

    buf = io.BytesIO()  # zero plików tymczasowych na dysku
    img.save(buf, format="WEBP", quality=WEBP_QUALITY)
    return buf.getvalue()


# ── Firebase Storage (blokujące I/O → wołane przez threadpool) ───────────────


def _upload_blob(firebase_uid: str, webp_data: bytes) -> str:
    blob = get_bucket().blob(_blob_path(firebase_uid))
    # rok cache'u jest bezpieczny, bo każdy upload zmienia ?v= w URL-u
    # Avatar jest danymi osobowymi; po usunięciu konta CDN nie powinien
    # przechowywać kopii przez rok. Cache busting ?v= nadal działa przy uploadzie.
    blob.cache_control = "public, max-age=300, must-revalidate"
    blob.upload_from_string(webp_data, content_type="image/webp")
    blob.make_public()
    # milisekundy: dwa uploady w tej samej sekundzie też muszą zmienić URL
    version = int(datetime.now(timezone.utc).timestamp() * 1000)
    return f"{blob.public_url}?v={version}"


# ── Publiczne API serwisu ─────────────────────────────────────────────────────


async def upload_avatar(file: UploadFile, firebase_uid: str) -> str:
    """Waliduje, optymalizuje i wysyła avatar. Zwraca publiczny URL z ?v=.

    Każdy upload nadpisuje avatars/{uid}/avatar.webp — stare wersje nie
    gromadzą się w buckecie.
    """
    # Warstwa 2: content-type z nagłówka części multipart
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise ApiError.bad_request(ErrorCode.INVALID_FILE_TYPE)

    data = await _read_limited(file)

    # Pillow i GCS są blokujące — threadpool, żeby nie stać w event loopie
    webp_data = await run_in_threadpool(_optimize_to_webp, data)
    try:
        return await run_in_threadpool(_upload_blob, firebase_uid, webp_data)
    except Exception:
        logger.exception("Upload avatara do Firebase Storage nie powiódł się")
        raise ApiError(502, ErrorCode.AVATAR_UPLOAD_FAILED)


def delete_avatar(firebase_uid: str) -> None:
    """Usuwa avatar z bucketa. Idempotentne — brak pliku to nie błąd."""
    try:
        get_bucket().blob(_blob_path(firebase_uid)).delete()
    except NotFound:
        pass
