from platform_codegen.runtime.operations import observed
import asyncio
import io
from pathlib import PurePosixPath
import secrets
import time
import uuid

from PIL import Image, UnidentifiedImageError

from generated.clients.llm.create_image_job import Request as CreateImageJobRequest
from platform_codegen.runtime.clients import ServiceCallError

from game.catalog import LEGACY_ROOM, ROOM_ALPHABET, MIN_PLAYERS
from catalog_repository import CatalogRepository
from game.room import GameRoom
from game.errors import GameError
from persistence import RoomRepository


class GameService:
    def __init__(self, runtime):
        self.runtime = runtime
        self.repository = None
        self.catalog = None
        self.storage = runtime.s3
        self.llm = runtime.clients["llm"]
        self.settings = runtime.settings

    async def start(self):
        self.catalog = await CatalogRepository(self.runtime.database).load()
        self.repository = RoomRepository(self.runtime.database, self.catalog)
        self.runtime.task(self.collect_statistics(), name="business-statistics")
        await self.repository.ensure_legacy()
        self.runtime.task(self.tick(), name="game-timers")
        for index in range(self.settings.outbox_concurrency):
            self.runtime.task(self.image_worker(), name="image-outbox-" + str(index))

    @observed("backend.create")
    async def create(self, body):
        name = body.name.strip()
        if not name:
            raise GameError(400, "Придумай название комнаты.")
        if body.mode not in [*self.catalog.mode_info, "mix"]:
            raise GameError(400, "Неизвестная игра")
        for attempt in range(10):
            code = "".join(secrets.choice(ROOM_ALPHABET) for _ in range(6))
            game = GameRoom(code, name, catalog=self.catalog)
            game.state.update(mode=body.mode, count=body.count, capacity=body.capacity)
            if await self.repository.create(game):
                return game.summary()
        raise GameError(503, "Не удалось создать комнату. Попробуй снова.")

    @staticmethod
    def normalize(code):
        value = (code or LEGACY_ROOM).strip().upper()
        if (
            len(value) != 6
            or any(char not in ROOM_ALPHABET for char in value)
            and value != LEGACY_ROOM
        ):
            raise GameError(404, "Комната не найдена. Проверь код.")
        return value

    def meta(self):
        return {
            "legacy_room": LEGACY_ROOM,
            "modes": self.catalog.mode_info,
            "powers": self.catalog.powers,
            "lan_ip": self.settings.lan_ip,
            "min_players": MIN_PLAYERS,
            "answer_fields": {
                name: mode["fields"]
                for name, mode in self.catalog.modes.items()
                if "fields" in mode
            },
            "image_modes": [
                name
                for name, mode in self.catalog.modes.items()
                if mode["kind"] in ("image", "relay", "shared")
            ],
            "image_model": self.settings.polza_image_model,
            "image_provider": self.settings.image_provider,
        }

    @observed("backend.mutate")
    async def mutate(self, code, action, token, body=None):
        async with self.repository.locked(self.normalize(code)) as (game, session):
            if action == "join":
                return game.join(body.name)
            if action == "leave":
                game.leave(token)
            elif action == "settings":
                game.configure(token, body.model_dump(), body.model_fields_set)
            elif action == "bots":
                game.add_bots(token)
            elif action == "start":
                game.start(token)
            elif action == "next":
                game.next(token, body.round_id, body.force)
            elif action == "lobby":
                game.lobby(token)
            elif action == "remove":
                game.remove_player(token, body)
            elif action == "answer":
                valid = False
                if body.image:
                    filename = PurePosixPath(body.image).name
                    image = game.image_url(filename)
                    valid = body.image in (image, image.removeprefix("/api")) and bool(
                        await self.repository.artifact(game.code, filename, session)
                    )
                game.answer(token, body.model_dump(), image_allowed=valid)
            elif action == "vote":
                game.vote(token, body.model_dump())
            elif action == "generate":
                game.generate(token, body.model_dump())
                return {"accepted": True}
            return {"ok": True}

    @observed("backend.state")
    async def state(self, code, token):
        async with self.repository.locked(self.normalize(code)) as (game, session):
            game.progress()
            return game.view(token)

    @observed("backend.summary")
    async def summary(self, code):
        async with self.repository.locked(self.normalize(code)) as (game, session):
            return game.summary()

    @observed("backend.upload")
    async def upload(self, code, token, body):
        code = self.normalize(code)
        if len(body) > self.settings.max_upload_bytes:
            raise GameError(400, "Максимальный размер — 10 МБ")
        async with self.repository.locked(code) as (game, session):
            game.player(token)
        try:
            with Image.open(io.BytesIO(body)) as image:
                if (
                    image.format not in ("PNG", "JPEG", "WEBP")
                    or image.width * image.height > self.settings.max_image_pixels
                ):
                    raise GameError(400, "Нужен PNG, JPG или WebP до 25 мегапикселей")
                extension = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[
                    image.format
                ]
                content_type = {
                    "PNG": "image/png",
                    "JPEG": "image/jpeg",
                    "WEBP": "image/webp",
                }[image.format]
                image.verify()
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
        ):
            raise GameError(400, "Не удалось прочитать изображение") from None
        filename = uuid.uuid4().hex + extension
        key = f"uploads/{code}/{filename}"
        await self.storage.put(key, body, content_type)
        async with self.repository.locked(code) as (game, session):
            game.player(token)
            await self.repository.store_artifact(
                session, code, filename, key, content_type, len(body)
            )
            return {"url": game.image_url(filename)}

    @observed("backend.download")
    async def download(self, path):
        parts = PurePosixPath(path).parts
        if len(parts) == 1:
            code, filename = LEGACY_ROOM, parts[0]
        elif len(parts) == 2:
            code, filename = parts
        else:
            raise GameError(404, "Картинка не найдена")
        artifact = await self.repository.artifact(self.normalize(code), filename)
        if not artifact:
            raise GameError(404, "Картинка не найдена")
        return await self.storage.get(
            artifact["object_key"], max_bytes=self.settings.max_upload_bytes
        )

    async def tick(self):
        while True:
            await asyncio.sleep(1)
            try:
                await self.advance_timers()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.runtime.logger.error("Game timer iteration failed; retrying")

    async def image_worker(self):
        while True:
            request = None
            try:
                request = await self.repository.claim_image()
                if not request:
                    await asyncio.sleep(0.3)
                    continue
                await self.process_image(request)
            except asyncio.CancelledError:
                raise
            except ServiceCallError as error:
                if request and error.status in (400, 403, 404, 409, 422):
                    await self.repository.reject_image(
                        request,
                        "Не удалось выполнить запрос генерации. Попробуй еще раз.",
                    )
                elif request:
                    await self.repository.update_request(
                        request,
                        attempts=request["attempts"] + 1,
                        next_attempt=time.time() + 3,
                    )
                await asyncio.sleep(1)
            except Exception:
                if request:
                    try:
                        await self.repository.update_request(
                            request,
                            attempts=request["attempts"] + 1,
                            next_attempt=time.time()
                            + min(30, 2 ** min(request["attempts"], 5)),
                        )
                    except Exception:
                        pass
                self.runtime.logger.warning(
                    "Image service unavailable; durable request will be retried"
                )
                await asyncio.sleep(1)

    @observed("image.outbox.process", parent="request")
    async def process_image(self, request):
        if not request["remote_id"]:
            response = await self.llm.create_image_job(
                body=CreateImageJobRequest(prompt=request["prompt"]),
                idempotency_key=request["room_code"]
                + ":"
                + request["round_id"]
                + ":"
                + request["id"],
            )
        else:
            response = await self.llm.get_image_job(
                job_id=uuid.UUID(request["remote_id"])
            )
        if response.status in ("succeeded", "failed", "needs_reconciliation"):
            await self.repository.finish_image(request, response)
        else:
            await self.repository.update_request(
                request, remote_id=str(response.id), next_attempt=time.time() + 1
            )

    async def collect_statistics(self):
        while True:
            try:
                phases, pending = await self.repository.statistics()
                for phase in ("lobby", "briefing", "answer", "vote", "reveal", "final"):
                    self.runtime.telemetry.gauge(
                        "game.rooms", phases.get(phase, 0), {"phase": phase}
                    )
                self.runtime.telemetry.gauge("image.outbox.pending", pending)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.runtime.logger.warning("Business statistics refresh failed")
            await asyncio.sleep(10)

    @observed("game.timers.tick")
    async def advance_timers(self):
        for code in await self.repository.codes():
            async with self.repository.locked(code) as (game, session):
                game.bot_step()
                game.progress()
