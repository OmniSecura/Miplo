"""Regresja strategii synchronizacji BGG: limity, deduplikacja i integralność."""

import asyncio
import io
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import pairwise
from unittest.mock import AsyncMock, patch

if "services.app.core.database" not in sys.modules:
    os.environ["ENV"] = "local"
    os.environ["SQLITE_PATH"] = os.path.join(tempfile.gettempdir(), "miplo-sync-tests.db")
    os.environ.setdefault("FIREBASE_ADMIN_CREDENTIALS", "unused-in-unit-tests.json")
    os.environ.setdefault("FIREBASE_STORAGE_BUCKET", "unused-in-unit-tests")

from fastapi import UploadFile
from sqlalchemy import select

from services.app.core import bgg_client
from services.app.core.config import Settings, settings
from services.app.core.database import Base, SessionLocal, engine
from services.app.core.errors import ApiError, ErrorCode
from services.app.games.enums import CatalogImportMode
from services.app.games.models import Game
from services.app.games.services import bgg_sync_service, catalog_import_service, game_service
from services.app.ratings.models import GameRating
from services.app.shelf.models import ShelfItem
from services.app.users.models import User


def _csv_upload(rows: str, *, content_type: str = "text/csv") -> UploadFile:
    header = "id,name,yearpublished,rank,bayesaverage,average,usersrated,is_expansion\n"
    return UploadFile(
        file=io.BytesIO((header + rows).encode()),
        filename="boardgames_ranks.csv",
        headers={"content-type": content_type},
    )


class BggSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Base.metadata.create_all(engine)

    @classmethod
    def tearDownClass(cls) -> None:
        engine.dispose()
        database_path = str(engine.url.database or "")
        if os.path.dirname(database_path) == tempfile.gettempdir():
            try:
                os.unlink(database_path)
            except FileNotFoundError:
                pass

    def setUp(self) -> None:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        self.db = SessionLocal()
        bgg_client._reset_runtime_state_for_tests()
        game_service._reset_refresh_state_for_tests()

    def tearDown(self) -> None:
        self.db.close()

    def test_fifty_parallel_requests_are_globally_throttled(self) -> None:
        starts: list[float] = []
        active = 0
        max_active = 0

        async def fake_request(_client, _url, _params):
            nonlocal active, max_active
            starts.append(time.monotonic())
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.012)
            active -= 1
            return 200, b"<items/>"

        async def run() -> None:
            await asyncio.gather(
                *(bgg_client._get_xml(None, "thing", {"id": str(index)}) for index in range(50))
            )

        with (
            patch.object(settings, "BGG_MAX_CONCURRENT", 2),
            patch.object(settings, "BGG_MIN_REQUEST_INTERVAL", 0.005),
            patch.object(bgg_client, "_request_once", side_effect=fake_request),
        ):
            asyncio.run(run())

        self.assertLessEqual(max_active, 2)
        self.assertEqual(len(starts), 50)
        self.assertTrue(all(right - left >= 0.003 for left, right in pairwise(starts)))

    def test_twenty_parallel_fetches_of_one_game_use_one_request(self) -> None:
        result = bgg_client.BggGameData(
            bgg_id=224517,
            title="Brass: Birmingham",
            description=None,
            year_published=2018,
            min_players=2,
            max_players=4,
            playing_time=120,
            rating=Decimal("8.60"),
            weight=Decimal("3.90"),
            users_rated=50_000,
            bgg_rank=1,
            cover_url=None,
            categories=[],
        )

        async def fake_fetch(_bgg_id: int):
            await asyncio.sleep(0.01)
            return result

        fetch = AsyncMock(side_effect=fake_fetch)

        async def run():
            return await asyncio.gather(*(bgg_client.fetch_game_deduped(224517) for _ in range(20)))

        with patch.object(bgg_client, "fetch_game", new=fetch):
            received = asyncio.run(run())
        self.assertEqual(fetch.await_count, 1)
        self.assertTrue(all(item is result for item in received))

    def test_failed_deduplicated_fetch_is_cleaned_and_can_be_retried(self) -> None:
        failed = AsyncMock(side_effect=ApiError(502, ErrorCode.BGG_UNAVAILABLE))

        async def run_failed():
            return await asyncio.gather(
                *(bgg_client.fetch_game_deduped(7) for _ in range(5)),
                return_exceptions=True,
            )

        with patch.object(bgg_client, "fetch_game", new=failed):
            results = asyncio.run(run_failed())
        self.assertEqual(failed.await_count, 1)
        self.assertTrue(all(isinstance(item, ApiError) for item in results))

        recovered = bgg_client.BggGameData(
            7,
            "Recovered",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            [],
        )
        with patch.object(bgg_client, "fetch_game", new=AsyncMock(return_value=recovered)):
            self.assertEqual(asyncio.run(bgg_client.fetch_game_deduped(7)).title, "Recovered")

    def test_cache_ttl_is_thirty_days_and_refresh_queue_is_bounded(self) -> None:
        game = Game(
            bgg_id=1,
            slug="cached",
            title="Cached",
            source="bgg",
            is_verified=True,
            cached_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        with patch.object(settings, "BGG_CACHE_TTL_SECONDS", 2_592_000):
            self.assertFalse(game_service.is_stale(game))
            game.cached_at = datetime.now(timezone.utc) - timedelta(days=31)
            self.assertTrue(game_service.is_stale(game))

        with (
            patch.object(settings, "BGG_API_TOKEN", "configured"),
            patch.object(settings, "BGG_MAX_PENDING_REFRESHES", 1),
        ):
            self.assertTrue(game_service.should_schedule_refresh(1))
            self.assertFalse(game_service.should_schedule_refresh(1))
            self.assertFalse(game_service.should_schedule_refresh(2))
            game_service._finish_scheduled_refresh(1)
            self.assertTrue(game_service.should_schedule_refresh(2))

    def test_update_import_preserves_all_non_whitelisted_fields(self) -> None:
        cached_at = datetime.now(timezone.utc) - timedelta(days=2)
        game = Game(
            bgg_id=1,
            slug="stable-slug",
            title="Manual title",
            description="Do not overwrite",
            year_published=2000,
            min_players=2,
            max_players=5,
            playing_time=90,
            rating=Decimal("6.00"),
            weight=Decimal("4.10"),
            cover_url="https://cf.geekdo-images.com/stable.webp",
            bgg_rank=50,
            users_rated=100,
            miplo_rating=Decimal("9.0"),
            miplo_ratings_count=20,
            miplo_reviews_count=10,
            source="bgg",
            is_verified=True,
            cached_at=cached_at,
        )
        self.db.add(game)
        self.db.commit()

        result = catalog_import_service.import_catalog(
            self.db,
            _csv_upload(
                "1,Changed title,2024,2,8.2,8.70,9999,1\n2,New game,2025,10,7.0,7.50,500,0\n"
            ),
            CatalogImportMode.UPDATE,
        )
        self.db.refresh(game)
        self.assertEqual((result.inserted, result.updated, result.errors), (1, 1, 0))
        self.assertEqual(game.title, "Manual title")
        self.assertEqual(game.slug, "stable-slug")
        self.assertEqual(game.description, "Do not overwrite")
        self.assertEqual((game.min_players, game.max_players, game.playing_time), (2, 5, 90))
        self.assertEqual(game.weight, Decimal("4.10"))
        self.assertEqual(game.cover_url, "https://cf.geekdo-images.com/stable.webp")
        restored_cached_at = game.cached_at
        if restored_cached_at.tzinfo is None:
            restored_cached_at = restored_cached_at.replace(tzinfo=timezone.utc)
        self.assertEqual(restored_cached_at, cached_at)
        self.assertEqual(game.miplo_rating, Decimal("9.0"))
        self.assertEqual(game.rating, Decimal("8.70"))
        self.assertEqual((game.bgg_rank, game.users_rated, game.year_published), (2, 9999, 2024))
        self.assertFalse(game.is_expansion)
        self.assertIsNotNone(self.db.scalar(select(Game).where(Game.bgg_id == 2)))

    def test_full_import_changes_only_its_explicit_extra_fields(self) -> None:
        game = Game(
            bgg_id=1,
            slug="never-change",
            title="Old title",
            cover_url="https://cf.geekdo-images.com/stable.webp",
            source="bgg",
            is_verified=True,
        )
        self.db.add(game)
        self.db.commit()
        catalog_import_service.import_catalog(
            self.db,
            _csv_upload("1,New title,2024,1,8.0,8.50,1000,1\n"),
            CatalogImportMode.FULL,
        )
        self.db.refresh(game)
        self.assertEqual(game.title, "New title")
        self.assertTrue(game.is_expansion)
        self.assertEqual(game.slug, "never-change")
        self.assertEqual(game.cover_url, "https://cf.geekdo-images.com/stable.webp")

    def test_csv_header_content_type_and_parallel_import_are_rejected(self) -> None:
        invalid_header = UploadFile(
            file=io.BytesIO(b"id,name\n1,Only two columns\n"),
            filename="bad.csv",
            headers={"content-type": "text/csv"},
        )
        with self.assertRaises(ApiError) as header_error:
            catalog_import_service.import_catalog(self.db, invalid_header)
        self.assertEqual(
            header_error.exception.detail["error_code"],
            ErrorCode.INVALID_CSV_FORMAT.value,
        )

        with self.assertRaises(ApiError):
            catalog_import_service.import_catalog(
                self.db,
                _csv_upload("1,Game,2020,1,8,8,100,0\n", content_type="application/json"),
            )

        with (
            patch.object(
                catalog_import_service,
                "_file_size",
                return_value=catalog_import_service.MAX_IMPORT_FILE_SIZE + 1,
            ),
            self.assertRaises(ApiError) as size_error,
        ):
            catalog_import_service.import_catalog(
                self.db,
                _csv_upload("1,Game,2020,1,8,8,100,0\n"),
            )
        self.assertEqual(size_error.exception.status_code, 413)
        self.assertEqual(
            size_error.exception.detail["error_code"],
            ErrorCode.CSV_TOO_LARGE.value,
        )

        catalog_import_service._import_lock.acquire()
        try:
            with self.assertRaises(ApiError) as lock_error:
                catalog_import_service.import_catalog(
                    self.db,
                    _csv_upload("1,Game,2020,1,8,8,100,0\n"),
                )
            self.assertEqual(
                lock_error.exception.detail["error_code"],
                ErrorCode.IMPORT_ALREADY_RUNNING.value,
            )
        finally:
            catalog_import_service._import_lock.release()

    def test_nightly_sync_processes_user_games_before_ranked_catalog(self) -> None:
        user = User(firebase_uid="sync-user", tag="sync_user", is_active=True)
        games = [
            Game(
                bgg_id=1, slug="shelf", title="Shelf", bgg_rank=100, source="bgg", is_verified=True
            ),
            Game(
                bgg_id=2,
                slug="rated",
                title="Rated",
                bgg_rank=200,
                source="bgg",
                is_verified=True,
                cached_at=datetime.now(timezone.utc) - timedelta(days=31),
            ),
            Game(bgg_id=3, slug="top", title="Top", bgg_rank=1, source="bgg", is_verified=True),
        ]
        self.db.add_all([user, *games])
        self.db.flush()
        self.db.add(ShelfItem(user_id=user.id, game_id=games[0].id))
        self.db.add(GameRating(user_id=user.id, game_id=games[1].id, rating=Decimal("8.0")))
        self.db.commit()
        calls: list[list[int]] = []

        async def fake_batch(db, ids, *, commit=True):
            calls.append(list(ids))
            result = {}
            for game in db.scalars(select(Game).where(Game.bgg_id.in_(ids))).all():
                game.cached_at = datetime.now(timezone.utc)
                result[int(game.bgg_id)] = game
            db.commit()
            return result

        with (
            patch.object(game_service, "get_or_fetch_games_batch", side_effect=fake_batch),
            patch.object(settings, "BGG_MIN_REQUEST_INTERVAL", 0.1),
            patch.object(settings, "BGG_API_TOKEN", "configured"),
        ):
            stats = asyncio.run(bgg_sync_service.nightly_sync(self.db, budget_seconds=5))

        self.assertEqual(calls, [[1], [2], [3]])
        self.assertEqual((stats["with_users"], stats["refreshed"], stats["by_rank"]), (1, 1, 1))
        self.assertEqual(stats["failed"], 0)

    def test_nightly_sync_honors_exhausted_budget(self) -> None:
        with patch.object(settings, "BGG_API_TOKEN", "configured"):
            stats = asyncio.run(bgg_sync_service.nightly_sync(self.db, budget_seconds=0.1))
        self.assertTrue(stats["budget_exhausted"])
        self.assertEqual(stats["with_users"], 0)

    def test_nightly_sync_without_token_fails_fast(self) -> None:
        with (
            patch.object(settings, "BGG_API_TOKEN", None),
            self.assertRaises(ApiError) as context,
        ):
            asyncio.run(bgg_sync_service.nightly_sync(self.db))
        self.assertEqual(
            context.exception.detail["error_code"],
            ErrorCode.BGG_NOT_CONFIGURED.value,
        )

    def test_admin_import_openapi_uses_enum_and_old_route_is_gone(self) -> None:
        from services.app.server import app

        schema = app.openapi()
        self.assertIn("/api/admin/games/import", schema["paths"])
        self.assertNotIn("/api/games/import", schema["paths"])
        self.assertEqual(
            schema["components"]["schemas"]["CatalogImportMode"]["enum"],
            ["update", "full"],
        )

    def test_bgg_base_url_cannot_exfiltrate_bearer_token(self) -> None:
        with self.assertRaises(ValueError):
            Settings(
                ENV="local",
                FIREBASE_ADMIN_CREDENTIALS="unused.json",
                FIREBASE_STORAGE_BUCKET="unused",
                BGG_API_BASE="https://attacker.example/xmlapi2",
            )


if __name__ == "__main__":
    unittest.main()
