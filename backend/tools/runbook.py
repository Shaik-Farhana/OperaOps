"""Runbook lookup tool."""

import json
from pathlib import Path

_RUNBOOKS_PATH = Path(__file__).parent.parent.parent / "data" / "runbooks.json"
_runbooks_cache: dict | None = None


def _load_runbooks() -> dict:
    global _runbooks_cache
    if _runbooks_cache is None:
        with open(_RUNBOOKS_PATH) as f:
            _runbooks_cache = json.load(f)
    return _runbooks_cache


def fetch_runbook(category: str) -> dict:
    books = _load_runbooks()
    book = books.get(category, books.get("deployment"))
    return {
        "category": category,
        "title": book["title"],
        "steps": book["steps"],
        "common_causes": book["common_causes"],
        "snippet": "\n".join(f"{i+1}. {s}" for i, s in enumerate(book["steps"])),
    }
