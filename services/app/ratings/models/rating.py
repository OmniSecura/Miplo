"""Modele ocen Miplo oraz zgłoszeń recenzji."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

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
    Uuid,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.app.core.database import Base


class GameRating(Base):
    __tablename__ = "game_ratings"
    __table_args__ = (
        UniqueConstraint("user_id", "game_id", name="uq_user_game_rating"),
        CheckConstraint(
            "rating >= 1 AND rating <= 10 AND "
            "rating * 2 = CAST(rating * 2 AS INTEGER)",
            name="ck_game_ratings_value",
        ),
        CheckConstraint(
            "source IN ('miplo', 'bgg_import')",
            name="ck_game_ratings_source",
        ),
        CheckConstraint(
            "review IS NULL OR length(review) <= 5000",
            name="ck_game_ratings_review_length",
        ),
        CheckConstraint(
            "hidden_reason IS NULL OR length(hidden_reason) <= 200",
            name="ck_game_ratings_hidden_reason_length",
        ),
        Index("ix_ratings_game_rating", "game_id", "rating"),
        Index("ix_ratings_game_created", "game_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        Uuid,
        unique=True,
        index=True,
        nullable=False,
        default=uuid4,
    )
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
        index=True,
    )
    rating: Mapped[Decimal] = mapped_column(Numeric(3, 1), nullable=False)
    review: Mapped[str | None] = mapped_column(Text)
    contains_spoilers: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="miplo",
        server_default="miplo",
    )
    is_hidden: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    hidden_reason: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    author: Mapped["User"] = relationship(back_populates="ratings")  # type: ignore[name-defined]
    game: Mapped["Game"] = relationship(back_populates="ratings")  # type: ignore[name-defined]
    reports: Mapped[list["ReviewReport"]] = relationship(
        back_populates="rating",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ReviewReport(Base):
    __tablename__ = "review_reports"
    __table_args__ = (
        UniqueConstraint("user_id", "rating_id", name="uq_user_review_report"),
        CheckConstraint(
            "reason IN ('spam', 'offensive', 'spoilers', 'off_topic')",
            name="ck_review_reports_reason",
        ),
        CheckConstraint(
            "details IS NULL OR length(details) <= 500",
            name="ck_review_reports_details_length",
        ),
        Index("ix_review_reports_rating_resolved", "rating_id", "resolved"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rating_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("game_ratings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    reporter: Mapped["User"] = relationship(back_populates="review_reports")  # type: ignore[name-defined]
    rating: Mapped[GameRating] = relationship(back_populates="reports")
