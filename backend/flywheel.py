"""
flywheel.py
Append agent trajectories for NeMo Customizer SFT / data flywheel.
"""

import os
import json
import time
from pathlib import Path
import env_loader  # noqa: F401 — loads .env.local from project root

LOG_DIR = Path(os.getenv("FLYWHEEL_LOG_DIR", str(env_loader.PROJECT_ROOT / "data" / "trajectories")))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "trajectories.jsonl"


async def log_trajectory(entry: dict) -> None:
    record = {**entry, "timestamp": time.time()}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def get_trajectory_stats(limit: int = 5) -> dict:
    if not LOG_FILE.exists():
        return {"count": 0, "recent": []}

    lines = LOG_FILE.read_text(encoding="utf-8").strip().split("\n")
    records = [json.loads(l) for l in lines if l]
    return {
        "count": len(records),
        "log_path": str(LOG_FILE),
        "recent": records[-limit:],
    }
