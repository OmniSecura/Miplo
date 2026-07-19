"""Testy domeny shelf bez prawdziwych połączeń Firebase i BGG."""

import asyncio
import os
import sys
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

if "services.app.core.database" not in sys.modules:
    os.environ["ENV"] = "local"
    os.environ["SQLITE_PATH"] = os.path.join(tempfile.gettempdir(), "miplo-shelf-tests.db")
    os.environ.setdefault("FIREBASE_ADMIN_CREDENTIALS", "unused-in-unit-tests.json")
    os.environ.setdefault("FIREBASE_STORAGE_BUCKET", "unused-in-unit-tests")

from pydantic import ValidationError
from sqlalchemy import event, select
from starlette.requests import Request

from services.app.core import bgg_client
from services.app.core.auth import get_current_user_optional
from services.app.core.database import Base, SessionLocal, engine
from services.app.core.errors import ApiError, ErrorCode
from services.app.games.models import Game
from services.app.games.services import game_service
from services.app.ratings.models import GameRating
from services.app.shelf.enums import ShelfCondition, ShelfSort
from services.app.shelf.models import ShelfItem
from services.app.shelf.schemas import (
    CollectionImportRequest,
    ShelfItemCreate,
    ShelfItemUpdate,
)
from services.app.shelf.services import shelf_service
from services.app.users.models import User


class ShelfServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Base.metadata.create_all(engine)

    @classmethod
    def tearDownClass(cls) -> None:
        engine.dispose()
        database_path = str(engine.url.database or "")
        if os.path.dirname(database_path) == tempfile.gettempdir() and os.path.basename(
            database_path
        ) in {"miplo-shelf-tests.db", "miplo-games-tests.db"}:
            try:
                os.unlink(database_path)
            except FileNotFoundError:
                pass

    def setUp(self) -> None:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        self.db = SessionLocal()
        self.user = User(firebase_uid="shelf-owner", tag="shelf_owner", is_active=True)
        self.other = User(firebase_uid="shelf-other", tag="shelf_other", is_active=True)
        self.games = [
            Game(
                bgg_id=100 + index,
                slug=f"game-{index}",
                title=f"Game {index}",
                min_players=1,
                max_players=index + 2,
                playing_time=30 * index,
                rating=Decimal(f"{6 + index}.25"),
                source="bgg",
                is_verified=True,
            )
            for index in range(1, 4)
        ]
        self.unverified = Game(
            slug="pending-custom",
            title="Pending Custom",
            source="custom",
            is_verified=False,
        )
        self.db.add_all([self.user, self.other, *self.games, self.unverified])
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def _add(self, game: Game, **overrides) -> ShelfItem:
        payload = ShelfItemCreate(game_slug=game.slug, **overrides)
        return shelf_service.add_to_shelf(self.db, self.user.id, payload)

    def test_create_schema_is_strict_and_rejects_unsafe_notes(self) -> None:
        with self.assertRaises(ValidationError):
            ShelfItemCreate(game_slug=self.games[0].slug, user_id=self.other.id)
        with self.assertRaises(ValidationError):
            ShelfItemCreate(game_slug=self.games[0].slug, notes="bad\x00note")
        with self.assertRaises(ValidationError):
            ShelfItemCreate(game_slug=self.games[0].slug, lending_deposit="10000")
        with self.assertRaises(ValidationError):
            ShelfItemCreate(game_slug="Game 1")
        with self.assertRaises(ValidationError):
            ShelfItemUpdate(lendable=None)

    def test_bgg_client_rejects_username_instead_of_silently_rewriting_it(self) -> None:
        with self.assertRaises(ApiError) as invalid_character:
            asyncio.run(bgg_client.fetch_collection("anna!"))
        self.assertEqual(
            invalid_character.exception.detail["error_code"],
            ErrorCode.INVALID_BGG_USERNAME.value,
        )
        with self.assertRaises(ApiError):
            asyncio.run(bgg_client.fetch_collection("a" * 51))

    def test_crud_is_scoped_to_current_user_and_duplicate_is_blocked(self) -> None:
        item = self._add(
            self.games[0],
            lendable=True,
            lending_deposit=Decimal("25.50"),
            condition=ShelfCondition.GOOD,
            notes="Prywatna notatka",
        )
        api_item = shelf_service.to_response(item).model_dump()
        self.assertNotIn("id", api_item)
        self.assertNotIn("game_id", api_item)
        self.assertEqual(api_item["game_slug"], self.games[0].slug)
        with self.assertRaises(ApiError) as duplicate:
            self._add(self.games[0])
        self.assertEqual(
            duplicate.exception.detail["error_code"],
            ErrorCode.GAME_ALREADY_ON_SHELF.value,
        )

        with self.assertRaises(ApiError) as other_user_error:
            shelf_service.update_shelf_item(
                self.db,
                self.other.id,
                self.games[0].slug,
                ShelfItemUpdate(lendable=True),
            )
        self.assertEqual(
            other_user_error.exception.detail["error_code"],
            ErrorCode.GAME_NOT_ON_SHELF.value,
        )

        updated = shelf_service.update_shelf_item(
            self.db,
            self.user.id,
            self.games[0].slug,
            ShelfItemUpdate(condition=ShelfCondition.USED, notes=None),
        )
        self.assertEqual(updated.condition, ShelfCondition.USED.value)
        self.assertIsNone(updated.notes)
        shelf_service.remove_from_shelf(self.db, self.user.id, self.games[0].slug)
        self.assertIsNone(self.db.get(ShelfItem, item.id))

    def test_unverified_game_cannot_bypass_moderation_through_shelf(self) -> None:
        with self.assertRaises(ApiError) as context:
            self._add(self.unverified)
        self.assertEqual(context.exception.detail["error_code"], ErrorCode.GAME_NOT_FOUND.value)

    def test_list_filters_sort_and_has_no_n_plus_one(self) -> None:
        self._add(self.games[0], lendable=True, condition=ShelfCondition.GOOD)
        self._add(self.games[1], lendable=False, condition=ShelfCondition.USED)
        user_id = self.user.id
        self.db.expire_all()
        statements: list[str] = []

        def count_selects(_conn, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", count_selects)
        try:
            result = shelf_service.get_my_shelf(
                self.db,
                user_id,
                1,
                20,
                lendable=True,
                players=2,
                condition=ShelfCondition.GOOD,
                sort=ShelfSort.GAME_RATING,
            )
        finally:
            event.remove(engine, "before_cursor_execute", count_selects)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0].game_slug, self.games[0].slug)
        self.assertEqual(
            len(statements),
            2,
            "\n\n".join(statements),
        )  # COUNT + jeden JOIN z games

    def test_public_shelf_never_contains_private_notes(self) -> None:
        self._add(
            self.games[0],
            lendable=False,
            lending_deposit=Decimal("50"),
            lending_notes="Ukryte, gdy nie wypożyczam",
            notes="Sekret właściciela",
        )
        public = shelf_service.get_user_shelf(self.db, self.user.tag, 1, 20)
        dumped = public.items[0].model_dump()
        self.assertNotIn("notes", dumped)
        self.assertEqual(public.items[0].game_playing_time, self.games[0].playing_time)
        self.assertIsNone(public.items[0].lending_deposit)
        self.assertIsNone(public.items[0].lending_notes)

        self.user.is_active = False
        self.db.commit()
        with self.assertRaises(ApiError) as context:
            shelf_service.get_user_shelf(self.db, self.user.tag, 1, 20)
        self.assertEqual(context.exception.detail["error_code"], ErrorCode.USER_NOT_FOUND.value)

    def test_stats_are_calculated_in_database(self) -> None:
        self._add(self.games[0], lendable=True)
        self._add(self.games[1], lendable=False)
        stats = shelf_service.get_shelf_stats(self.db, self.user.id)
        self.assertEqual(stats.total_games, 2)
        self.assertEqual(stats.lendable_games, 1)
        self.assertEqual(stats.total_playing_time, 90)

    def test_game_detail_contains_only_current_users_shelf_context(self) -> None:
        item = self._add(self.games[0], notes="Tylko moje")
        detail = game_service.to_detail(self.games[0], item)
        self.assertTrue(detail.on_my_shelf)
        self.assertEqual(detail.my_shelf_item.notes, "Tylko moje")
        anonymous = game_service.to_detail(self.games[0])
        self.assertFalse(anonymous.on_my_shelf)
        self.assertIsNone(anonymous.my_shelf_item)

    def test_optional_auth_is_anonymous_only_when_header_is_absent(self) -> None:
        anonymous_request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
        self.assertIsNone(get_current_user_optional(anonymous_request, None, self.db))
        malformed_request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"authorization", b"Basic abc")],
            }
        )
        with self.assertRaises(ApiError) as context:
            get_current_user_optional(malformed_request, None, self.db)
        self.assertEqual(context.exception.status_code, 401)

    def test_collection_import_batches_and_reports_partial_failures(self) -> None:
        self._add(self.games[0])
        collection = [
            bgg_client.BggCollectionItem(101, "Game 1", 2020, None),
            bgg_client.BggCollectionItem(102, "Game 2", 2021, None),
            bgg_client.BggCollectionItem(999, "Missing", 2022, None),
        ]
        with (
            patch.object(bgg_client, "fetch_collection", new=AsyncMock(return_value=collection)),
            patch.object(
                game_service,
                "get_or_fetch_games_batch",
                new=AsyncMock(return_value={101: self.games[0], 102: self.games[1]}),
            ),
        ):
            result = asyncio.run(
                shelf_service.import_bgg_collection(
                    self.db,
                    self.user.id,
                    CollectionImportRequest(bgg_username="valid_user"),
                )
            )
        self.assertEqual((result.imported, result.skipped, result.failed), (1, 1, 1))
        self.assertEqual(result.total_in_bgg, 3)

    def test_collection_import_can_import_bgg_ratings_without_overwriting(self) -> None:
        collection = [
            bgg_client.BggCollectionItem(101, "Game 1", 2020, Decimal("8.3")),
            bgg_client.BggCollectionItem(102, "Game 2", 2021, None),
        ]
        with (
            patch.object(bgg_client, "fetch_collection", new=AsyncMock(return_value=collection)),
            patch.object(
                game_service,
                "get_or_fetch_games_batch",
                new=AsyncMock(return_value={101: self.games[0], 102: self.games[1]}),
            ),
        ):
            result = asyncio.run(
                shelf_service.import_bgg_collection(
                    self.db,
                    self.user.id,
                    CollectionImportRequest(bgg_username="valid_user", import_ratings=True),
                )
            )
        rating = self.db.scalar(
            select(GameRating).where(
                GameRating.user_id == self.user.id,
                GameRating.game_id == self.games[0].id,
            )
        )
        self.assertEqual(result.ratings_imported, 1)
        self.assertEqual(rating.rating, Decimal("8.5"))
        self.assertEqual(rating.source, "bgg_import")

    def test_database_cascades_shelf_items_on_user_delete(self) -> None:
        item = self._add(self.games[0])
        item_id = item.id
        self.db.delete(self.user)
        self.db.commit()
        # Nowa sesja omija identity map i potwierdza faktyczny stan bazy.
        verification_db = SessionLocal()
        try:
            self.assertIsNone(verification_db.get(ShelfItem, item_id))
        finally:
            verification_db.close()


if __name__ == "__main__":
    unittest.main()
