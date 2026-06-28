#!/usr/bin/env python3
"""
Run OperaOps infrastructure migrations (Hindsight + Supabase).

Usage:
  python scripts/migrate.py
  python scripts/migrate.py --hindsight-only
  python scripts/migrate.py --supabase-only
  python scripts/migrate.py --force   # re-seed Hindsight memories
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from migrations.hindsight import run as run_hindsight  # noqa: E402
from migrations.supabase import run as run_supabase  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OperaOps migrations")
    parser.add_argument("--hindsight-only", action="store_true")
    parser.add_argument("--supabase-only", action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-seed Hindsight bank")
    args = parser.parse_args()

    results: dict = {}

    if not args.supabase_only:
        results["hindsight"] = run_hindsight(force=args.force)

    if not args.hindsight_only:
        results["supabase"] = run_supabase()

    print(json.dumps(results, indent=2))

    if results.get("hindsight", {}).get("status") == "error":
        return 1
    if results.get("supabase", {}).get("status") == "error":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
