"""Zbiera routery wszystkich domen (monolit modularny — decyzja 0002).

Kolejne moduły (games, shelf, matchmaking, venues) dopinane tu jedną linią.
"""

from fastapi import APIRouter

from services.app.users.routers.router import users_router

api_router = APIRouter(prefix="/api")
api_router.include_router(users_router)
