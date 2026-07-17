"""Firebase Storage — jedyne miejsce dotykające bucketa.

Analogicznie do core/auth.py: reszta kodu (avatar_service) dostaje gotowy
uchwyt bucketa i nie wie, jak jest skonfigurowany. Wymaga zainicjalizowanego
firebase_admin (init_firebase z core/auth.py musi zajść wcześniej).
"""

from firebase_admin import storage
from google.cloud.storage import Bucket

from services.app.core.config import settings

_bucket: Bucket | None = None


def init_storage() -> None:
    """Wołane raz w lifespanie, PO init_firebase.

    Fail-fast: brak zainicjalizowanej appki Firebase albo pusta nazwa bucketa
    wywala start serwera, nie pierwszy upload.
    """
    global _bucket
    _bucket = storage.bucket(name=settings.FIREBASE_STORAGE_BUCKET)


def get_bucket() -> Bucket:
    if _bucket is None:
        init_storage()
    return _bucket
