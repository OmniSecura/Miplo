from fastapi import APIRouter
from services.app.users.routers.users_router import users_router

api_router = APIRouter(prefix="/api")
api_router.include_router(users_router)
