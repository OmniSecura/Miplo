"""Bezpieczny generator dwuczęściowego, teksturowanego pudełka GLB.

Geometria jest budowana bez CSG i bez plików tymczasowych. Denko i wieko są
osobnymi node'ami, a boczne tekstury są dzielone na dolny pasek denka i część
przykrywki. GLB korzysta wyłącznie z podstawowego glTF 2.0 oraz osadzonych JPEG,
więc nie wymaga rozszerzenia EXT_texture_webp po stronie klienta.
"""

import asyncio
import io
import json
import logging
import math
import struct
from datetime import datetime, timedelta, timezone

from fastapi import UploadFile
from google.cloud.exceptions import NotFound
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from services.app.core.config import settings
from services.app.core.database import db_session
from services.app.core.errors import ApiError, ErrorCode
from services.app.core.storage import get_bucket
from services.app.games.models import Game

logger = logging.getLogger(__name__)

SIDE_NAMES = ("front", "back", "left", "right", "top", "bottom")
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_SIDE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000
MAX_TEXTURE_DIMENSION = 1024
MAX_GLB_BYTES = 24 * 1024 * 1024
_CHUNK_SIZE = 64 * 1024
_WALL_CM = 0.20
_CLEARANCE_CM = 0.05
_LID_DEPTH_RATIO = 0.96
_GENERATION_SLOTS = asyncio.Semaphore(settings.MODEL_GENERATION_CONCURRENCY)


def _candidate_path(game_id: int, job_id: str) -> str:
    return f"games/{game_id}/models/submissions/{job_id}.glb"


def _public_path(game_id: int) -> str:
    return f"games/{game_id}/box_model.glb"


async def _read_limited(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_CHUNK_SIZE):
        total += len(chunk)
        if total > MAX_SIDE_BYTES:
            raise ApiError.bad_request(
                ErrorCode.FILE_TOO_LARGE,
                details={"max_bytes_per_file": MAX_SIDE_BYTES},
            )
        chunks.append(chunk)
    if not chunks:
        raise ApiError.bad_request(ErrorCode.INVALID_FILE_TYPE)
    return b"".join(chunks)


def _validate_image(raw: bytes) -> None:
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


async def read_validated_sides(files: dict[str, UploadFile | None]) -> dict[str, bytes]:
    if set(files) != set(SIDE_NAMES) or any(files[name] is None for name in SIDE_NAMES):
        raise ApiError.bad_request(ErrorCode.ALL_SIDES_REQUIRED)

    result: dict[str, bytes] = {}
    total = 0
    for name in SIDE_NAMES:
        file = files[name]
        if file is None:  # defense in depth; normalnie odrzucone wyżej
            raise ApiError.bad_request(ErrorCode.ALL_SIDES_REQUIRED)
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise ApiError.bad_request(
                ErrorCode.INVALID_FILE_TYPE,
                details={"side": name},
            )
        raw = await _read_limited(file)
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise ApiError.bad_request(
                ErrorCode.FILE_TOO_LARGE,
                details={"max_total_bytes": MAX_TOTAL_BYTES},
            )
        try:
            await run_in_threadpool(_validate_image, raw)
        except ApiError as exc:
            detail: dict[str, object] = exc.detail if isinstance(exc.detail, dict) else {}
            raw_details = detail.get("details", {})
            details = dict(raw_details) if isinstance(raw_details, dict) else {}
            details["side"] = name
            raw_code = detail.get("error_code", ErrorCode.INVALID_FILE_TYPE.value)
            try:
                error_code = ErrorCode(raw_code)
            except (TypeError, ValueError):
                error_code = ErrorCode.INVALID_FILE_TYPE
            raise ApiError.bad_request(
                error_code,
                details=details,
            )
        result[name] = raw
    return result


def _target_pixels(width: float, height: float) -> tuple[int, int]:
    longest = max(width, height)
    scale = MAX_TEXTURE_DIMENSION / longest
    return (
        max(64, min(MAX_TEXTURE_DIMENSION, round(width * scale))),
        max(64, min(MAX_TEXTURE_DIMENSION, round(height * scale))),
    )


def _texture_jpeg(
    raw: bytes,
    physical_width: float,
    physical_height: float,
    rotation_clockwise: int = 0,
) -> bytes:
    image: Image.Image = Image.open(io.BytesIO(raw))
    image.load()
    image = ImageOps.exif_transpose(image).convert("RGB")

    rotations = {
        0: None,
        90: Image.Transpose.ROTATE_270,
        180: Image.Transpose.ROTATE_180,
        270: Image.Transpose.ROTATE_90,
    }
    transpose = rotations.get(rotation_clockwise)
    if rotation_clockwise not in rotations:
        raise ValueError("rotation must be one of 0, 90, 180, 270")
    if transpose is not None:
        image = image.transpose(transpose)

    # Telefon potrafi zapisać bok pudełka obrócony mimo poprawnego EXIF. Obracamy
    # o 90° tylko wtedy, gdy taka orientacja wyraźnie lepiej odpowiada fizycznym
    # proporcjom ścianki. Nie próbujemy rozpoznawać tekstu ani zgadywać 180°.
    target_ratio = physical_width / physical_height
    current_ratio = image.width / image.height
    normal_error = abs(math.log(current_ratio / target_ratio))
    rotated_error = abs(math.log((1 / current_ratio) / target_ratio))
    if rotated_error + 0.10 < normal_error:
        image = image.transpose(Image.Transpose.ROTATE_270)

    image = ImageOps.fit(
        image,
        _target_pixels(physical_width, physical_height),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    output = io.BytesIO()
    image.save(output, "JPEG", quality=85, optimize=True, progressive=True)
    return output.getvalue()


class _BinaryBuilder:
    def __init__(self) -> None:
        self.data = bytearray()
        self.buffer_views: list[dict] = []
        self.accessors: list[dict] = []

    def add_view(self, payload: bytes, *, target: int | None = None) -> int:
        while len(self.data) % 4:
            self.data.append(0)
        offset = len(self.data)
        self.data.extend(payload)
        view: dict = {"buffer": 0, "byteOffset": offset, "byteLength": len(payload)}
        if target is not None:
            view["target"] = target
        self.buffer_views.append(view)
        return len(self.buffer_views) - 1

    def add_accessor(
        self,
        payload: bytes,
        *,
        component_type: int,
        count: int,
        value_type: str,
        target: int,
        minimum: list[float] | None = None,
        maximum: list[float] | None = None,
    ) -> int:
        accessor: dict = {
            "bufferView": self.add_view(payload, target=target),
            "componentType": component_type,
            "count": count,
            "type": value_type,
        }
        if minimum is not None:
            accessor["min"] = minimum
        if maximum is not None:
            accessor["max"] = maximum
        self.accessors.append(accessor)
        return len(self.accessors) - 1


def _pack_floats(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def _primitive(
    builder: _BinaryBuilder,
    positions: list[tuple[float, float, float]],
    normal: tuple[float, float, float],
    uvs: list[tuple[float, float]],
    material: int,
) -> dict:
    flat_positions = [coordinate for point in positions for coordinate in point]
    flat_normals = list(normal) * 4
    flat_uvs = [coordinate for uv in uvs for coordinate in uv]
    minimum = [min(point[axis] for point in positions) for axis in range(3)]
    maximum = [max(point[axis] for point in positions) for axis in range(3)]
    position_accessor = builder.add_accessor(
        _pack_floats(flat_positions),
        component_type=5126,
        count=4,
        value_type="VEC3",
        target=34962,
        minimum=minimum,
        maximum=maximum,
    )
    normal_accessor = builder.add_accessor(
        _pack_floats(flat_normals),
        component_type=5126,
        count=4,
        value_type="VEC3",
        target=34962,
    )
    uv_accessor = builder.add_accessor(
        _pack_floats(flat_uvs),
        component_type=5126,
        count=4,
        value_type="VEC2",
        target=34962,
    )
    index_accessor = builder.add_accessor(
        struct.pack("<6H", 0, 1, 2, 0, 2, 3),
        component_type=5123,
        count=6,
        value_type="SCALAR",
        target=34963,
        minimum=[0],
        maximum=[3],
    )
    return {
        "attributes": {
            "POSITION": position_accessor,
            "NORMAL": normal_accessor,
            "TEXCOORD_0": uv_accessor,
        },
        "indices": index_accessor,
        "material": material,
        "mode": 4,
    }


def _edge_quads(
    builder: _BinaryBuilder,
    *,
    half_width: float,
    half_height: float,
    z0: float,
    z1: float,
    depth_fraction_0: float,
    depth_fraction_1: float,
    materials: dict[str, int],
) -> list[dict]:
    """Cztery krawędzie pudełka z orientacją zgodną z widokiem z zewnątrz.

    Oś X = szerokość okładki, Y = wysokość okładki, Z = grubość pudełka.
    Dla każdej ściany góra obrazu pozostaje skierowana ku wieku. Lewy i prawy
    bok są lustrzanie mapowane geometrycznie, dzięki czemu tekst nie jest
    odwrócony po obejrzeniu odpowiedniej strony z zewnątrz.
    """
    x, y = half_width, half_height
    # W glTF v=0 odpowiada górze źródłowego obrazu. Na top/bottom górą zdjęcia
    # jest strona wieka (+Z), więc rosnące Z oznacza malejące V.
    v0 = 1.0 - depth_fraction_0
    v1 = 1.0 - depth_fraction_1
    return [
        # Górny wąski bok (+Y): patrząc z zewnątrz, prawa strona obrazu
        # wskazuje -X, a jego góra wskazuje wieko (+Z).
        _primitive(
            builder,
            [(-x, y, z0), (-x, y, z1), (x, y, z1), (x, y, z0)],
            (0, 1, 0),
            [(1, v0), (1, v1), (0, v1), (0, v0)],
            materials["top"],
        ),
        # Dolny wąski bok (-Y).
        _primitive(
            builder,
            [(x, -y, z0), (x, -y, z1), (-x, -y, z1), (-x, -y, z0)],
            (0, -1, 0),
            [(1, v0), (1, v1), (0, v1), (0, v0)],
            materials["bottom"],
        ),
        # Lewy bok (-X): szerokość zdjęcia biegnie po grubości pudełka,
        # a wysokość zdjęcia po osi Y.
        _primitive(
            builder,
            [(-x, -y, z0), (-x, -y, z1), (-x, y, z1), (-x, y, z0)],
            (-1, 0, 0),
            [
                (depth_fraction_0, 1),
                (depth_fraction_1, 1),
                (depth_fraction_1, 0),
                (depth_fraction_0, 0),
            ],
            materials["left"],
        ),
        # Prawy bok (+X): odwrócenie U kompensuje oglądanie z przeciwnej strony.
        _primitive(
            builder,
            [(x, y, z0), (x, y, z1), (x, -y, z1), (x, -y, z0)],
            (1, 0, 0),
            [
                (1 - depth_fraction_0, 0),
                (1 - depth_fraction_1, 0),
                (1 - depth_fraction_1, 1),
                (1 - depth_fraction_0, 1),
            ],
            materials["right"],
        ),
    ]


def _seam_ring(
    builder: _BinaryBuilder,
    *,
    base_half_width: float,
    base_half_height: float,
    lid_half_width: float,
    lid_half_height: float,
    z: float,
    material: int,
) -> list[dict]:
    """Czarny spód rantu wieka zasłaniający prześwit między dwiema częściami."""
    x, y = base_half_width, base_half_height
    lx, ly = lid_half_width, lid_half_height
    uv: list[tuple[float, float]] = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]
    return [
        _primitive(
            builder,
            [(-lx, -ly, z), (-x, -y, z), (x, -y, z), (lx, -ly, z)],
            (0, 0, -1),
            uv,
            material,
        ),
        _primitive(
            builder,
            [(-lx, ly, z), (lx, ly, z), (x, y, z), (-x, y, z)],
            (0, 0, -1),
            uv,
            material,
        ),
        _primitive(
            builder,
            [(-lx, -y, z), (-lx, y, z), (-x, y, z), (-x, -y, z)],
            (0, 0, -1),
            uv,
            material,
        ),
        _primitive(
            builder,
            [(lx, -y, z), (x, -y, z), (x, y, z), (lx, y, z)],
            (0, 0, -1),
            uv,
            material,
        ),
    ]


def build_glb(
    raw_sides: dict[str, bytes],
    dimensions_cm: tuple[float, float, float],
    rotations: dict[str, int] | None = None,
) -> bytes:
    width_cm, height_cm, depth_cm = dimensions_cm
    if not all(2.0 <= value <= 100.0 for value in dimensions_cm):
        raise ValueError("box dimensions outside supported range")
    rotations = rotations or {}
    if any(name not in SIDE_NAMES for name in rotations):
        raise ValueError("unknown side rotation")

    textures = {
        "front": _texture_jpeg(raw_sides["front"], width_cm, height_cm, rotations.get("front", 0)),
        "back": _texture_jpeg(raw_sides["back"], width_cm, height_cm, rotations.get("back", 0)),
        "left": _texture_jpeg(raw_sides["left"], depth_cm, height_cm, rotations.get("left", 0)),
        "right": _texture_jpeg(raw_sides["right"], depth_cm, height_cm, rotations.get("right", 0)),
        "top": _texture_jpeg(raw_sides["top"], width_cm, depth_cm, rotations.get("top", 0)),
        "bottom": _texture_jpeg(
            raw_sides["bottom"], width_cm, depth_cm, rotations.get("bottom", 0)
        ),
    }

    # glTF używa metrów. W bazie trzymamy centymetry.
    # X = box_width, Y = box_height, Z = box_depth. To kluczowe: wieko
    # nasuwa się wzdłuż GRUBOŚCI pudełka, a nie dużej wysokości okładki.
    width, height, depth = width_cm / 100, height_cm / 100, depth_cm / 100
    x, y, z = width / 2, height / 2, depth / 2
    wall = _WALL_CM / 100
    lid_depth = depth * _LID_DEPTH_RATIO
    seam_z = z - lid_depth + wall
    lid_expansion = (_WALL_CM + _CLEARANCE_CM) / 100
    lid_top = z + wall
    full_visible_depth = lid_top - (-z)
    seam_fraction = (seam_z - (-z)) / full_visible_depth

    builder = _BinaryBuilder()
    images: list[dict] = []
    texture_defs: list[dict] = []
    materials: list[dict] = []
    material_indexes: dict[str, int] = {}
    for name in SIDE_NAMES:
        image_view = builder.add_view(textures[name])
        images.append({"name": name, "bufferView": image_view, "mimeType": "image/jpeg"})
        texture_defs.append({"sampler": 0, "source": len(images) - 1})
        materials.append(
            {
                "name": name,
                "pbrMetallicRoughness": {
                    "baseColorTexture": {"index": len(texture_defs) - 1},
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.82,
                },
                "doubleSided": False,
            }
        )
        material_indexes[name] = len(materials) - 1
    cardboard_material = len(materials)
    materials.append(
        {
            "name": "cardboard_black",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.01, 0.01, 0.01, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.95,
            },
            "doubleSided": True,
        }
    )

    base_primitives = _edge_quads(
        builder,
        half_width=x,
        half_height=y,
        z0=-z,
        z1=seam_z,
        depth_fraction_0=0.0,
        depth_fraction_1=seam_fraction,
        materials=material_indexes,
    )
    # Spód pudełka: plik "back". UV zachowuje czytelność po spojrzeniu od dołu.
    base_primitives.append(
        _primitive(
            builder,
            [(x, -y, -z), (-x, -y, -z), (-x, y, -z), (x, y, -z)],
            (0, 0, -1),
            [(0, 1), (1, 1), (1, 0), (0, 0)],
            material_indexes["back"],
        )
    )

    lid_primitives = _edge_quads(
        builder,
        half_width=x + lid_expansion,
        half_height=y + lid_expansion,
        z0=seam_z,
        z1=lid_top,
        depth_fraction_0=seam_fraction,
        depth_fraction_1=1.0,
        materials=material_indexes,
    )
    lx, ly = x + lid_expansion, y + lid_expansion
    lid_primitives.extend(
        _seam_ring(
            builder,
            base_half_width=x,
            base_half_height=y,
            lid_half_width=lx,
            lid_half_height=ly,
            z=seam_z,
            material=cardboard_material,
        )
    )
    # Wierzch/wieko pudełka: plik "front". Góra obrazu wskazuje +Y.
    lid_primitives.append(
        _primitive(
            builder,
            [(-lx, -ly, lid_top), (lx, -ly, lid_top), (lx, ly, lid_top), (-lx, ly, lid_top)],
            (0, 0, 1),
            [(0, 1), (1, 1), (1, 0), (0, 0)],
            material_indexes["front"],
        )
    )

    document = {
        "asset": {"version": "2.0", "generator": "Miplo box generator"},
        "extras": {
            "axisConvention": "X=width,Y=height,Z=depth",
            "faceConvention": "front=lid,back=base,left/right/top/bottom=edges",
        },
        "scene": 0,
        "scenes": [{"nodes": [0, 1]}],
        "nodes": [
            {"name": "BoxBase", "mesh": 0},
            {"name": "BoxLid", "mesh": 1},
        ],
        "meshes": [
            {"name": "BoxBase", "primitives": base_primitives},
            {"name": "BoxLid", "primitives": lid_primitives},
        ],
        "samplers": [{"magFilter": 9729, "minFilter": 9729, "wrapS": 33071, "wrapT": 33071}],
        "images": images,
        "textures": texture_defs,
        "materials": materials,
        "buffers": [{"byteLength": len(builder.data)}],
        "bufferViews": builder.buffer_views,
        "accessors": builder.accessors,
    }

    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((-len(json_chunk)) % 4)
    binary_chunk = bytes(builder.data)
    binary_chunk += b"\x00" * ((-len(binary_chunk)) % 4)
    total_length = 12 + 8 + len(json_chunk) + 8 + len(binary_chunk)
    glb = b"".join(
        [
            struct.pack("<4sII", b"glTF", 2, total_length),
            struct.pack("<I4s", len(json_chunk), b"JSON"),
            json_chunk,
            struct.pack("<I4s", len(binary_chunk), b"BIN\x00"),
            binary_chunk,
        ]
    )
    if len(glb) > MAX_GLB_BYTES:
        raise ValueError("generated GLB exceeds size limit")
    return glb


def _upload_private(path: str, glb: bytes) -> None:
    blob = get_bucket().blob(path)
    blob.cache_control = "private, no-store"
    blob.upload_from_string(glb, content_type="model/gltf-binary")


def _delete(path: str | None) -> None:
    if not path:
        return
    try:
        get_bucket().blob(path).delete()
    except NotFound:
        pass


def signed_preview_url(path: str) -> str:
    return str(
        get_bucket()
        .blob(path)
        .generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=15),
            method="GET",
        )
    )


def publish_candidate(game_id: int, candidate_path: str) -> str:
    bucket = get_bucket()
    source = bucket.blob(candidate_path)
    destination = bucket.copy_blob(source, bucket, _public_path(game_id))
    destination.cache_control = "public, max-age=31536000, immutable"
    destination.patch()
    destination.make_public()
    version = int(datetime.now(timezone.utc).timestamp() * 1000)
    return f"{destination.public_url}?v={version}"


def delete_path(path: str | None) -> None:
    _delete(path)


def delete_model_files(game_id: int, candidate_path: str | None = None) -> None:
    for path in (candidate_path, _public_path(game_id)):
        try:
            _delete(path)
        except Exception:
            logger.warning("Nie udało się usunąć modelu %s", path, exc_info=True)


def _set_processing(game_id: int, job_id: str) -> bool:
    with db_session() as db:
        game = db.get(Game, game_id)
        if game is None or game.model_job_id != job_id or game.model_status != "pending":
            return False
        game.model_status = "processing"
        db.commit()
        return True


def _set_awaiting_review(game_id: int, job_id: str, path: str) -> bool:
    with db_session() as db:
        game = db.get(Game, game_id)
        if game is None or game.model_job_id != job_id:
            return False
        game.model_candidate_path = path
        game.model_status = "awaiting_review"
        db.commit()
        return True


def _set_failed(game_id: int, job_id: str) -> None:
    with db_session() as db:
        game = db.get(Game, game_id)
        if game is None or game.model_job_id != job_id:
            return
        game.model_status = "failed"
        game.model_candidate_path = None
        db.commit()


async def generate_and_upload(
    game_id: int,
    job_id: str,
    raw_sides: dict[str, bytes],
    dimensions_cm: tuple[float, float, float],
    rotations: dict[str, int] | None = None,
) -> None:
    """Ograniczony job requestowy: zawsze kończy awaiting_review albo failed."""
    candidate_path = _candidate_path(game_id, job_id)
    uploaded = False
    slot_acquired = False
    try:
        # Timeout dotyczy wyłącznie oczekiwania na wolny slot. Nie anulujemy
        # rozpoczętego wątku Pillow/GLB, bo wątek nadal używałby buforów po tym,
        # jak coroutine wykona cleanup — prowadziłoby to do race condition.
        await asyncio.wait_for(
            _GENERATION_SLOTS.acquire(),
            timeout=settings.MODEL_GENERATION_TIMEOUT_SECONDS,
        )
        slot_acquired = True
        if not _set_processing(game_id, job_id):
            return
        glb = await run_in_threadpool(build_glb, raw_sides, dimensions_cm, rotations)
        await run_in_threadpool(_upload_private, candidate_path, glb)
        uploaded = True
        if not _set_awaiting_review(game_id, job_id, candidate_path):
            await run_in_threadpool(_delete, candidate_path)
    except Exception:
        logger.exception("Generowanie modelu 3D gry %d nie powiodło się", game_id)
        if uploaded:
            try:
                _delete(candidate_path)
            except Exception:
                logger.warning(
                    "Cleanup nieudanego modelu %d nie powiódł się", game_id, exc_info=True
                )
        try:
            _set_failed(game_id, job_id)
        except Exception:
            logger.exception("Nie udało się oznaczyć modelu gry %d jako failed", game_id)
    finally:
        if slot_acquired:
            _GENERATION_SLOTS.release()
        raw_sides.clear()
