"""Testy domeny ratings: walidacja, agregaty, moderacja i integracje."""

import os
import sys
import tempfile
import unittest
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

if "services.app.core.database" not in sys.modules:
    os.environ["ENV"] = "local"
    os.environ["SQLITE_PATH"] = os.path.join(tempfile.gettempdir(), "miplo-ratings-tests.db")
    os.environ.setdefault("FIREBASE_ADMIN_CREDENTIALS", "unused-in-unit-tests.json")
    os.environ.setdefault("FIREBASE_STORAGE_BUCKET", "unused-in-unit-tests")

from pydantic import ValidationError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.app.core import bgg_client
from services.app.core.database import Base, SessionLocal, engine
from services.app.core.errors import ApiError, ErrorCode, register_error_handlers
from services.app.games.models import Game
from services.app.games.services import game_service
from services.app.ratings.models import GameRating, ReviewReport
from services.app.ratings.schemas import (
    HideReviewRequest,
    RatingCreate,
    RatingUpdate,
    ReviewReportCreate,
)
from services.app.ratings.services import rating_service
from services.app.shelf.models import ShelfItem
from services.app.users.models import User


class RatingsServiceTests(unittest.TestCase):
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
        self.users = [
            User(firebase_uid=f"rating-uid-{index}", tag=f"rating_user_{index}", is_active=True)
            for index in range(1, 5)
        ]
        self.game = Game(
            slug="brass-birmingham",
            title="Brass: Birmingham",
            source="bgg",
            is_verified=True,
            rating=Decimal("8.56"),
            users_rated=1000,
            bgg_rank=1,
        )
        self.db.add_all([*self.users, self.game])
        self.db.commit()
        for item in [*self.users, self.game]:
            self.db.refresh(item)

    def tearDown(self) -> None:
        self.db.close()

    def _rate(
        self,
        user_index: int,
        value: str,
        review: str | None = None,
    ) -> GameRating:
        return rating_service.rate_game(
            self.db,
            self.users[user_index].id,
            self.game.slug,
            RatingCreate(rating=Decimal(value), review=review),
        )

    def test_schema_is_strict_half_step_and_plain_text(self) -> None:
        with self.assertRaises(ValidationError):
            RatingCreate(rating=Decimal("8.3"))
        with self.assertRaises(ValidationError):
            RatingCreate(rating=Decimal("0.5"))
        with self.assertRaises(ValidationError):
            RatingCreate(rating=Decimal("8.5"), admin=True)  # type: ignore[call-arg]
        with self.assertRaises(ValidationError):
            RatingCreate(rating=Decimal("8.5"), review="za krótko")
        payload = RatingCreate(
            rating=Decimal("8.5"),
            review="<b>Bardzo dobra gra ekonomiczna.</b>",
        )
        self.assertEqual(payload.review, "Bardzo dobra gra ekonomiczna.")
        with self.assertRaises(ValidationError):
            RatingCreate(rating=Decimal("8.5"), review="Bezpieczna recenzja\u202e z kontrolą")
        with self.assertRaises(ValidationError):
            RatingUpdate(rating=None)

    def test_http_validation_and_unknown_route_use_error_codes(self) -> None:
        app = FastAPI()
        register_error_handlers(app)

        @app.post("/rating")
        def validate_rating(payload: RatingCreate) -> None:
            return None

        client = TestClient(app, raise_server_exceptions=False)
        invalid = client.post("/rating", json={"rating": 8.3})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(
            invalid.json()["detail"]["error_code"],
            ErrorCode.VALIDATION_ERROR.value,
        )
        self.assertEqual(
            invalid.json()["detail"]["details"]["errors"][0]["field"],
            "rating",
        )
        missing = client.get("/does-not-exist")
        self.assertEqual(
            missing.json()["detail"]["error_code"],
            ErrorCode.ROUTE_NOT_FOUND.value,
        )

    def test_crud_is_scoped_to_token_user_and_recalculates(self) -> None:
        created = self._rate(0, "8.5", "Bardzo dobra gra ekonomiczna.")
        self.db.refresh(self.game)
        self.assertEqual(self.game.miplo_rating, Decimal("8.5"))
        self.assertEqual((self.game.miplo_ratings_count, self.game.miplo_reviews_count), (1, 1))
        self.assertNotIn("user_id", rating_service.to_response(created).model_dump())
        self.assertNotIn("game_id", rating_service.to_response(created).model_dump())

        with self.assertRaises(ApiError) as duplicate:
            self._rate(0, "7.0")
        self.assertEqual(duplicate.exception.detail["error_code"], ErrorCode.ALREADY_RATED.value)

        with self.assertRaises(ApiError) as other_user:
            rating_service.update_rating(
                self.db,
                self.users[1].id,
                self.game.slug,
                RatingUpdate(rating=Decimal("1.0")),
            )
        self.assertEqual(other_user.exception.detail["error_code"], ErrorCode.NOT_RATED_YET.value)

        updated = rating_service.update_rating(
            self.db,
            self.users[0].id,
            self.game.slug,
            RatingUpdate(rating=Decimal("9.0"), review=None),
        )
        self.assertEqual(updated.rating, Decimal("9.0"))
        self.assertIsNone(updated.review)
        rating_service.delete_rating(self.db, self.users[0].id, self.game.slug)
        self.db.refresh(self.game)
        self.assertEqual(self.game.miplo_ratings_count, 0)
        self.assertIsNone(self.game.miplo_rating)

    def test_threshold_distribution_combined_and_personal_context(self) -> None:
        self._rate(0, "9.0", "Wybitna gra, która nagradza planowanie.")
        first = rating_service.get_ratings_summary(self.db, self.game.slug, self.users[0].id)
        self.assertIsNone(first.miplo_rating)
        self.assertIsNone(first.miplo_distribution)
        self.assertEqual(first.combined_rating, Decimal("8.56"))

        self._rate(1, "7.0")
        self._rate(2, "8.0")
        self.db.add(ShelfItem(user_id=self.users[0].id, game_id=self.game.id))
        self.db.commit()
        summary = rating_service.get_ratings_summary(self.db, self.game.slug, self.users[0].id)
        self.assertEqual(summary.miplo_rating, Decimal("8.0"))
        self.assertEqual(summary.miplo_distribution.rating_7_8, 2)
        self.assertEqual(summary.miplo_distribution.rating_9_10, 1)
        self.assertEqual(summary.my_rating, Decimal("9.0"))
        self.assertTrue(summary.has_game_on_shelf)
        self.assertEqual(summary.combined_rating, Decimal("8.56"))

    def test_report_hide_and_restore_excludes_rating_from_public_data(self) -> None:
        rating = self._rate(0, "2.0", "Recenzja nadająca się do zgłoszenia.")
        self._rate(2, "8.0")
        self._rate(3, "9.0")
        report = ReviewReportCreate(reason="offensive", details="Narusza zasady społeczności.")
        rating_service.report_review(
            self.db, self.users[1].id, self.game.slug, rating.public_id, report
        )
        with self.assertRaises(ApiError) as own_report:
            rating_service.report_review(
                self.db, self.users[0].id, self.game.slug, rating.public_id, report
            )
        self.assertEqual(
            own_report.exception.detail["error_code"],
            ErrorCode.CANNOT_REPORT_OWN_REVIEW.value,
        )
        with self.assertRaises(ApiError) as duplicate:
            rating_service.report_review(
                self.db, self.users[1].id, self.game.slug, rating.public_id, report
            )
        self.assertEqual(
            duplicate.exception.detail["error_code"], ErrorCode.REVIEW_ALREADY_REPORTED.value
        )
        queue = rating_service.list_reported_reviews(self.db, 100)
        self.assertEqual(queue[0].rating_public_id, rating.public_id)
        self.assertEqual(queue[0].report_count, 1)

        rating_service.hide_rating(
            self.db,
            rating.public_id,
            HideReviewRequest(reason="Naruszenie zasad społeczności."),
        )
        visible = rating_service.get_game_ratings(self.db, self.game.slug, 1, 20)
        self.assertEqual(visible.total, 2)
        self.db.refresh(self.game)
        self.assertEqual(self.game.miplo_ratings_count, 2)
        rating_service.restore_rating(self.db, rating.public_id)
        self.db.refresh(self.game)
        self.assertEqual(self.game.miplo_ratings_count, 3)
        self.assertEqual(
            self.db.scalar(select(ReviewReport).where(ReviewReport.rating_id == rating.id)).resolved,
            True,
        )

    def test_restore_also_dismisses_invalid_open_reports(self) -> None:
        rating = self._rate(0, "8.0", "Poprawna recenzja zgłoszona przez pomyłkę.")
        rating_service.report_review(
            self.db,
            self.users[1].id,
            self.game.slug,
            rating.public_id,
            ReviewReportCreate(reason="off_topic"),
        )
        rating_service.restore_rating(self.db, rating.public_id)
        self.assertEqual(rating_service.list_reported_reviews(self.db, 100), [])
        report = self.db.scalar(select(ReviewReport))
        self.assertTrue(report.resolved)
        self.assertFalse(self.db.get(GameRating, rating.id).is_hidden)

    def test_many_users_can_report_one_review_and_queue_prioritizes_it(self) -> None:
        most_reported = self._rate(
            0,
            "4.0",
            "Pierwsza recenzja do testu priorytetu moderacji.",
        )
        other_review = self._rate(
            1,
            "6.0",
            "Druga recenzja z mniejszą liczbą zgłoszeń.",
        )
        payload = ReviewReportCreate(reason="spam")
        rating_service.report_review(
            self.db, self.users[1].id, self.game.slug, most_reported.public_id, payload
        )
        rating_service.report_review(
            self.db, self.users[2].id, self.game.slug, most_reported.public_id, payload
        )
        rating_service.report_review(
            self.db, self.users[3].id, self.game.slug, other_review.public_id, payload
        )

        queue = rating_service.list_reported_reviews(self.db, 100)
        self.assertEqual([item.report_count for item in queue], [2, 1])
        self.assertEqual(queue[0].rating_public_id, most_reported.public_id)
        self.assertEqual(len(queue[0].reports), 2)

    def test_bgg_upsert_whitelist_preserves_all_miplo_and_custom_fields(self) -> None:
        self.game.miplo_rating = Decimal("9.0")
        self.game.miplo_ratings_count = 5
        self.game.miplo_reviews_count = 2
        self.game.box_width = Decimal("29.50")
        self.game.model_3d_url = "https://storage.example/model.glb"
        self.db.commit()
        data = bgg_client.BggGameData(
            bgg_id=224517,
            title="Brass: Birmingham Updated",
            description="Nowy opis",
            year_published=2018,
            min_players=2,
            max_players=4,
            playing_time=120,
            rating=Decimal("8.60"),
            weight=Decimal("3.90"),
            users_rated=2000,
            bgg_rank=2,
            cover_url="https://cf.geekdo-images.com/cover.jpg",
            categories=["Economic"],
        )
        game_service._apply_bgg_data(self.db, data, self.game)
        self.db.flush()
        self.assertEqual(self.game.miplo_rating, Decimal("9.0"))
        self.assertEqual(self.game.miplo_ratings_count, 5)
        self.assertEqual(self.game.miplo_reviews_count, 2)
        self.assertEqual(self.game.box_width, Decimal("29.50"))
        self.assertEqual(self.game.model_3d_url, "https://storage.example/model.glb")
        self.assertEqual(self.game.users_rated, 2000)

    def test_stale_bgg_fetch_preserves_miplo_aggregates_end_to_end(self) -> None:
        self._rate(0, "9.0")
        self.game.bgg_id = 224517
        self.game.cached_at = datetime.now(timezone.utc) - timedelta(days=2)
        self.db.commit()
        remote = bgg_client.BggGameData(
            bgg_id=224517,
            title="Brass: Birmingham",
            description="Odświeżony opis",
            year_published=2018,
            min_players=2,
            max_players=4,
            playing_time=120,
            rating=Decimal("8.60"),
            weight=Decimal("3.90"),
            users_rated=2000,
            bgg_rank=2,
            cover_url="https://cf.geekdo-images.com/cover.jpg",
            categories=["Economic"],
        )
        with patch(
            "services.app.games.services.game_service.bgg_client.fetch_game",
            new=AsyncMock(return_value=remote),
        ):
            refreshed = asyncio.run(game_service.get_or_fetch_game(self.db, 224517))
        self.assertEqual(refreshed.miplo_rating, Decimal("9.0"))
        self.assertEqual(refreshed.miplo_ratings_count, 1)

    def test_removing_game_from_shelf_does_not_remove_rating(self) -> None:
        rating = self._rate(0, "8.0")
        self.db.add(ShelfItem(user_id=self.users[0].id, game_id=self.game.id))
        self.db.commit()
        from services.app.shelf.services import shelf_service

        shelf_service.remove_from_shelf(self.db, self.users[0].id, self.game.slug)
        self.assertIsNotNone(self.db.get(GameRating, rating.id))

    def test_bgg_import_rounds_half_step_and_never_overwrites(self) -> None:
        self._rate(0, "6.0")
        imported = rating_service.import_from_bgg(
            self.db,
            self.users[0].id,
            [(self.game.id, Decimal("9.2"))],
        )
        self.assertEqual(imported, 0)
        second_game = Game(slug="second", title="Second", source="bgg", is_verified=True)
        self.db.add(second_game)
        self.db.commit()
        imported = rating_service.import_from_bgg(
            self.db,
            self.users[0].id,
            [(second_game.id, Decimal("8.3"))],
        )
        item = self.db.scalar(
            select(GameRating).where(
                GameRating.user_id == self.users[0].id,
                GameRating.game_id == second_game.id,
            )
        )
        self.assertEqual(imported, 1)
        self.assertEqual(item.rating, Decimal("8.5"))
        self.assertEqual(item.source, "bgg_import")

    def test_game_detail_and_shelf_expose_only_trusted_miplo_score(self) -> None:
        self._rate(0, "9.0")
        own = rating_service.get_user_rating(self.db, self.users[0].id, self.game.id)
        detail = game_service.to_detail(self.game, my_rating=own)
        self.assertIsNone(detail.miplo_rating)
        self.assertEqual(detail.my_rating, Decimal("9.0"))
        self._rate(1, "8.0")
        self._rate(2, "7.0")
        self.db.refresh(self.game)
        self.assertEqual(game_service.to_list_item(self.game).miplo_rating, Decimal("8.0"))

    def test_delete_user_cascades_ratings_and_reports(self) -> None:
        rating = self._rate(0, "8.0", "Pełna, bezpieczna recenzja testowa.")
        rating_service.report_review(
            self.db,
            self.users[1].id,
            self.game.slug,
            rating.public_id,
            ReviewReportCreate(reason="spam"),
        )
        rating_id = rating.id
        self.db.delete(self.users[0])
        self.db.commit()
        self.db.expire_all()
        verification_db = SessionLocal()
        try:
            self.assertIsNone(verification_db.get(GameRating, rating_id))
            self.assertEqual(verification_db.scalar(select(ReviewReport)), None)
        finally:
            verification_db.close()


if __name__ == "__main__":
    unittest.main()
