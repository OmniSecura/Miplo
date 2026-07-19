"""Krytyczne testy uruchamiane w CI niezależnie od szerszej regresji domen."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import patch

import httpx
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from services.app.core import bgg_client
from services.app.core.config import settings
from services.app.games.models import Game
from services.app.games.services import game_service
from services.app.server import app


def test_health_endpoint_reports_database_and_bgg_attribution() -> None:
    client = TestClient(app)
    try:
        with patch("services.app.server.ping", return_value=True):
            response = client.get("/health")
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "reachable",
        "attribution": {
            "name": "Powered by BoardGameGeek data",
            "url": "https://boardgamegeek.com",
        },
    }


def test_bgg_refresh_never_overwrites_miplo_fields(db: Session) -> None:
    game = Game(
        bgg_id=224517,
        slug="brass-birmingham",
        title="Brass: Birmingham",
        source="bgg",
        is_verified=True,
        miplo_rating=Decimal("9.20"),
        miplo_ratings_count=14,
        miplo_reviews_count=7,
        box_width=Decimal("29.50"),
        box_height=Decimal("29.50"),
        box_depth=Decimal("7.00"),
        model_3d_url="https://storage.googleapis.com/miplo/box.glb",
        model_status="ready",
        community_contributions_enabled=False,
    )
    db.add(game)
    db.commit()

    data = bgg_client.BggGameData(
        bgg_id=224517,
        title="Updated by BGG",
        description="Updated description",
        year_published=2018,
        min_players=2,
        max_players=4,
        playing_time=120,
        rating=Decimal("8.60"),
        weight=Decimal("3.90"),
        users_rated=50_000,
        bgg_rank=1,
        cover_url="https://cf.geekdo-images.com/cover.webp",
        categories=[],
    )
    game_service._apply_bgg_data(db, data, game)
    db.commit()
    db.refresh(game)

    assert game.title == "Updated by BGG"
    assert game.rating == Decimal("8.60")
    assert game.miplo_rating == Decimal("9.20")
    assert game.miplo_ratings_count == 14
    assert game.miplo_reviews_count == 7
    assert game.box_width == Decimal("29.50")
    assert game.model_3d_url == "https://storage.googleapis.com/miplo/box.glb"
    assert game.model_status == "ready"
    assert game.community_contributions_enabled is False


def test_slug_collision_gets_deterministic_numeric_suffix(db: Session) -> None:
    db.add(
        Game(
            slug="brass-birmingham",
            title="Existing game",
            source="custom",
            is_verified=False,
        )
    )
    db.commit()

    assert game_service._generate_slug(db, "Brass: Birmingham") == "brass-birmingham-2"


@respx.mock
def test_bgg_search_uses_http_mock_and_never_real_network() -> None:
    route = respx.get("https://boardgamegeek.com/xmlapi2/search").mock(
        return_value=httpx.Response(
            200,
            text=(
                '<items><item id="224517">'
                '<name type="primary" value="Brass: Birmingham"/>'
                '<yearpublished value="2018"/>'
                "</item></items>"
            ),
        )
    )
    bgg_client._reset_runtime_state_for_tests()

    with (
        patch.object(settings, "BGG_API_TOKEN", "mock-token"),
        patch.object(settings, "BGG_MIN_REQUEST_INTERVAL", 0.0),
    ):
        results = asyncio.run(bgg_client.search("Brass"))

    assert route.called
    assert [(item.bgg_id, item.title) for item in results] == [(224517, "Brass: Birmingham")]
