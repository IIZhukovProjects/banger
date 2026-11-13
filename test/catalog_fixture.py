"""Test-only game data; production reads CatalogRepository from PostgreSQL."""

import json
from pathlib import Path
from game.catalog import GameCatalog

CATALOG_SNAPSHOT = GameCatalog.from_dict(
    json.loads(
        (Path(__file__).resolve().parents[1] / "services/backend/src/game/catalog_seed.json").read_text()
    )
)
CATALOG = CATALOG_SNAPSHOT.modes
MODES = CATALOG_SNAPSHOT.mode_info
POWERS = CATALOG_SNAPSHOT.powers
