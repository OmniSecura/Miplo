"""Testy krytycznej logiki modułu games bez sieci i Firebase."""

import asyncio
import inspect
import io
import json
import os
import struct
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from xml.etree import ElementTree as ET

os.environ["ENV"] = "local"
os.environ["SQLITE_PATH"] = os.path.join(tempfile.gettempdir(), "miplo-games-tests.db")
os.environ.setdefault("FIREBASE_ADMIN_CREDENTIALS", "unused-in-unit-tests.json")
os.environ.setdefault("FIREBASE_STORAGE_BUCKET", "unused-in-unit-tests")
os.environ["GAMES_IMPORT_KEY"] = "unit-test-import-key-long-enough"
os.environ["ADMIN_API_KEY"] = "unit-test-admin-key-long-enough-123"

from fastapi import UploadFile
import httpx
from PIL import Image
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from starlette.requests import Request

from services.app.core import bgg_client
from services.app.core.auth import get_admin_access, get_current_admin
from services.app.core.database import Base, SessionLocal, engine
from services.app.core.errors import ApiError, ErrorCode
from services.app.games.models import Game, GameBarcode, GameImage
from services.app.games.enums import GameLanguage
from services.app.games.routers.router import submit_3d_model
from services.app.games.schemas import BarcodeAssign, GalleryImageCreate, GameCreate, GameUpdate
from services.app.games.services import (
    box_generator_service,
    catalog_import_service,
    cover_service,
    game_service,
    moderation_service,
)
from services.app.users.models import User


class GamesServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Base.metadata.create_all(engine)

    @classmethod
    def tearDownClass(cls) -> None:
        engine.dispose()
        try:
            os.unlink(os.environ["SQLITE_PATH"])
        except FileNotFoundError:
            pass

    def setUp(self) -> None:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        self.db = SessionLocal()
        self.user = User(firebase_uid="uid-owner", tag="owner", is_active=True)
        self.other = User(firebase_uid="uid-other", tag="other", is_active=True)
        self.db.add_all([self.user, self.other])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.other)

    def tearDown(self) -> None:
        self.db.close()

    def _create_custom(self):
        payload = GameCreate(
            title="Brass: Birmingham",
            description="<b>Ekonomiczna</b> gra planszowa",
            min_players=2,
            max_players=4,
            playing_time=120,
            game_types='["Euro", "Ekonomiczna"]',
        )
        return asyncio.run(game_service.create_custom_game(self.db, payload, None, self.user))

    @staticmethod
    def _image_bytes(color=(30, 60, 90)) -> bytes:
        output = io.BytesIO()
        Image.new("RGB", (320, 240), color).save(output, "PNG")
        return output.getvalue()

    def test_custom_game_slug_types_and_plain_text(self) -> None:
        game = self._create_custom()
        self.assertEqual(game.slug, "brass-birmingham")
        self.assertEqual(game.description, "Ekonomiczna gra planszowa")
        self.assertEqual({item.name for item in game.game_types}, {"Euro", "Ekonomiczna"})
        self.assertFalse(game.is_verified)
        self.assertEqual(game.created_by_id, self.user.id)
        self.assertEqual(game_service.get_game_by_slug(self.db, "Brass Birmingham"), game)

    def test_only_owner_can_update_custom_game(self) -> None:
        game = self._create_custom()
        with self.assertRaises(ApiError) as context:
            asyncio.run(
                game_service.update_custom_game(
                    self.db,
                    game.slug,
                    GameUpdate(title="Inny tytuł"),
                    None,
                    self.other,
                )
            )
        self.assertEqual(context.exception.detail["error_code"], ErrorCode.NOT_GAME_OWNER.value)

    def test_unverified_custom_is_hidden_until_admin_approval(self) -> None:
        game = self._create_custom()
        self.assertEqual(game_service.list_games(self.db, 1, 20).total, 0)
        moderation_service.approve_game(self.db, game.slug)
        self.assertEqual(game_service.list_games(self.db, 1, 20).total, 1)

    def test_admin_can_lock_and_unlock_all_contributions(self) -> None:
        game = self._create_custom()
        moderation_service.set_contributions_enabled(self.db, game.slug, False)
        with self.assertRaises(ApiError) as context:
            asyncio.run(
                game_service.update_custom_game(
                    self.db,
                    game.slug,
                    GameUpdate(title="Nowy tytuł"),
                    None,
                    self.user,
                )
            )
        self.assertEqual(
            context.exception.detail["error_code"],
            ErrorCode.CONTRIBUTIONS_LOCKED.value,
        )
        moderation_service.set_contributions_enabled(self.db, game.slug, True)
        updated = asyncio.run(
            game_service.update_custom_game(
                self.db,
                game.slug,
                GameUpdate(title="Nowy tytuł"),
                None,
                self.user,
            )
        )
        self.assertEqual(updated.slug, "nowy-tytul")

    def test_gallery_is_private_until_moderator_approval(self) -> None:
        game = self._create_custom()
        upload = UploadFile(
            file=io.BytesIO(self._image_bytes()),
            filename="inside.png",
            headers={"content-type": "image/png"},
        )
        with patch(
            "services.app.games.services.gallery_service.upload_private",
            new=AsyncMock(),
        ):
            submission = asyncio.run(
                game_service.submit_gallery_image(
                    self.db,
                    game.slug,
                    GalleryImageCreate(caption="Wnętrze pudełka"),
                    upload,
                    self.user,
                )
            )
        self.assertEqual(submission.status, "pending")
        self.assertEqual(game_service.to_detail(game).images, [])

        with patch(
            "services.app.games.services.gallery_service.make_public",
            return_value="https://storage.example/inside.webp",
        ):
            moderation_service.approve_image(self.db, submission.public_id)
        self.db.refresh(game)
        images = game_service.to_detail(game).images
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].image_url, "https://storage.example/inside.webp")

    def test_local_admin_flag_is_required(self) -> None:
        with self.assertRaises(ApiError) as context:
            get_current_admin(self.user)
        self.assertEqual(context.exception.detail["error_code"], ErrorCode.ADMIN_REQUIRED.value)
        self.user.is_admin = True
        self.assertIs(get_current_admin(self.user), self.user)

    def test_admin_api_key_uses_constant_secret_and_never_falls_back(self) -> None:
        request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
        result = get_admin_access(
            request,
            api_key="unit-test-admin-key-long-enough-123",
            bearer=None,
            db=self.db,
        )
        self.assertIsNone(result)
        self.assertEqual(request.state.firebase_uid, "admin-api-key")

        with self.assertRaises(ApiError) as context:
            get_admin_access(
                request,
                api_key="wrong-key-that-is-still-long-enough-123",
                bearer=None,
                db=self.db,
            )
        self.assertEqual(
            context.exception.detail["error_code"],
            ErrorCode.INVALID_ADMIN_API_KEY.value,
        )
        self.assertEqual(context.exception.status_code, 401)

    def test_catalog_csv_import_is_idempotent_and_excludes_expansions(self) -> None:
        csv_data = (
            "id,name,yearpublished,rank,average,usersrated,is_expansion\n"
            "224517,Brass Birmingham,2018,1,8.61,50000,0\n"
            "999999,Brass Expansion,2020,100,7.00,200,1\n"
        ).encode()
        upload = UploadFile(file=io.BytesIO(csv_data), filename="bgg.csv")
        first = catalog_import_service.import_catalog(self.db, upload)
        self.assertEqual((first.created, first.updated, first.skipped), (2, 0, 0))

        upload_again = UploadFile(file=io.BytesIO(csv_data), filename="bgg.csv")
        second = catalog_import_service.import_catalog(self.db, upload_again)
        self.assertEqual((second.created, second.updated), (0, 2))
        self.assertEqual(self.db.query(Game).count(), 2)

        catalog = game_service.list_games(self.db, page=1, size=20)
        self.assertEqual(catalog.total, 1)
        catalog_with_expansions = game_service.list_games(
            self.db,
            page=1,
            size=20,
            include_expansions=True,
        )
        self.assertEqual(catalog_with_expansions.total, 2)

    def test_empty_catalog_has_zero_pages(self) -> None:
        catalog = game_service.list_games(self.db, page=1, size=20)
        self.assertEqual((catalog.total, catalog.pages, catalog.items), (0, 0, []))

    def test_title_and_instruction_url_reject_ambiguous_input(self) -> None:
        common = {
            "min_players": 1,
            "max_players": 2,
            "game_types": '["Familijna"]',
        }
        with self.assertRaises(ValidationError):
            GameCreate(title="Gra\nPodmieniona", **common)
        with self.assertRaises(ValidationError):
            GameCreate(
                title="Poprawna gra",
                instruction_url="https://user:secret@example.com/manual.pdf",
                **common,
            )

    def test_barcode_checksum_is_enforced(self) -> None:
        self.assertTrue(game_service._is_valid_barcode("5901549927658"))
        self.assertFalse(game_service._is_valid_barcode("5901549927659"))
        self.assertFalse(game_service._is_valid_barcode("１２３４５６７８"))

    def test_barcode_language_is_normalized_and_strict(self) -> None:
        payload = BarcodeAssign(barcode="5901549927658", language_code="PL")
        self.assertIs(payload.language_code, GameLanguage.POLISH)
        for invalid_length in ("123456789", "1234567890", "12345678901"):
            with self.assertRaises(ValidationError):
                BarcodeAssign(barcode=invalid_length, language_code="pl")
        with self.assertRaises(ValidationError):
            BarcodeAssign(barcode="5901549927658", language_code="de")
        with self.assertRaises(ValidationError):
            BarcodeAssign(barcode="5901549927658", language_code="polski")
        with self.assertRaises(ValidationError):
            BarcodeAssign(barcode="5901549927658", language_code=123)

    def test_barcode_is_private_until_admin_approval(self) -> None:
        game = self._create_custom()
        moderation_service.approve_game(self.db, game.slug)
        submission = game_service.propose_barcode(
            self.db,
            game.slug,
            "5901549927658",
            "pl",
            self.other,
        )
        self.assertEqual(submission.status, "pending")
        self.assertIsNone(game_service.get_game_by_barcode(self.db, submission.barcode))
        self.assertEqual(len(moderation_service.list_pending_barcodes(self.db)), 1)

        moderation_service.approve_barcode(self.db, submission.public_id)
        self.assertEqual(game_service.get_game_by_barcode(self.db, submission.barcode).id, game.id)
        self.db.refresh(game)
        detail = game_service.to_detail(game)
        self.assertEqual(
            [(item.language_code, item.barcode) for item in detail.barcodes],
            [("pl", "5901549927658")],
        )

    def test_game_can_have_one_approved_barcode_per_language(self) -> None:
        game = self._create_custom()
        moderation_service.approve_game(self.db, game.slug)
        for barcode, language in (
            ("5901549927658", "pl"),
            ("4006381333931", "en"),
        ):
            submission = game_service.propose_barcode(
                self.db, game.slug, barcode, language, self.other
            )
            moderation_service.approve_barcode(self.db, submission.public_id)

        approved = self.db.scalars(
            select(GameBarcode).where(
                GameBarcode.game_id == game.id,
                GameBarcode.status == "approved",
            )
        ).all()
        self.assertEqual({item.language_code for item in approved}, {"pl", "en"})

    def test_approved_barcode_can_only_be_replaced_through_moderation(self) -> None:
        game = self._create_custom()
        moderation_service.approve_game(self.db, game.slug)
        first = game_service.propose_barcode(
            self.db, game.slug, "5901549927658", "pl", self.other
        )
        moderation_service.approve_barcode(self.db, first.public_id)

        replacement = game_service.propose_barcode(
            self.db, game.slug, "4006381333931", "pl", self.other
        )
        pending = moderation_service.list_pending_barcodes(self.db)
        self.assertEqual(pending[0].replaces_barcode, "5901549927658")
        self.assertEqual(
            game_service.get_game_by_barcode(self.db, "5901549927658").id,
            game.id,
        )

        moderation_service.approve_barcode(self.db, replacement.public_id)
        self.assertIsNone(game_service.get_game_by_barcode(self.db, "5901549927658"))
        self.assertEqual(
            game_service.get_game_by_barcode(self.db, "4006381333931").id,
            game.id,
        )

    def test_contribution_lock_blocks_barcode_proposals(self) -> None:
        game = self._create_custom()
        moderation_service.approve_game(self.db, game.slug)
        moderation_service.set_contributions_enabled(self.db, game.slug, False)
        with self.assertRaises(ApiError) as context:
            game_service.propose_barcode(
                self.db, game.slug, "5901549927658", "pl", self.other
            )
        self.assertEqual(
            context.exception.detail["error_code"],
            ErrorCode.CONTRIBUTIONS_LOCKED.value,
        )

    def test_delete_custom_game_cleans_assets_and_record(self) -> None:
        game = self._create_custom()
        with patch(
            "services.app.games.services.cover_service.delete_game_assets"
        ) as delete_assets:
            game_service.delete_custom_game(self.db, game.slug, self.user)
        delete_assets.assert_called_once_with(game.id)
        self.assertIsNone(self.db.get(Game, game.id))

    def test_cover_is_reencoded_and_limited(self) -> None:
        source = io.BytesIO()
        Image.new("RGBA", (1600, 900), (10, 20, 30, 128)).save(source, "PNG")
        upload = UploadFile(
            file=io.BytesIO(source.getvalue()),
            filename="cover.png",
            headers={"content-type": "image/png"},
        )
        optimized = asyncio.run(cover_service.prepare_cover(upload))
        image = Image.open(io.BytesIO(optimized))
        self.assertEqual(image.format, "WEBP")
        self.assertLessEqual(max(image.size), 800)
        self.assertEqual(image.mode, "RGB")

    def test_invalid_cover_is_rejected(self) -> None:
        upload = UploadFile(
            file=io.BytesIO(b"not-an-image"),
            filename="cover.png",
            headers={"content-type": "image/png"},
        )
        with self.assertRaises(ApiError) as context:
            asyncio.run(cover_service.prepare_cover(upload))
        self.assertEqual(
            context.exception.detail["error_code"],
            ErrorCode.INVALID_FILE_TYPE.value,
        )

    def test_glb_contains_two_parts_and_six_embedded_textures(self) -> None:
        raw_sides = {
            name: self._image_bytes((index * 30, 80, 120))
            for index, name in enumerate(box_generator_service.SIDE_NAMES, start=1)
        }
        glb = box_generator_service.build_glb(raw_sides, (29.8, 29.8, 7.4))
        magic, version, total_length = struct.unpack("<4sII", glb[:12])
        self.assertEqual((magic, version, total_length), (b"glTF", 2, len(glb)))
        json_length, chunk_type = struct.unpack("<I4s", glb[12:20])
        self.assertEqual(chunk_type, b"JSON")
        document = json.loads(glb[20 : 20 + json_length].decode().rstrip())
        self.assertEqual([node["name"] for node in document["nodes"]], ["BoxBase", "BoxLid"])
        self.assertEqual(len(document["images"]), 6)
        self.assertEqual(len(document["materials"]), 7)
        self.assertEqual(document["materials"][-1]["name"], "cardboard_black")
        self.assertEqual(sum(len(mesh["primitives"]) for mesh in document["meshes"]), 14)
        self.assertTrue(all(image["mimeType"] == "image/jpeg" for image in document["images"]))
        self.assertEqual(document["extras"]["axisConvention"], "X=width,Y=height,Z=depth")

        # Duże obrazy muszą trafić na wieko i spód, nie na pionowe boki.
        self.assertEqual(document["materials"][document["meshes"][1]["primitives"][-1]["material"]]["name"], "front")
        self.assertEqual(document["materials"][document["meshes"][0]["primitives"][4]["material"]]["name"], "back")

        binary_header = 20 + json_length
        binary_length, binary_type = struct.unpack("<I4s", glb[binary_header : binary_header + 8])
        self.assertEqual(binary_type, b"BIN\x00")
        binary = glb[binary_header + 8 : binary_header + 8 + binary_length]

        def positions(primitive: dict) -> list[tuple[float, float, float]]:
            accessor = document["accessors"][primitive["attributes"]["POSITION"]]
            view = document["bufferViews"][accessor["bufferView"]]
            values = struct.unpack_from(
                f"<{accessor['count'] * 3}f",
                binary,
                view.get("byteOffset", 0),
            )
            return [tuple(values[index : index + 3]) for index in range(0, len(values), 3)]

        lid_cover = positions(document["meshes"][1]["primitives"][-1])
        base_back = positions(document["meshes"][0]["primitives"][4])
        # box_depth=7.4 cm steruje osią Z. Stary błąd używał tu 29.8 cm.
        self.assertAlmostEqual(max(point[2] for point in lid_cover), 0.039, places=5)
        self.assertAlmostEqual(min(point[2] for point in base_back), -0.037, places=5)
        self.assertAlmostEqual(
            max(point[2] for point in lid_cover) - min(point[2] for point in base_back),
            0.076,
            places=5,
        )

        seam_materials = [
            primitive["material"]
            for primitive in document["meshes"][1]["primitives"][4:8]
        ]
        self.assertEqual(seam_materials, [6, 6, 6, 6])

    def test_side_texture_is_rotated_to_match_physical_edge(self) -> None:
        landscape = io.BytesIO()
        Image.new("RGB", (800, 200), (40, 80, 120)).save(landscape, "PNG")
        optimized = box_generator_service._texture_jpeg(
            landscape.getvalue(),
            physical_width=7.4,
            physical_height=29.8,
        )
        image = Image.open(io.BytesIO(optimized))
        self.assertGreater(image.height, image.width)

    def test_explicit_side_rotation_corrects_upside_down_photo(self) -> None:
        source = Image.new("RGB", (100, 100), (0, 0, 255))
        for y in range(50):
            for x in range(100):
                source.putpixel((x, y), (255, 0, 0))
        raw = io.BytesIO()
        source.save(raw, "PNG")

        optimized = box_generator_service._texture_jpeg(
            raw.getvalue(),
            physical_width=10,
            physical_height=10,
            rotation_clockwise=180,
        )
        image = Image.open(io.BytesIO(optimized))
        top_pixel = image.getpixel((image.width // 2, image.height // 4))
        bottom_pixel = image.getpixel((image.width // 2, image.height * 3 // 4))
        self.assertGreater(top_pixel[2], top_pixel[0])
        self.assertGreater(bottom_pixel[0], bottom_pixel[2])

    def test_multipart_text_zero_is_valid_rotation(self) -> None:
        annotation = inspect.signature(submit_3d_model).parameters[
            "rotation_front"
        ].annotation
        self.assertEqual(TypeAdapter(annotation).validate_python("0"), "0")
        with self.assertRaises(ValidationError):
            TypeAdapter(annotation).validate_python("45")

    def test_verified_game_accepts_community_gallery_proposal(self) -> None:
        game = self._create_custom()
        moderation_service.approve_game(self.db, game.slug)
        upload = UploadFile(
            file=io.BytesIO(self._image_bytes()),
            filename="community.png",
            headers={"content-type": "image/png"},
        )
        with patch(
            "services.app.games.services.gallery_service.upload_private",
            new=AsyncMock(),
        ):
            submission = asyncio.run(
                game_service.submit_gallery_image(
                    self.db,
                    game.slug,
                    GalleryImageCreate(caption="Propozycja społeczności"),
                    upload,
                    self.other,
                )
            )
        image = self.db.scalar(
            select(GameImage).where(GameImage.public_id == submission.public_id)
        )
        self.assertEqual(image.created_by_id, self.other.id)
        self.assertFalse(image.is_verified)

    def test_replacement_proposer_cannot_remove_approved_model(self) -> None:
        game = self._create_custom()
        moderation_service.approve_game(self.db, game.slug)
        game.model_3d_url = "https://storage.example/approved.glb"
        game.model_status = "ready"
        game.model_is_verified = True
        self.db.commit()

        game, _ = game_service.begin_model_submission(self.db, game.slug, self.other)
        with patch(
            "services.app.games.services.box_generator_service.delete_path"
        ) as delete_path:
            game_service.delete_model_submission(self.db, game.slug, self.other)
        self.db.refresh(game)
        self.assertEqual(game.model_3d_url, "https://storage.example/approved.glb")
        self.assertEqual(game.model_status, "ready")
        self.assertTrue(game.model_is_verified)
        delete_path.assert_called_once_with(None)

    def test_all_six_model_sides_are_required(self) -> None:
        files = {
            name: UploadFile(
                file=io.BytesIO(self._image_bytes()),
                filename=f"{name}.png",
                headers={"content-type": "image/png"},
            )
            for name in box_generator_service.SIDE_NAMES
            if name != "bottom"
        }
        with self.assertRaises(ApiError) as context:
            asyncio.run(box_generator_service.read_validated_sides(files))
        self.assertEqual(
            context.exception.detail["error_code"],
            ErrorCode.ALL_SIDES_REQUIRED.value,
        )

    def test_model_candidate_requires_admin_approval(self) -> None:
        game = self._create_custom()
        game, _ = game_service.begin_model_submission(self.db, game.slug, self.user)
        game.model_status = "awaiting_review"
        game.model_candidate_path = "games/1/models/submissions/job.glb"
        self.db.commit()
        with (
            patch(
                "services.app.games.services.box_generator_service.publish_candidate",
                return_value="https://storage.example/box_model.glb?v=1",
            ),
            patch("services.app.games.services.box_generator_service.delete_path"),
        ):
            detail = moderation_service.approve_model(self.db, game.slug)
        self.assertEqual(detail.model_status, "ready")
        self.assertEqual(detail.model_3d_url, "https://storage.example/box_model.glb?v=1")

    def test_bgg_202_is_retried_before_xml_is_parsed(self) -> None:
        client = AsyncMock()
        client.get.side_effect = [
            httpx.Response(202, content=b"queued"),
            httpx.Response(200, content=b"<items />"),
        ]
        with patch("services.app.core.bgg_client.asyncio.sleep", new=AsyncMock()) as sleep:
            root = asyncio.run(bgg_client._get_xml(client, "thing", {"id": "1"}))
        self.assertEqual(root.tag, "items")
        self.assertEqual(client.get.await_count, 2)
        sleep.assert_awaited_once_with(2.0)

    def test_bgg_game_xml_parsing(self) -> None:
        xml = ET.fromstring(
            """
            <items><item id="224517">
              <name type="primary" value="Brass: Birmingham"/>
              <yearpublished value="2018"/><minplayers value="2"/>
              <maxplayers value="4"/><playingtime value="120"/>
              <description>Economic &amp;lt;b&amp;gt;game&amp;lt;/b&amp;gt;</description>
              <image>https://cf.geekdo-images.com/cover.jpg</image>
              <statistics><ratings><average value="8.60"/>
                <averageweight value="3.90"/></ratings></statistics>
              <link type="boardgamecategory" value="Economic"/>
            </item></items>
            """
        )
        with (
            patch("services.app.core.bgg_client._require_token"),
            patch(
                "services.app.core.bgg_client._get_xml",
                new=AsyncMock(return_value=xml),
            ),
        ):
            game = asyncio.run(bgg_client.fetch_game(224517))
        self.assertEqual(game.title, "Brass: Birmingham")
        self.assertEqual(game.description, "Economic game")
        self.assertEqual(game.categories, ["Economic"])


if __name__ == "__main__":
    unittest.main()
