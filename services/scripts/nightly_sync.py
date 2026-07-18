"""Uruchom z katalogu repo: python -m services.scripts.nightly_sync"""

import asyncio
import json
import logging

from services.app.core.database import db_session
from services.app.games.services.bgg_sync_service import nightly_sync

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    with db_session() as db:
        stats = await nightly_sync(db)
    print(json.dumps(stats, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
