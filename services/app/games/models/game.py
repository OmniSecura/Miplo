"""Modele ORM modułu games: cache BGG i gry dodawane przez społeczność."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.app.core.database import Base
from services.app.games.enums import GameLanguage


game_game_types = Table(
    "game_game_types",
    Base.metadata,
    Column("game_id", Integer, ForeignKey("games.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "game_type_id",
        Integer,
        ForeignKey("game_types.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    UniqueConstraint("game_id", "game_type_id", name="uq_game_game_types_pair"),
)


class GameType(Base):
    __tablename__ = "game_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)

    games: Mapped[list["Game"]] = relationship(
        secondary=game_game_types,
        back_populates="game_types",
    )


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint("source IN ('bgg', 'custom')", name="ck_games_source"),
        CheckConstraint(
            "model_status IS NULL OR model_status IN "
            "('pending', 'processing', 'awaiting_review', 'ready', 'failed')",
            name="ck_games_model_status",
        ),
        CheckConstraint("min_players IS NULL OR min_players >= 1", name="ck_games_min_players"),
        CheckConstraint(
            "max_players IS NULL OR min_players IS NULL OR max_players >= min_players",
            name="ck_games_players_range",
        ),
        CheckConstraint("rating IS NULL OR (rating >= 0 AND rating <= 10)", name="ck_games_rating"),
        CheckConstraint("weight IS NULL OR (weight >= 0 AND weight <= 5)", name="ck_games_weight"),
        Index("ix_games_title", "title"),
        Index("ix_games_is_expansion", "is_expansion"),
        Index("ix_games_bgg_rank", "bgg_rank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bgg_id: Mapped[int | None] = mapped_column(Integer, unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    year_published: Mapped[int | None] = mapped_column(SmallInteger)
    min_players: Mapped[int | None] = mapped_column(SmallInteger)
    max_players: Mapped[int | None] = mapped_column(SmallInteger)
    playing_time: Mapped[int | None] = mapped_column(SmallInteger)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    weight: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    cover_url: Mapped[str | None] = mapped_column(String(500))
    cover_candidate_path: Mapped[str | None] = mapped_column(String(500))
    instruction_url: Mapped[str | None] = mapped_column(String(500))

    bgg_rank: Mapped[int | None] = mapped_column(Integer)
    users_rated: Mapped[int | None] = mapped_column(Integer)
    is_expansion: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )

    box_width: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    box_height: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    box_depth: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    model_3d_url: Mapped[str | None] = mapped_column(String(500))
    model_status: Mapped[str | None] = mapped_column(String(20))
    model_candidate_path: Mapped[str | None] = mapped_column(String(500))
    model_job_id: Mapped[str | None] = mapped_column(String(36), index=True)
    model_submitted_by_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    model_is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    model_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[str] = mapped_column(String(10), nullable=False, default="bgg", server_default="bgg")
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    community_contributions_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    created_by_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    # NULL oznacza rekord zaimportowany tylko z rankingu, bez pełnych danych /thing.
    cached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    game_types: Mapped[list[GameType]] = relationship(
        secondary=game_game_types,
        back_populates="games",
        lazy="selectin",
    )
    images: Mapped[list["GameImage"]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="GameImage.created_at",
    )
    barcodes: Mapped[list["GameBarcode"]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="GameBarcode.language_code",
    )


class GameImage(Base):
    """Zdjęcie społecznościowe; prywatne do chwili akceptacji moderatora."""

    __tablename__ = "game_images"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved')", name="ck_game_images_status"),
        Index("ix_game_images_game_id", "game_id"),
        Index("ix_game_images_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        Uuid,
        unique=True,
        index=True,
        nullable=False,
        default=uuid4,
    )
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
    )
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500))
    caption: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    created_by_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    game: Mapped[Game] = relationship(back_populates="images")


class GameBarcode(Base):
    """Barcode konkretnej wersji językowej, moderowany jak pozostałe dane community."""

    __tablename__ = "game_barcodes"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved')", name="ck_game_barcodes_status"),
        CheckConstraint(
            "source IN ('community', 'legacy')",
            name="ck_game_barcodes_source",
        ),
        # EAN-8, UPC-A i EAN-13. Cyfry oraz suma kontrolna są dodatkowo
        # egzekwowane przez schemat wejściowy i game_service; produkcyjny DDL
        # ma równoważny constraint regex dla PostgreSQL.
        CheckConstraint(
            "length(barcode) IN (8, 12, 13)",
            name="ck_game_barcodes_format",
        ),
        UniqueConstraint(
            "game_id",
            "language_code",
            "status",
            name="uq_game_barcodes_game_language_status",
        ),
        Index("ix_game_barcodes_game_id", "game_id"),
        Index("ix_game_barcodes_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        Uuid,
        unique=True,
        index=True,
        nullable=False,
        default=uuid4,
    )
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
    )
    barcode: Mapped[str] = mapped_column(String(13), unique=True, index=True, nullable=False)
    language_code: Mapped[GameLanguage] = mapped_column(
        SqlEnum(
            GameLanguage,
            values_callable=lambda enum_type: [item.value for item in enum_type],
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            name="game_language",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="community", server_default="community"
    )
    created_by_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    game: Mapped[Game] = relationship(back_populates="barcodes")
