"""PostgreSQL catalogue storage and explicit, idempotent seed import."""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    JSON,
    MetaData,
    Table,
    ForeignKey,
    CheckConstraint,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from platform_codegen.runtime.operations import observed
from game.catalog import GameCatalog

metadata = MetaData()
json_type = JSON().with_variant(JSONB, "postgresql")
modes = Table(
    "game_modes",
    metadata,
    Column("id", String(63), primary_key=True),
    Column("position", Integer, nullable=False),
    Column("title", String(200), nullable=False),
    Column("description", Text, nullable=False),
    Column("icon", String(32), nullable=False),
    Column("tone", String(32), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("fields", json_type, nullable=False),
    Column("mix_position", Integer),
    CheckConstraint(
        "kind IN ('text','image','shared','relay')", name="ck_game_modes_kind"
    ),
    CheckConstraint(
        "position >= 0 AND (mix_position IS NULL OR mix_position >= 0)",
        name="ck_game_modes_position",
    ),
)
prompts = Table(
    "game_prompts",
    metadata,
    Column("id", String(128), primary_key=True),
    Column("mode_id", String(63), ForeignKey("game_modes.id"), nullable=False),
    Column("position", Integer, nullable=False),
    Column("prompt", Text, nullable=False),
    Column("context", Text, nullable=False),
    Column("payload", json_type, nullable=False),
    CheckConstraint("position >= 0", name="ck_game_prompts_position"),
)
powers = Table(
    "game_powers",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("position", Integer, nullable=False),
    Column("title", String(200), nullable=False),
    Column("description", Text, nullable=False),
    Column("icon", String(32), nullable=False),
    CheckConstraint("position >= 0", name="ck_game_powers_position"),
)


class CatalogNotSeeded(RuntimeError):
    def __init__(self):
        super().__init__(
            "Game catalogue is empty; run python scripts/seed.py after migrations"
        )


class CatalogRepository:
    def __init__(self, database):
        self.database = database
        self.telemetry = getattr(database, "telemetry", None)

    @observed("catalog.load")
    async def load(self):
        async with self.database.transaction() as session:
            if self.database.engine.dialect.name == "postgresql":
                await session.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                )
            mode_rows = (
                (
                    await session.execute(
                        select(modes).order_by(modes.c.position, modes.c.id)
                    )
                )
                .mappings()
                .all()
            )
            prompt_rows = (
                (
                    await session.execute(
                        select(prompts).order_by(
                            prompts.c.mode_id, prompts.c.position, prompts.c.id
                        )
                    )
                )
                .mappings()
                .all()
            )
            power_rows = (
                (
                    await session.execute(
                        select(powers).order_by(powers.c.position, powers.c.id)
                    )
                )
                .mappings()
                .all()
            )
        if not mode_rows or not prompt_rows or not power_rows:
            raise CatalogNotSeeded()
        data = {
            row["id"]: {
                field: row[field]
                for field in ("title", "description", "icon", "tone", "kind")
            }
            for row in mode_rows
        }
        for row in mode_rows:
            data[row["id"]]["prompts"] = []
            if row["fields"]:
                data[row["id"]]["fields"] = row["fields"]
        for row in prompt_rows:
            data[row["mode_id"]]["prompts"].append(
                {
                    **row["payload"],
                    "id": row["id"],
                    "prompt": row["prompt"],
                    "context": row["context"],
                }
            )
        playlist = [
            row["id"]
            for row in sorted(
                (row for row in mode_rows if row["mix_position"] is not None),
                key=lambda row: (row["mix_position"], row["id"]),
            )
        ]
        return GameCatalog.from_dict(
            {
                "modes": data,
                "mix": playlist,
                "powers": {
                    row["id"]: {
                        field: row[field] for field in ("title", "description", "icon")
                    }
                    for row in power_rows
                },
            }
        )

    @observed("catalog.seed")
    async def seed(self, catalog, *, overwrite=True):
        # All input validation happens before this transaction; room/job tables are untouched.
        factory = {"postgresql": pg_insert, "sqlite": sqlite_insert}[
            self.database.engine.dialect.name
        ]
        playlist = {name: index for index, name in enumerate(catalog.mix_modes)}
        mode_rows = [
            {
                "id": name,
                "position": index,
                **{
                    field: mode[field]
                    for field in ("title", "description", "icon", "tone", "kind")
                },
                "fields": mode.get("fields", []),
                "mix_position": playlist.get(name),
            }
            for index, (name, mode) in enumerate(catalog.modes.items())
        ]
        prompt_rows = [
            {
                "id": row["id"],
                "mode_id": name,
                "position": index,
                "prompt": row["prompt"],
                "context": row["context"],
                "payload": {
                    key: value
                    for key, value in row.items()
                    if key not in ("id", "prompt", "context")
                },
            }
            for name, mode in catalog.modes.items()
            for index, row in enumerate(mode["prompts"])
        ]
        power_rows = [
            {
                "id": name,
                "position": index,
                **dict(zip(("title", "description", "icon"), row)),
            }
            for index, (name, row) in enumerate(catalog.powers.items())
        ]
        async with self.database.transaction() as session:
            for table, rows in (
                (modes, mode_rows),
                (prompts, prompt_rows),
                (powers, power_rows),
            ):
                statement = factory(table).values(rows)
                if overwrite:
                    statement = statement.on_conflict_do_update(
                        index_elements=["id"],
                        set_={
                            column.name: statement.excluded[column.name]
                            for column in table.c
                            if not column.primary_key
                        },
                    )
                else:
                    statement = statement.on_conflict_do_nothing(index_elements=["id"])
                await session.execute(statement)
        return {
            "modes": len(mode_rows),
            "prompts": len(prompt_rows),
            "powers": len(power_rows),
        }
