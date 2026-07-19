"""Operacje bazodanowe ocen, agregaty, import i moderacja recenzji."""

import math
from decimal import ROUND_HALF_UP, Decimal
from typing import cast as type_cast
from uuid import UUID

from sqlalchemy import Numeric, case, cast, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager, joinedload, selectinload

from services.app.core.errors import ApiError, ErrorCode
from services.app.games.models import Game
from services.app.games.services import game_service
from services.app.ratings.constants import MIPLO_MIN_RATINGS_FOR_DISPLAY
from services.app.ratings.enums import RatingSort, RatingSource, ReviewReportReason
from services.app.ratings.models import GameRating, ReviewReport
from services.app.ratings.schemas import (
    GameRatingsSummary,
    HideReviewRequest,
    MyRatingResponse,
    PaginatedMyRatings,
    PaginatedRatings,
    RatingAuthor,
    RatingCreate,
    RatingDistribution,
    RatingResponse,
    RatingUpdate,
    ReportedReviewModeration,
    ReviewReportCreate,
    ReviewReportItem,
    UserRatingStats,
)
from services.app.users.models import User


def _round(value: object, places: str) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _public_game(db: Session, slug: str) -> Game:
    game = game_service.get_game_by_slug(db, slug)
    if game is None or not game.is_verified:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    return game


def _rating_query():
    game_eager = contains_eager(GameRating.game)
    author_eager = contains_eager(GameRating.author)
    return (
        select(GameRating)
        .join(GameRating.author)
        .join(GameRating.game)
        .options(
            game_eager.noload(Game.game_types),
            game_eager.noload(Game.images),
            game_eager.noload(Game.barcodes),
            game_eager.noload(Game.shelf_items),
            game_eager.noload(Game.ratings),
            author_eager.noload(User.shelf_items),
            author_eager.noload(User.ratings),
            author_eager.noload(User.review_reports),
        )
    )


def to_response(item: GameRating) -> RatingResponse:
    return RatingResponse(
        public_id=item.public_id,
        game_slug=item.game.slug,
        rating=item.rating,
        review=item.review,
        contains_spoilers=item.contains_spoilers,
        source=RatingSource(item.source),
        created_at=item.created_at,
        updated_at=item.updated_at,
        author=RatingAuthor(
            tag=item.author.tag,
            display_name=item.author.display_name,
            avatar_url=item.author.avatar_url,
        ),
    )


def to_my_response(item: GameRating) -> MyRatingResponse:
    return MyRatingResponse(
        public_id=item.public_id,
        game_slug=item.game.slug,
        game_title=item.game.title,
        game_cover_url=item.game.cover_url,
        rating=item.rating,
        review=item.review,
        contains_spoilers=item.contains_spoilers,
        source=RatingSource(item.source),
        is_hidden=item.is_hidden,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _get_user_rating(db: Session, user_id: int, game_id: int) -> GameRating | None:
    return type_cast(
        GameRating | None,
        db.scalar(
            _rating_query().where(
                GameRating.user_id == user_id,
                GameRating.game_id == game_id,
            )
        ),
    )


def get_user_rating(db: Session, user_id: int, game_id: int) -> GameRating | None:
    """Kontekst własnej oceny używany przez publiczny GameDetail."""
    return _get_user_rating(db, user_id, game_id)


def recalculate_game_rating(db: Session, game_id: int) -> None:
    average, ratings_count, reviews_count = db.execute(
        select(
            func.avg(GameRating.rating),
            func.count(GameRating.id),
            func.sum(case((GameRating.review.is_not(None), 1), else_=0)),
        ).where(
            GameRating.game_id == game_id,
            GameRating.is_hidden.is_(False),
        )
    ).one()
    game = db.get(Game, game_id)
    if game is None:
        return
    game.miplo_rating = _round(average, "0.1")
    game.miplo_ratings_count = int(ratings_count or 0)
    game.miplo_reviews_count = int(reviews_count or 0)
    db.flush()


def recalculate_batch(db: Session, game_ids: set[int]) -> None:
    if not game_ids:
        return
    visible = (
        GameRating.game_id == Game.id,
        GameRating.is_hidden.is_(False),
    )
    average = select(func.avg(GameRating.rating)).where(*visible).scalar_subquery()
    ratings_count = select(func.count(GameRating.id)).where(*visible).scalar_subquery()
    reviews_count = (
        select(func.count(GameRating.id))
        .where(*visible, GameRating.review.is_not(None))
        .scalar_subquery()
    )
    # Jeden zbiorczy UPDATE również dla gier, którym usunięto ostatnią ocenę.
    # Numeric(3,1) wymusza ten sam format agregatu na PostgreSQL i SQLite.
    db.execute(
        update(Game)
        .where(Game.id.in_(game_ids))
        .values(
            miplo_rating=cast(average, Numeric(3, 1)),
            miplo_ratings_count=ratings_count,
            miplo_reviews_count=reviews_count,
        )
        .execution_options(synchronize_session="fetch")
    )
    db.flush()


def rate_game(db: Session, user_id: int, slug: str, data: RatingCreate) -> GameRating:
    game = _public_game(db, slug)
    if _get_user_rating(db, user_id, game.id) is not None:
        raise ApiError.conflict(ErrorCode.ALREADY_RATED)
    item = GameRating(
        user_id=user_id,
        game_id=game.id,
        rating=data.rating,
        review=data.review,
        contains_spoilers=data.contains_spoilers,
        source=RatingSource.MIPLO.value,
    )
    db.add(item)
    try:
        db.flush()
        recalculate_game_rating(db, game.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError.conflict(ErrorCode.ALREADY_RATED)
    return _get_user_rating(db, user_id, game.id) or item


def update_rating(
    db: Session,
    user_id: int,
    slug: str,
    data: RatingUpdate,
) -> GameRating:
    game = _public_game(db, slug)
    item = _get_user_rating(db, user_id, game.id)
    if item is None:
        raise ApiError.not_found(ErrorCode.NOT_RATED_YET)
    if item.is_hidden:
        raise ApiError.forbidden(ErrorCode.RATING_HIDDEN)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(item, field, value)
    db.flush()
    recalculate_game_rating(db, game.id)
    db.commit()
    return _get_user_rating(db, user_id, game.id) or item


def delete_rating(db: Session, user_id: int, slug: str) -> None:
    game = _public_game(db, slug)
    item = _get_user_rating(db, user_id, game.id)
    if item is None:
        raise ApiError.not_found(ErrorCode.NOT_RATED_YET)
    db.delete(item)
    db.flush()
    recalculate_game_rating(db, game.id)
    db.commit()


def _apply_rating_filters(query, *, with_review, min_rating, max_rating):
    if with_review is True:
        query = query.where(GameRating.review.is_not(None))
    elif with_review is False:
        query = query.where(GameRating.review.is_(None))
    if min_rating is not None:
        query = query.where(GameRating.rating >= min_rating)
    if max_rating is not None:
        query = query.where(GameRating.rating <= max_rating)
    return query


def _apply_sort(query, sort: RatingSort):
    if sort is RatingSort.RATING_DESC:
        return query.order_by(GameRating.rating.desc(), GameRating.created_at.desc())
    if sort is RatingSort.RATING_ASC:
        return query.order_by(GameRating.rating.asc(), GameRating.created_at.desc())
    return query.order_by(GameRating.created_at.desc(), GameRating.id.desc())


def get_game_ratings(
    db: Session,
    slug: str,
    page: int,
    size: int,
    *,
    with_review: bool | None = None,
    min_rating: Decimal | None = None,
    max_rating: Decimal | None = None,
    sort: RatingSort = RatingSort.NEWEST,
) -> PaginatedRatings:
    game = _public_game(db, slug)
    filters = [GameRating.game_id == game.id, GameRating.is_hidden.is_(False)]
    count_query = _apply_rating_filters(
        select(GameRating.id).where(*filters),
        with_review=with_review,
        min_rating=min_rating,
        max_rating=max_rating,
    )
    total = db.scalar(select(func.count()).select_from(count_query.subquery())) or 0
    query = _apply_rating_filters(
        _rating_query().where(*filters),
        with_review=with_review,
        min_rating=min_rating,
        max_rating=max_rating,
    )
    items = (
        db.scalars(_apply_sort(query, sort).offset((page - 1) * size).limit(size)).unique().all()
    )
    return PaginatedRatings(
        items=[to_response(item) for item in items],
        total=total,
        page=page,
        size=size,
        pages=math.ceil(total / size),
    )


def get_my_ratings(
    db: Session,
    user_id: int,
    page: int,
    size: int,
    *,
    with_review: bool | None = None,
    sort: RatingSort = RatingSort.NEWEST,
) -> PaginatedMyRatings:
    filters = [GameRating.user_id == user_id]
    count_query = _apply_rating_filters(
        select(GameRating.id).where(*filters),
        with_review=with_review,
        min_rating=None,
        max_rating=None,
    )
    total = db.scalar(select(func.count()).select_from(count_query.subquery())) or 0
    query = _apply_rating_filters(
        _rating_query().where(*filters),
        with_review=with_review,
        min_rating=None,
        max_rating=None,
    )
    items = (
        db.scalars(_apply_sort(query, sort).offset((page - 1) * size).limit(size)).unique().all()
    )
    return PaginatedMyRatings(
        items=[to_my_response(item) for item in items],
        total=total,
        page=page,
        size=size,
        pages=math.ceil(total / size),
    )


def get_user_ratings(
    db: Session,
    tag: str,
    page: int,
    size: int,
    *,
    with_review: bool | None = None,
    sort: RatingSort = RatingSort.NEWEST,
) -> PaginatedRatings:
    user = db.scalar(select(User).where(User.tag == tag, User.is_active.is_(True)))
    if user is None:
        raise ApiError.not_found(ErrorCode.USER_NOT_FOUND)
    filters = [GameRating.user_id == user.id, GameRating.is_hidden.is_(False)]
    count_query = _apply_rating_filters(
        select(GameRating.id).where(*filters),
        with_review=with_review,
        min_rating=None,
        max_rating=None,
    )
    total = db.scalar(select(func.count()).select_from(count_query.subquery())) or 0
    query = _apply_rating_filters(
        _rating_query().where(*filters),
        with_review=with_review,
        min_rating=None,
        max_rating=None,
    )
    items = (
        db.scalars(_apply_sort(query, sort).offset((page - 1) * size).limit(size)).unique().all()
    )
    return PaginatedRatings(
        items=[to_response(item) for item in items],
        total=total,
        page=page,
        size=size,
        pages=math.ceil(total / size),
    )


def get_user_rating_stats(db: Session, user_id: int) -> UserRatingStats:
    total, reviews, average, highest, lowest = db.execute(
        select(
            func.count(GameRating.id),
            func.sum(case((GameRating.review.is_not(None), 1), else_=0)),
            func.avg(GameRating.rating),
            func.max(GameRating.rating),
            func.min(GameRating.rating),
        ).where(
            GameRating.user_id == user_id,
            GameRating.is_hidden.is_(False),
        )
    ).one()
    return UserRatingStats(
        total_ratings=int(total or 0),
        total_reviews=int(reviews or 0),
        avg_rating=_round(average, "0.1"),
        most_generous_score=_round(highest, "0.1"),
        harshest_score=_round(lowest, "0.1"),
    )


def get_ratings_summary(
    db: Session,
    slug: str,
    current_user_id: int | None,
) -> GameRatingsSummary:
    game = _public_game(db, slug)
    row = db.execute(
        select(
            func.sum(case((GameRating.rating < 3, 1), else_=0)),
            func.sum(case((GameRating.rating.between(3, Decimal("4.5")), 1), else_=0)),
            func.sum(case((GameRating.rating.between(5, Decimal("6.5")), 1), else_=0)),
            func.sum(case((GameRating.rating.between(7, Decimal("8.5")), 1), else_=0)),
            func.sum(case((GameRating.rating >= 9, 1), else_=0)),
        ).where(
            GameRating.game_id == game.id,
            GameRating.is_hidden.is_(False),
        )
    ).one()
    trusted = game.miplo_ratings_count >= MIPLO_MIN_RATINGS_FOR_DISPLAY
    distribution = None
    if trusted:
        distribution = RatingDistribution(
            rating_1_2=int(row[0] or 0),
            rating_3_4=int(row[1] or 0),
            rating_5_6=int(row[2] or 0),
            rating_7_8=int(row[3] or 0),
            rating_9_10=int(row[4] or 0),
        )
    public_miplo = game.miplo_rating if trusted else None
    bgg_count = int(game.users_rated or 0)
    miplo_count = game.miplo_ratings_count if trusted else 0
    combined = None
    if game.rating is not None and bgg_count > 0 and public_miplo is not None:
        combined = _round(
            (game.rating * bgg_count + public_miplo * miplo_count) / (bgg_count + miplo_count),
            "0.01",
        )
    elif game.rating is not None and bgg_count > 0:
        combined = _round(game.rating, "0.01")
    elif public_miplo is not None:
        combined = _round(public_miplo, "0.01")

    own = None
    has_game = False
    if current_user_id is not None:
        own = _get_user_rating(db, current_user_id, game.id)
        from services.app.shelf.services import shelf_service

        has_game = shelf_service.is_on_shelf(db, current_user_id, game.id) is not None
    return GameRatingsSummary(
        bgg_rating=game.rating,
        bgg_ratings_count=game.users_rated,
        bgg_rank=game.bgg_rank,
        miplo_rating=public_miplo,
        miplo_ratings_count=game.miplo_ratings_count,
        miplo_reviews_count=game.miplo_reviews_count,
        miplo_distribution=distribution,
        combined_rating=combined,
        my_rating=own.rating if own is not None else None,
        my_review=own.review if own is not None else None,
        has_game_on_shelf=has_game,
    )


def _normalize_import_rating(value: Decimal) -> Decimal | None:
    if value < 1 or value > 10:
        return None
    return ((value * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 2).quantize(Decimal("0.1"))


def import_from_bgg(
    db: Session,
    user_id: int,
    ratings: list[tuple[int, Decimal]],
    *,
    commit: bool = True,
) -> int:
    game_ids = {game_id for game_id, _ in ratings}
    existing = (
        set(
            db.scalars(
                select(GameRating.game_id).where(
                    GameRating.user_id == user_id,
                    GameRating.game_id.in_(game_ids),
                )
            ).all()
        )
        if game_ids
        else set()
    )
    imported = 0
    affected: set[int] = set()
    for game_id, raw_rating in dict(ratings).items():
        if game_id in existing:
            continue
        normalized = _normalize_import_rating(raw_rating)
        if normalized is None:
            continue
        try:
            with db.begin_nested():
                db.add(
                    GameRating(
                        user_id=user_id,
                        game_id=game_id,
                        rating=normalized,
                        source=RatingSource.BGG_IMPORT.value,
                    )
                )
                db.flush()
        except IntegrityError:
            continue
        imported += 1
        affected.add(game_id)
        existing.add(game_id)
    recalculate_batch(db, affected)
    if commit:
        db.commit()
    return imported


def report_review(
    db: Session,
    user_id: int,
    slug: str,
    rating_public_id: UUID,
    data: ReviewReportCreate,
) -> None:
    game = _public_game(db, slug)
    rating = db.scalar(
        select(GameRating).where(
            GameRating.public_id == rating_public_id,
            GameRating.game_id == game.id,
            GameRating.review.is_not(None),
            GameRating.is_hidden.is_(False),
        )
    )
    if rating is None:
        raise ApiError.not_found(ErrorCode.RATING_NOT_FOUND)
    if rating.user_id == user_id:
        raise ApiError.forbidden(ErrorCode.CANNOT_REPORT_OWN_REVIEW)
    db.add(
        ReviewReport(
            user_id=user_id,
            rating_id=rating.id,
            reason=data.reason.value,
            details=data.details,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError.conflict(ErrorCode.REVIEW_ALREADY_REPORTED)


def list_reported_reviews(db: Session, limit: int) -> list[ReportedReviewModeration]:
    report_count = (
        select(func.count(ReviewReport.id))
        .where(
            ReviewReport.rating_id == GameRating.id,
            ReviewReport.resolved.is_(False),
        )
        .correlate(GameRating)
        .scalar_subquery()
    )
    ratings = (
        db.scalars(
            select(GameRating)
            .where(report_count > 0, GameRating.review.is_not(None))
            .options(
                joinedload(GameRating.author),
                joinedload(GameRating.game),
                selectinload(GameRating.reports).joinedload(ReviewReport.reporter),
            )
            .order_by(report_count.desc(), GameRating.created_at.asc())
            .limit(limit)
        )
        .unique()
        .all()
    )
    result: list[ReportedReviewModeration] = []
    for rating in ratings:
        reports = [report for report in rating.reports if not report.resolved]
        result.append(
            ReportedReviewModeration(
                rating_public_id=rating.public_id,
                game_slug=rating.game.slug,
                game_title=rating.game.title,
                rating=rating.rating,
                review=rating.review or "",
                contains_spoilers=rating.contains_spoilers,
                author=RatingAuthor(
                    tag=rating.author.tag,
                    display_name=rating.author.display_name,
                    avatar_url=rating.author.avatar_url,
                ),
                report_count=len(reports),
                reports=[
                    ReviewReportItem(
                        reason=ReviewReportReason(report.reason),
                        details=report.details,
                        reporter_tag=report.reporter.tag,
                        created_at=report.created_at,
                    )
                    for report in reports
                ],
                created_at=rating.created_at,
            )
        )
    return result


def hide_rating(
    db: Session,
    rating_public_id: UUID,
    data: HideReviewRequest,
) -> None:
    rating = db.scalar(select(GameRating).where(GameRating.public_id == rating_public_id))
    if rating is None:
        raise ApiError.not_found(ErrorCode.RATING_NOT_FOUND)
    rating.is_hidden = True
    rating.hidden_reason = data.reason
    for report in db.scalars(
        select(ReviewReport).where(
            ReviewReport.rating_id == rating.id,
            ReviewReport.resolved.is_(False),
        )
    ).all():
        report.resolved = True
    db.flush()
    recalculate_game_rating(db, rating.game_id)
    db.commit()


def restore_rating(db: Session, rating_public_id: UUID) -> None:
    rating = db.scalar(select(GameRating).where(GameRating.public_id == rating_public_id))
    if rating is None:
        raise ApiError.not_found(ErrorCode.RATING_NOT_FOUND)
    rating.is_hidden = False
    rating.hidden_reason = None
    for report in db.scalars(
        select(ReviewReport).where(
            ReviewReport.rating_id == rating.id,
            ReviewReport.resolved.is_(False),
        )
    ).all():
        # Restore pełni też rolę odrzucenia bezzasadnego zgłoszenia, gdy
        # recenzja była przez cały czas widoczna.
        report.resolved = True
    db.flush()
    recalculate_game_rating(db, rating.game_id)
    db.commit()
