from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.app.core.database import get_db
from services.app.users.models import User
from services.app.users.schemas import CreateUser, ReadUser

users_router = APIRouter(prefix="/users", tags=["Users"])


@users_router.post("/", response_model=ReadUser, status_code=status.HTTP_201_CREATED)
def create_user(payload: CreateUser, db: Session = Depends(get_db)) -> User:
    exists = db.scalar(select(User).where(User.firebase_uid == payload.firebase_uid))
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this firebase_uid already exists",
        )

    user = User(**payload.model_dump())
    db.add(user)
    db.flush()      # nadaje id; commit robi get_db po wyjściu z endpointu
    db.refresh(user)
    return user


@users_router.get("/", response_model=list[ReadUser])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    return list(db.scalars(select(User)).all())
