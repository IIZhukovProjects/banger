from contextlib import nullcontext
from platform_codegen.runtime.operations import capture_context, observed
from datetime import datetime, timezone
import hashlib
import time
import uuid

from sqlalchemy import (
    Column,
    Float,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, insert


metadata = MetaData()
json_type = JSON().with_variant(JSONB, "postgresql")
jobs = Table(
    "image_jobs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("idempotency_key", String(128), nullable=False, unique=True),
    Column("fingerprint", String(64), nullable=False),
    Column("prompt", Text, nullable=False),
    Column("provider", String(20), nullable=False),
    Column("model", String(200), nullable=False),
    Column("provider_base_url", String(2048)),
    Column("provider_id", String(300)),
    Column("phase", String(30), nullable=False),
    Column("status", String(30), nullable=False),
    Column("result", json_type),
    Column("error", json_type),
    Column("created_at", Float, nullable=False),
    Column("updated_at", Float, nullable=False),
    Column("lease_until", Float, nullable=False),
    Column("lease_token", String(32)),
    Column("trace_context", json_type, nullable=False, server_default="{}"),
    Column("next_attempt", Float, nullable=False),
    Column("attempts", Integer, nullable=False),
)


class JobConflict(Exception):
    status = 409


class QueueFull(Exception):
    status = 429


class JobRepository:
    def __init__(self, database):
        self.database = database
        self.telemetry = getattr(database, "telemetry", None)

    async def ready(self):
        async with self.database.transaction() as session:
            await session.execute(select(jobs.c.provider_base_url).limit(0))

    @observed("llm.repository.create")
    async def create(self, key, prompt, provider, model, limit, *, provider_base_url):
        normalized = prompt.strip()
        fingerprint = hashlib.sha256(normalized.encode()).hexdigest()
        now = time.time()
        async with self.database.transaction() as session:
            existing = (
                (
                    await session.execute(
                        select(jobs).where(jobs.c.idempotency_key == key)
                    )
                )
                .mappings()
                .first()
            )
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise JobConflict()
                return existing
            pending = (
                await session.execute(
                    select(func.count())
                    .select_from(jobs)
                    .where(jobs.c.status.in_(("queued", "running")))
                )
            ).scalar_one()
            if pending >= limit:
                raise QueueFull()
            row = (
                (
                    await session.execute(
                        insert(jobs)
                        .values(
                            id=str(uuid.uuid4()),
                            idempotency_key=key,
                            fingerprint=fingerprint,
                            prompt=normalized,
                            trace_context=capture_context(),
                            provider=provider,
                            model=model,
                            provider_base_url=provider_base_url,
                            phase="queued",
                            status="queued",
                            created_at=now,
                            updated_at=now,
                            lease_until=0,
                            next_attempt=0,
                            attempts=0,
                        )
                        .on_conflict_do_nothing(index_elements=[jobs.c.idempotency_key])
                        .returning(jobs)
                    )
                )
                .mappings()
                .first()
            )
            if row:
                return row
            existing = (
                (
                    await session.execute(
                        select(jobs).where(jobs.c.idempotency_key == key)
                    )
                )
                .mappings()
                .one()
            )
            if existing["fingerprint"] != fingerprint:
                raise JobConflict()
            return existing

    @observed("llm.repository.get")
    async def get(self, identifier):
        async with self.database.transaction() as session:
            return (
                (
                    await session.execute(
                        select(jobs).where(jobs.c.id == str(identifier))
                    )
                )
                .mappings()
                .first()
            )

    @staticmethod
    def public(row):
        value = {
            "id": row["id"],
            "status": row["status"],
            "createdAt": datetime.fromtimestamp(row["created_at"], timezone.utc),
            "updatedAt": datetime.fromtimestamp(row["updated_at"], timezone.utc),
        }
        if row["result"] is not None:
            value["result"] = row["result"]
        if row["error"] is not None:
            value["error"] = row["error"]
        return value

    async def claim(self):
        now = time.time()
        async with self.database.transaction() as session:
            row = (
                (
                    await session.execute(
                        select(jobs)
                        .where(
                            jobs.c.status.in_(("queued", "running")),
                            jobs.c.next_attempt <= now,
                            jobs.c.lease_until <= now,
                        )
                        .order_by(jobs.c.created_at)
                        .with_for_update(skip_locked=True)
                        .limit(1)
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            if (
                row["provider"] == "polza"
                and row["phase"] == "submitting"
                and (not row["provider_id"])
            ):
                with (
                    self.telemetry.operation(
                        "image.job.reconcile", parent=row.get("trace_context") or {}
                    )
                    if self.telemetry
                    else nullcontext()
                ):
                    await session.execute(
                        update(jobs)
                        .where(jobs.c.id == row["id"])
                        .values(
                            status="needs_reconciliation",
                            phase="finished",
                            updated_at=now,
                            error={
                                "code": "submit_unknown",
                                "message": "Не удалось подтвердить отправку задания провайдеру. Нужна проверка операции.",
                            },
                            lease_until=0,
                            lease_token=None,
                        )
                    )
                    if self.telemetry:
                        self.telemetry.event(
                            "image.jobs.completed", {"status": "needs_reconciliation"}
                        )
                return None
            token = uuid.uuid4().hex
            await session.execute(
                update(jobs)
                .where(jobs.c.id == row["id"])
                .values(
                    status="running",
                    lease_until=now + 90,
                    lease_token=token,
                    updated_at=now,
                )
            )
            return {**row, "status": "running", "lease_token": token}

    @observed("llm.repository.save")
    async def save(self, job, *, release=True, **values):
        async with self.database.transaction() as session:
            values["updated_at"] = time.time()
            if release:
                values.update(lease_until=0, lease_token=None)
            result = await session.execute(
                update(jobs)
                .where(jobs.c.id == job["id"], jobs.c.lease_token == job["lease_token"])
                .values(**values)
            )
            changed = bool(result.rowcount)
        if (
            changed
            and values.get("status") in ("succeeded", "failed", "needs_reconciliation")
            and self.telemetry
        ):
            self.telemetry.event("image.jobs.completed", {"status": values["status"]})
        return changed

    async def statistics(self):
        async with self.database.transaction() as session:
            return dict(
                (
                    await session.execute(
                        select(jobs.c.status, func.count()).group_by(jobs.c.status)
                    )
                ).all()
            )
