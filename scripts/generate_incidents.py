#!/usr/bin/env python3
"""
Generate synthetic incidents for OperaOps using Groq.

Usage:
  python scripts/generate_incidents.py
  python scripts/generate_incidents.py --per-category 7
  python scripts/generate_incidents.py --dry-run
  python scripts/generate_incidents.py --output data/incidents_generated.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import env_loader  # noqa: F401
import llm_client

INCIDENTS_PATH = ROOT / "data" / "incidents.json"
RUNBOOKS_PATH = ROOT / "data" / "runbooks.json"

CATEGORIES = ["database", "deployment", "memory", "api", "infrastructure"]
REQUIRED_FIELDS = {
    "title",
    "service",
    "severity",
    "error_message",
    "stack_trace",
    "category",
    "known_fix",
    "resolution_time_minutes",
}
VALID_SEVERITIES = {"P1", "P2", "P3"}


def _load_examples() -> list[dict]:
    return json.loads(INCIDENTS_PATH.read_text(encoding="utf-8"))


def _load_runbook_hints() -> dict[str, list[str]]:
    books = json.loads(RUNBOOKS_PATH.read_text(encoding="utf-8"))
    return {k: v.get("common_causes", []) for k, v in books.items()}


def _next_id(existing: list[dict]) -> int:
    nums = []
    for item in existing:
        match = re.match(r"inc_(\d+)", item.get("id", ""))
        if match:
            nums.append(int(match.group(1)))
    return max(nums, default=0) + 1


def _validate_incident(raw: dict, category: str) -> dict | None:
    if not REQUIRED_FIELDS.issubset(raw.keys()):
        return None
    if raw.get("category") != category:
        raw = {**raw, "category": category}
    if raw["severity"] not in VALID_SEVERITIES:
        raw["severity"] = "P2"
    try:
        raw["resolution_time_minutes"] = int(raw["resolution_time_minutes"])
    except (TypeError, ValueError):
        raw["resolution_time_minutes"] = 15
    for key in ("title", "service", "error_message", "stack_trace", "known_fix"):
        if not str(raw.get(key, "")).strip():
            return None
    return raw


def _generate_batch(
    category: str,
    count: int,
    examples: list[dict],
    runbook_hints: list[str],
    existing_titles: set[str],
) -> list[dict]:
    sample = [e for e in examples if e.get("category") == category][:2]
    if not sample:
        sample = examples[:2]

    prompt = f"""Generate exactly {count} NEW production incident records as a JSON array.
Category: {category}
Common causes to vary: {", ".join(runbook_hints)}

Requirements:
- Realistic microservice names (e.g. payments-service, auth-service)
- Unique titles and error signatures (do NOT duplicate these existing titles: {list(existing_titles)[:8]})
- severity: P1, P2, or P3
- stack_trace: 3-6 lines with plausible file names and line numbers
- known_fix: specific actionable steps an on-call engineer would take
- resolution_time_minutes: integer 4-45

Return ONLY a JSON array of objects with keys:
title, service, severity, error_message, stack_trace, category, known_fix, resolution_time_minutes

Example shape:
{json.dumps(sample[0], indent=2)}
"""

    result = llm_client.complete(
        messages=[
            {
                "role": "system",
                "content": "You generate realistic SRE incident datasets. Output valid JSON arrays only.",
            },
            {"role": "user", "content": prompt},
        ],
        tier="nano",
        groq_model="openai/gpt-oss-20b",
        nim_model="openai/gpt-oss-20b",
        max_tokens=4096,
        json_mode=False,
        temperature=0.7,
        _force_groq=True,
    )

    if result.raw_error:
        raise RuntimeError(f"Groq generation failed for {category}: {result.raw_error}")

    text = result.content.strip()
    # Extract JSON array if model wrapped in markdown
    if "```" in text:
        match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
        if match:
            text = match.group(1)
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise RuntimeError(f"No JSON array in response for {category}")
    batch = json.loads(text[start : end + 1])
    if not isinstance(batch, list):
        raise RuntimeError(f"Expected list for {category}")

    validated = []
    for item in batch:
        cleaned = _validate_incident(item, category)
        if cleaned and cleaned["title"] not in existing_titles:
            validated.append(cleaned)
            existing_titles.add(cleaned["title"])
    return validated


def generate(per_category: int, dry_run: bool = False) -> dict:
    if not llm_client.GROQ_API_KEY:
        return {"status": "error", "reason": "GROQ_API_KEY not set in .env.local"}

    existing = _load_examples()
    runbooks = _load_runbook_hints()
    existing_titles = {e["title"] for e in existing}
    next_num = _next_id(existing)

    generated: list[dict] = []
    errors: list[str] = []

    for category in CATEGORIES:
        try:
            batch = _generate_batch(
                category,
                per_category,
                existing,
                runbooks.get(category, []),
                existing_titles,
            )
            for item in batch:
                item["id"] = f"inc_{next_num:03d}"
                next_num += 1
                generated.append(item)
            print(f"  {category}: +{len(batch)} incidents")
        except Exception as exc:
            errors.append(f"{category}: {exc}")
            print(f"  {category}: FAILED — {exc}")

    merged = existing + generated
    summary = {
        "status": "ok" if generated else "partial",
        "existing_count": len(existing),
        "generated_count": len(generated),
        "total_count": len(merged),
        "errors": errors,
    }

    if dry_run:
        summary["preview"] = generated[:3]
        return summary

    INCIDENTS_PATH.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    summary["output"] = str(INCIDENTS_PATH)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic OperaOps incidents via Groq")
    parser.add_argument("--per-category", type=int, default=7, help="New incidents per category (default 7 → +35 total)")
    parser.add_argument("--dry-run", action="store_true", help="Generate but do not write file")
    args = parser.parse_args()

    print(f"Generating ~{args.per_category * len(CATEGORIES)} incidents with Groq...")
    result = generate(per_category=args.per_category, dry_run=args.dry_run)
    print(json.dumps({k: v for k, v in result.items() if k != "preview"}, indent=2))
    if result.get("preview"):
        print("\nPreview:", json.dumps(result["preview"], indent=2)[:800])

    if result.get("status") == "error" or (not result.get("generated_count") and result.get("errors")):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
