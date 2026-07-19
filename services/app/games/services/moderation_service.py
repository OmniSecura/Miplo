"""Operacje moderatorskie dla customowych gier i mediów społecznościowych."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.app.core.errors import ApiError, ErrorCode
from services.app.games.models import Game, GameBarcode, GameImage
from services.app.games.schemas import (
    GameDetail,
    PendingBarcodeModeration,
    PendingGameModeration,
    PendingImageModeration,
    PendingModelModeration,
)
from services.app.games.services import box_generator_service, cover_service, gallery_service
from services.app.users.models import User


def list_pending_games(db: Session, limit: int = 100) -> list[PendingGameModeration]:
    from services.app.games.services.game_service import to_detail

    games = db.scalars(
        select(Game)
        .where(Game.source == "custom", Game.is_verified.is_(False))
        .order_by(Game.created_at)
        .limit(limit)
    ).all()
    return [
        PendingGameModeration(
            game=to_detail(game),
            cover_preview_url=(
                cover_service.signed_preview_url(game.cover_candidate_path)
                if game.cover_candidate_path
                else None
            ),
        )
        for game in games
    ]


def approve_game(db: Session, slug: str) -> GameDetail:
    from services.app.games.services.game_service import get_game_by_slug, to_detail

    game = get_game_by_slug(db, slug)
    if game is None:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    if game.source != "custom":
        raise ApiError.forbidden(ErrorCode.CANNOT_EDIT_BGG_GAME)
    candidate_path = game.cover_candidate_path
    if candidate_path:
        game.cover_url = cover_service.publish_candidate(game.id, candidate_path)
        game.cover_candidate_path = None
    game.is_verified = True
    db.commit()
    cover_service.delete_path(candidate_path)
    db.refresh(game)
    return to_detail(game)


def reject_game(db: Session, slug: str) -> None:
    from services.app.games.services.game_service import get_game_by_slug

    game = get_game_by_slug(db, slug)
    if game is None:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    if game.source != "custom":
        raise ApiError.forbidden(ErrorCode.CANNOT_EDIT_BGG_GAME)
    game_id = game.id
    db.delete(game)
    db.commit()
    cover_service.delete_game_assets(game_id)


def list_pending_images(db: Session, limit: int = 100) -> list[PendingImageModeration]:
    images = db.scalars(
        select(GameImage)
        .where(GameImage.status == "pending", GameImage.is_verified.is_(False))
        .order_by(GameImage.created_at)
        .limit(limit)
    ).all()
    result: list[PendingImageModeration] = []
    for image in images:
        submitter = db.get(User, image.created_by_id) if image.created_by_id else None
        result.append(
            PendingImageModeration(
                public_id=image.public_id,
                game_slug=image.game.slug,
                game_title=image.game.title,
                caption=image.caption,
                preview_url=gallery_service.signed_preview_url(image.storage_path),
                submitted_by_tag=submitter.tag if submitter else None,
                created_at=image.created_at,
            )
        )
    return result


def approve_image(db: Session, public_id: UUID) -> None:
    image = db.scalar(select(GameImage).where(GameImage.public_id == public_id))
    if image is None:
        raise ApiError.not_found(ErrorCode.IMAGE_NOT_FOUND)
    if image.status != "pending" or image.is_verified:
        raise ApiError.conflict(ErrorCode.MEDIA_NOT_PENDING)
    image.image_url = gallery_service.make_public(image.storage_path)
    image.status = "approved"
    image.is_verified = True
    db.commit()


def reject_image(db: Session, public_id: UUID) -> None:
    image = db.scalar(select(GameImage).where(GameImage.public_id == public_id))
    if image is None:
        raise ApiError.not_found(ErrorCode.IMAGE_NOT_FOUND)
    path = image.storage_path
    db.delete(image)
    db.commit()
    gallery_service.delete(path)


def list_pending_barcodes(
    db: Session,
    limit: int = 100,
) -> list[PendingBarcodeModeration]:
    proposals = db.scalars(
        select(GameBarcode)
        .where(
            GameBarcode.status == "pending",
            GameBarcode.is_verified.is_(False),
        )
        .order_by(GameBarcode.created_at)
        .limit(limit)
    ).all()
    result: list[PendingBarcodeModeration] = []
    for proposal in proposals:
        submitter = db.get(User, proposal.created_by_id) if proposal.created_by_id else None
        approved = db.scalar(
            select(GameBarcode).where(
                GameBarcode.game_id == proposal.game_id,
                GameBarcode.language_code == proposal.language_code,
                GameBarcode.status == "approved",
                GameBarcode.is_verified.is_(True),
            )
        )
        result.append(
            PendingBarcodeModeration(
                public_id=proposal.public_id,
                game_slug=proposal.game.slug,
                game_title=proposal.game.title,
                barcode=proposal.barcode,
                language_code=proposal.language_code,
                replaces_barcode=approved.barcode if approved else None,
                submitted_by_tag=submitter.tag if submitter else None,
                created_at=proposal.created_at,
            )
        )
    return result


def approve_barcode(db: Session, public_id: UUID) -> None:
    proposal = db.scalar(
        select(GameBarcode).where(GameBarcode.public_id == public_id).with_for_update()
    )
    if proposal is None:
        raise ApiError.not_found(ErrorCode.BARCODE_PROPOSAL_NOT_FOUND)
    if proposal.status != "pending" or proposal.is_verified:
        raise ApiError.conflict(ErrorCode.BARCODE_NOT_PENDING)

    previous = db.scalar(
        select(GameBarcode)
        .where(
            GameBarcode.game_id == proposal.game_id,
            GameBarcode.language_code == proposal.language_code,
            GameBarcode.status == "approved",
            GameBarcode.id != proposal.id,
        )
        .with_for_update()
    )
    if previous is not None:
        db.delete(previous)
        db.flush()

    proposal.status = "approved"
    proposal.is_verified = True
    proposal.approved_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError.conflict(ErrorCode.BARCODE_NOT_PENDING)


def reject_barcode(db: Session, public_id: UUID) -> None:
    proposal = db.scalar(
        select(GameBarcode).where(GameBarcode.public_id == public_id).with_for_update()
    )
    if proposal is None:
        raise ApiError.not_found(ErrorCode.BARCODE_PROPOSAL_NOT_FOUND)
    if proposal.status != "pending" or proposal.is_verified:
        raise ApiError.conflict(ErrorCode.BARCODE_NOT_PENDING)
    db.delete(proposal)
    db.commit()


def list_pending_models(db: Session, limit: int = 100) -> list[PendingModelModeration]:
    games = db.scalars(
        select(Game)
        .where(
            Game.model_status == "awaiting_review",
            Game.model_candidate_path.is_not(None),
        )
        .order_by(Game.model_submitted_at)
        .limit(limit)
    ).all()
    result: list[PendingModelModeration] = []
    for game in games:
        submitter = db.get(User, game.model_submitted_by_id) if game.model_submitted_by_id else None
        candidate_path = game.model_candidate_path
        if candidate_path is None:  # query excludes it; guard keeps storage call explicit
            continue
        result.append(
            PendingModelModeration(
                game_slug=game.slug,
                game_title=game.title,
                model_status=game.model_status or "awaiting_review",
                preview_url=box_generator_service.signed_preview_url(candidate_path),
                submitted_by_tag=submitter.tag if submitter else None,
                submitted_at=game.model_submitted_at,
            )
        )
    return result


def approve_model(db: Session, slug: str) -> GameDetail:
    from services.app.games.services.game_service import get_game_by_slug, to_detail

    game = get_game_by_slug(db, slug)
    if game is None:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    if game.model_status != "awaiting_review" or not game.model_candidate_path:
        raise ApiError.conflict(ErrorCode.MODEL_NOT_READY_FOR_REVIEW)

    candidate_path = game.model_candidate_path
    game.model_3d_url = box_generator_service.publish_candidate(game.id, candidate_path)
    game.model_status = "ready"
    game.model_is_verified = True
    game.model_candidate_path = None
    game.model_job_id = None
    game.model_submitted_by_id = None
    game.model_submitted_at = None
    db.commit()
    box_generator_service.delete_path(candidate_path)
    db.refresh(game)
    return to_detail(game)


def reject_model(db: Session, slug: str) -> None:
    from services.app.games.services.game_service import get_game_by_slug

    game = get_game_by_slug(db, slug)
    if game is None:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    if game.model_status not in {"awaiting_review", "failed"}:
        raise ApiError.conflict(ErrorCode.MODEL_NOT_READY_FOR_REVIEW)
    candidate_path = game.model_candidate_path
    game.model_status = "ready" if game.model_3d_url else None
    game.model_candidate_path = None
    game.model_job_id = None
    game.model_submitted_by_id = None
    game.model_submitted_at = None
    game.model_is_verified = game.model_3d_url is not None
    db.commit()
    box_generator_service.delete_path(candidate_path)


def set_contributions_enabled(db: Session, slug: str, enabled: bool) -> GameDetail:
    from services.app.games.services.game_service import get_game_by_slug, to_detail

    game = get_game_by_slug(db, slug)
    if game is None:
        raise ApiError.not_found(ErrorCode.GAME_NOT_FOUND)
    game.community_contributions_enabled = enabled
    db.commit()
    db.refresh(game)
    return to_detail(game)
