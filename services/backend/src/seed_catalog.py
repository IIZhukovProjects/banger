"""Initialize the PostgreSQL catalogue before starting the service."""

import asyncio
import json
import os
from pathlib import Path
import sys

from catalog_repository import CatalogRepository
from game.catalog import GameCatalog
from platform_codegen.runtime.database import Database


SEED_FILE = Path(__file__).parent / "game/catalog_seed.json"


def load_seed(path=SEED_FILE):
    return GameCatalog.from_dict(json.loads(path.read_text(encoding="utf-8")))


async def seed(url, catalog, *, overwrite):
    database = Database(url)
    try:
        return await CatalogRepository(database).seed(catalog, overwrite=overwrite)
    finally:
        await database.close()


def main():
    try:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise ValueError("DATABASE_URL is required")
        counts = asyncio.run(seed(url, load_seed(), overwrite=False))
    except Exception as error:
        print(
            f"Catalogue initialization failed ({type(error).__name__})", file=sys.stderr
        )
        return 1
    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
