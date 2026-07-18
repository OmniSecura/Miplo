"""Zbiera routery wszystkich domen (monolit modularny — decyzja 0002).

Kolejne moduły (games, shelf, matchmaking, venues) dopinane tu jedną linią.
"""

from fastapi import APIRouter

from services.app.users.routers.router import users_router
from services.app.games.routers.router import games_router
from services.app.games.routers.moderation_router import moderation_router
from services.app.shelf.routers.router import shelf_router
from services.app.ratings.routers import ratings_moderation_router, ratings_router

api_router = APIRouter(prefix="/api")
api_router.include_router(users_router)
api_router.include_router(ratings_router)
api_router.include_router(games_router)
api_router.include_router(shelf_router)
api_router.include_router(moderation_router)
api_router.include_router(ratings_moderation_router)
