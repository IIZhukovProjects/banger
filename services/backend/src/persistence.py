from platform_codegen.runtime.operations import capture_context, observed
from contextlib import asynccontextmanager
import time
import uuid

from sqlalchemy import (
    func,
    Column,
    Float,
    ForeignKey,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from game.room import GameRoom
from game.catalog import LEGACY_ROOM
from game.errors import GameError


metadata = MetaData()
json_type = JSON().with_variant(JSONB, "postgresql")
rooms = Table(
    "rooms",
    metadata,
    Column("code", String(6), primary_key=True),
    Column("name", String(40), nullable=False),
    Column("state", json_type, nullable=False),
    Column("created_at", Float, nullable=False),
)
image_requests = Table(
    "image_requests",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("room_code", ForeignKey("rooms.code"), nullable=False),
    Column("round_id", String(32), nullable=False),
    Column("owner", String(32), nullable=False),
    Column("prompt", Text, nullable=False),
    Column("remote_id", String(36)),
    Column("status", String(20), nullable=False, default="pending"),
    Column("attempts", Integer, nullable=False, default=0),
    Column("next_attempt", Float, nullable=False, default=0),
    Column("lease_until", Float, nullable=False, default=0),
    Column("lease_token", String(32)),
    Column("trace_context", json_type, nullable=False, server_default="{}"),
)
artifacts = Table(
    "artifacts",
    metadata,
    Column("room_code", ForeignKey("rooms.code"), primary_key=True),
    Column("filename", String(80), primary_key=True),
    Column("object_key", String(512), nullable=False),
    Column("content_type", String(80), nullable=False),
    Column("size", Integer, nullable=False),
)


class RoomRepository:
    def __init__(self, database, catalog):
        self.catalog = catalog
        self.database = database
        self.telemetry = getattr(database, "telemetry", None)

    async def ensure_legacy(self):
        async with self.database.transaction() as session:
            game = GameRoom(LEGACY_ROOM, "Общая комната", catalog=self.catalog)
            await session.execute(
                postgres_insert(rooms)
                .values(
                    code=game.code,
                    name=game.name,
                    state=game.state,
                    created_at=game.created_at,
                )
                .on_conflict_do_nothing()
            )

    @observed("backend.repository.list")
    async def list(self):
        async with self.database.transaction() as session:
            result = await session.execute(
                select(rooms).order_by(rooms.c.created_at.desc())
            )
            return [self.aggregate(row).summary() for row in result.mappings()]

    async def codes(self):
        async with self.database.transaction() as session:
            return list((await session.execute(select(rooms.c.code))).scalars())

    def aggregate(self, row):
        return GameRoom(
            row["code"],
            row["name"],
            row["state"],
            row["created_at"],
            catalog=self.catalog,
        )

    @observed("backend.repository.create")
    async def create(self, game):
        async with self.database.transaction() as session:
            result = await session.execute(
                postgres_insert(rooms)
                .values(
                    code=game.code,
                    name=game.name,
                    state=game.state,
                    created_at=game.created_at,
                )
                .on_conflict_do_nothing()
                .returning(rooms.c.code)
            )
            return result.scalar_one_or_none() is not None

    @asynccontextmanager
    async def locked(self, code):
        async with self.database.transaction() as session:
            row = (
                (
                    await session.execute(
                        select(rooms).where(rooms.c.code == code).with_for_update()
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise GameError(404, "Комната не найдена. Проверь код.")
            game = self.aggregate(row)
            yield game, session
            if game.state != row["state"] or game.name != row["name"]:
                await session.execute(
                    update(rooms)
                    .where(rooms.c.code == code)
                    .values(state=game.state, name=game.name)
                )
            await self.enqueue_images(session, game)

    async def enqueue_images(self, session, game):
        if (
            game.state["phase"] not in ("answer", "briefing")
            or not game.state["rounds"]
        ):
            return
        row = game.current()
        for owner, job in row.get("image_jobs", {}).items():
            if job.get("status") != "queued":
                continue
            await session.execute(
                postgres_insert(image_requests)
                .values(
                    id=job["id"],
                    room_code=game.code,
                    round_id=row["round_id"],
                    owner=owner,
                    prompt=job["text"],
                    trace_context=capture_context(),
                    status="pending",
                    attempts=0,
                    next_attempt=0,
                    lease_until=0,
                )
                .on_conflict_do_nothing()
            )

    @observed("backend.repository.artifact")
    async def artifact(self, code, filename, session=None):
        if session is None:
            async with self.database.transaction() as transaction:
                return await self.artifact(code, filename, transaction)
        return (
            (
                await session.execute(
                    select(artifacts).where(
                        artifacts.c.room_code == code, artifacts.c.filename == filename
                    )
                )
            )
            .mappings()
            .first()
        )

    @observed("backend.repository.store_artifact")
    async def store_artifact(self, session, code, filename, key, content_type, size):
        await session.execute(
            postgres_insert(artifacts)
            .values(
                room_code=code,
                filename=filename,
                object_key=key,
                content_type=content_type,
                size=size,
            )
            .on_conflict_do_nothing()
        )

    async def claim_image(self):
        now = time.time()
        async with self.database.transaction() as session:
            row = (
                (
                    await session.execute(
                        select(image_requests)
                        .where(
                            image_requests.c.status == "pending",
                            image_requests.c.next_attempt <= now,
                            image_requests.c.lease_until <= now,
                        )
                        .order_by(image_requests.c.next_attempt, image_requests.c.id)
                        .with_for_update(skip_locked=True)
                        .limit(1)
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            token = uuid.uuid4().hex
            await session.execute(
                update(image_requests)
                .where(image_requests.c.id == row["id"])
                .values(lease_until=now + 60, lease_token=token)
            )
            return {**row, "lease_token": token}

    async def update_request(self, request, **values):
        async with self.database.transaction() as session:
            await session.execute(
                update(image_requests)
                .where(
                    image_requests.c.id == request["id"],
                    image_requests.c.lease_token == request["lease_token"],
                )
                .values(**values, lease_until=0, lease_token=None)
            )

    @observed("backend.repository.finish_image")
    async def finish_image(self, request, response):
        async with self.locked(request["room_code"]) as (game, session):
            row = (
                (
                    await session.execute(
                        select(image_requests)
                        .where(image_requests.c.id == request["id"])
                        .with_for_update()
                    )
                )
                .mappings()
                .one()
            )
            if row["lease_token"] != request["lease_token"]:
                return
            image = None
            error = None
            moderated = False
            if response.status == "succeeded":
                result = response.result
                filename = str(response.id) + ".png"
                await self.store_artifact(
                    session,
                    game.code,
                    filename,
                    result.object_key,
                    result.media_type,
                    result.bytes,
                )
                image = game.image_url(filename)
            else:
                error = (
                    response.error.message
                    if response.error
                    else "Не удалось создать изображение"
                )
                moderated = bool(response.error and response.error.code == "moderated")
            game.apply_image(
                request["round_id"],
                request["owner"],
                request["id"],
                image=image,
                error=error,
                moderated=moderated,
            )
            await session.execute(
                update(image_requests)
                .where(image_requests.c.id == request["id"])
                .values(status="done", lease_until=0, lease_token=None)
            )

    @observed("backend.repository.reject_image")
    async def reject_image(self, request, message):
        async with self.locked(request["room_code"]) as (game, session):
            row = (
                (
                    await session.execute(
                        select(image_requests)
                        .where(image_requests.c.id == request["id"])
                        .with_for_update()
                    )
                )
                .mappings()
                .one()
            )
            if row["lease_token"] != request["lease_token"]:
                return
            game.apply_image(
                request["round_id"], request["owner"], request["id"], error=message
            )
            await session.execute(
                update(image_requests)
                .where(image_requests.c.id == request["id"])
                .values(status="done", lease_until=0, lease_token=None)
            )

    async def statistics(self):
        async with self.database.transaction() as session:
            phase = rooms.c.state["phase"].as_string()
            phases = dict(
                (
                    await session.execute(select(phase, func.count()).group_by(phase))
                ).all()
            )
            pending = (
                await session.execute(
                    select(func.count())
                    .select_from(image_requests)
                    .where(image_requests.c.status == "pending")
                )
            ).scalar_one()
        return phases, pending
