from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func, true
from sqlalchemy.orm import Mapped, mapped_column

from services.app.core.database import Base


class User(Base):
    """Cień tożsamości z Firebase + dane apki.

    Firebase trzyma: hasła, MFA, OAuth providery, lockout, weryfikację maila.
    Tu TYLKO: most do Firebase (firebase_uid) + dane Miplo.
    Odpowiednik SQL: database/sql/tables/users/users.sql.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # SERIAL
    firebase_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    # Techniczny, publiczny identyfikator (tag): unique, [a-z0-9_], do URL-i i API.
    # Generowany przy pierwszym logowaniu, edytowalny przez PUT /me.
    tag: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320))
    # Wyświetlana nazwa: NIE-unikalna, dowolny Unicode — UI dokleja tag
    # w nawiasie tylko przy kolizji w widoku.
    display_name: Mapped[str | None] = mapped_column(String(80))
    city: Mapped[str | None] = mapped_column(String(120), index=True)  # pod matchmaking
    bio: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(String(500))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
