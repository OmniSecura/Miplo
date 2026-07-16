from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CreateUser(BaseModel):
    firebase_uid: str
    email: str | None = None
    display_name: str | None = None
    city: str | None = None


class ReadUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    firebase_uid: str
    email: str | None
    display_name: str | None
    city: str | None
    is_active: bool
    created_at: datetime
