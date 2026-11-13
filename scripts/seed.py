"""Explicit seed import. Credentials come from backend ENV binding, not CLI arguments."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--environment", default="local")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = args.project.resolve()
    sys.path.insert(0, str(root / "services/backend/src"))
    from game.catalog import GameCatalog

    try:
        path = args.file or root / "services/backend/src/game/catalog_seed.json"
        if not path.is_absolute():
            path = root / path
        catalog = GameCatalog.from_dict(json.loads(path.read_text(encoding="utf-8")))
        if args.dry_run:
            print(
                json.dumps(
                    {
                        "modes": len(catalog.modes),
                        "prompts": sum(
                            len(mode["prompts"]) for mode in catalog.modes.values()
                        ),
                        "powers": len(catalog.powers),
                    }
                )
            )
            return 0
        from platform_codegen.generation.toolchain import verify
        from platform_codegen.configuration.environment import resolve_environment
        from seed_catalog import seed

        verify(root)
        values = resolve_environment(
            root, "backend", args.environment, only={"DATABASE_URL"}
        )
        url = os.environ.get("DATABASE_URL") or values.get("DATABASE_URL")
        if not url:
            raise ValueError("DATABASE_URL is required from backend runtime ENV")
        print(
            json.dumps(
                asyncio.run(seed(url, catalog, overwrite=True)), ensure_ascii=False
            )
        )
        return 0
    except (OSError, ValueError) as error:
        # Validation paths/messages contain no connection strings or seed values.
        print(
            "Seed validation failed: "
            + (
                str(error)
                if isinstance(error, ValueError)
                and str(error).startswith(("Invalid catalogue:", "DATABASE_URL"))
                else type(error).__name__
            ),
            file=sys.stderr,
        )
        return 1
    except Exception as error:
        print(
            "Seed failed (" + type(error).__name__ + "); connection details suppressed",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
