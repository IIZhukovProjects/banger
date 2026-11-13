"""Run application tests with both service source roots; no Docker or paid API."""

import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
environment = dict(os.environ)
environment["PYTHONPATH"] = os.pathsep.join(
    [
        str(root / "services/backend/src"),
        str(root / "services/llm/src"),
        environment.get("PYTHONPATH", ""),
    ]
)
raise SystemExit(
    subprocess.call(
        [sys.executable, "-m", "unittest", "discover", "-s", str(root / "test"), "-v"],
        cwd=root,
        env=environment,
    )
)
