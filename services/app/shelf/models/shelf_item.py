"""Model egzemplarza gry znajdującego się na półce użytkownika."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.app.core.database import Base


class ShelfItem(Base):
    __tablename__ = "shelf_items"
    __table_args__ = (
        UniqueConstraint("user_id", "game_id", name="uq_shelf_items_user_game"),
        CheckConstraint(
            "condition IS NULL OR condition IN ('new', 'good', 'used', 'damaged')",
            name="ck_shelf_items_condition",
        ),
        CheckConstraint(
            "lending_deposit IS NULL OR "
            "(lending_deposit >= 0 AND lending_deposit <= 9999)",
            name="ck_shelf_items_deposit",
        ),
        CheckConstraint(
            "lending_notes IS NULL OR length(lending_notes) <= 500",
            name="ck_shelf_items_lending_notes_length",
        ),
        CheckConstraint(
            "notes IS NULL OR length(notes) <= 500",
            name="ck_shelf_items_notes_length",
        ),
        Index("ix_shelf_items_game_lendable", "game_id", "lendable"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
    )

    lendable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    lending_deposit: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    lending_notes: Mapped[str | None] = mapped_column(Text)
    condition: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)

    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="shelf_items")  # type: ignore[name-defined]
    game: Mapped["Game"] = relationship(back_populates="shelf_items")  # type: ignore[name-defined]
