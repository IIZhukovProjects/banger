from copy import deepcopy
import unittest
from sqlalchemy import select, func, update, insert
from sqlalchemy.exc import IntegrityError

from platform_codegen.runtime.database import Database
from catalog_repository import (
    CatalogRepository,
    CatalogNotSeeded,
    metadata,
    modes,
    prompts,
    powers,
)
from game.catalog import GameCatalog
from catalog_fixture import CATALOG_SNAPSHOT


class CatalogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = Database("sqlite+aiosqlite:///:memory:")
        async with self.database.engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
        self.repository = CatalogRepository(self.database)

    async def asyncTearDown(self):
        await self.database.close()

    async def test_empty_catalog_requires_explicit_seed(self):
        with self.assertRaisesRegex(CatalogNotSeeded, "scripts/seed.py"):
            await self.repository.load()

    async def test_seed_is_idempotent_updates_and_reads_database(self):
        expected = {"modes": 16, "prompts": 118, "powers": 5}
        self.assertEqual(await self.repository.seed(CATALOG_SNAPSHOT), expected)
        self.assertEqual(await self.repository.seed(CATALOG_SNAPSHOT), expected)
        async with self.database.transaction() as session:
            counts = [
                (
                    await session.execute(select(func.count()).select_from(table))
                ).scalar_one()
                for table in (modes, prompts, powers)
            ]
            await session.execute(
                update(modes)
                .where(modes.c.id == "excuses")
                .values(title="Название из БД")
            )
        self.assertEqual(counts, [16, 118, 5])
        snapshot = await self.repository.load()
        self.assertEqual(snapshot.modes["excuses"]["title"], "Название из БД")
        self.assertEqual(snapshot.mix_modes, CATALOG_SNAPSHOT.mix_modes)
        self.assertEqual(snapshot.powers, CATALOG_SNAPSHOT.powers)
        self.assertEqual(
            sum(len(mode["prompts"]) for mode in snapshot.modes.values()), 118
        )

    async def test_seed_keeps_additional_database_records(self):
        await self.repository.seed(CATALOG_SNAPSHOT)
        async with self.database.transaction() as session:
            await session.execute(
                insert(prompts).values(
                    id="custom-prompt",
                    mode_id="excuses",
                    position=999,
                    prompt="Своё задание",
                    context="Свой контекст",
                    payload={},
                )
            )
        await self.repository.seed(CATALOG_SNAPSHOT)
        catalog = await self.repository.load()
        self.assertIn(
            "custom-prompt", [row["id"] for row in catalog.prompts["excuses"]]
        )

    async def test_seed_transaction_rolls_back_all_tables_on_error(self):
        await self.repository.seed(CATALOG_SNAPSHOT)
        raw = {
            "modes": deepcopy(CATALOG_SNAPSHOT.modes),
            "mix": list(CATALOG_SNAPSHOT.mix_modes),
            "powers": {
                key: dict(zip(("title", "description", "icon"), row))
                for key, row in CATALOG_SNAPSHOT.powers.items()
            },
        }
        raw["modes"]["excuses"]["title"] = "Не должно сохраниться"
        snapshot = GameCatalog.from_dict(raw)
        # Deliberately damage an already validated snapshot to force a DB constraint error.
        snapshot.modes["clue"]["kind"] = "unsupported"
        with self.assertRaises(IntegrityError):
            await self.repository.seed(snapshot)
        catalog = await self.repository.load()
        self.assertEqual(
            catalog.modes["excuses"]["title"],
            CATALOG_SNAPSHOT.modes["excuses"]["title"],
        )
