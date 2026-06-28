"""
Hindsight migration: ensure opera memory bank exists and seed synthetic incidents.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

import env_loader  # noqa: F401

HINDSIGHT_BASE_URL = os.getenv("HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io")
HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY")
HINDSIGHT_BANK_ID = os.getenv("HINDSIGHT_BANK_ID", "opera")

INCIDENTS_PATH = env_loader.PROJECT_ROOT / "data" / "incidents.json"
MIGRATION_MARKER = env_loader.PROJECT_ROOT / "data" / ".hindsight_migration_v1.json"

BANK_MISSION = (
    "You are OperaOps incident memory. Retain root causes, fixes, services, "
    "severity, and error signatures from production incidents for future recall."
)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {HINDSIGHT_API_KEY}",
        "Content-Type": "application/json",
    }


def ensure_bank(client: httpx.Client, bank_id: str) -> dict:
    response = client.put(
        f"{HINDSIGHT_BASE_URL}/v1/default/banks/{bank_id}",
        headers=_headers(),
        json={
            "name": "OperaOps",
            "mission": BANK_MISSION,
            "disposition": {"skepticism": 3, "literalism": 4, "empathy": 2},
        },
        timeout=30.0,
    )
    if response.status_code in (200, 201):
        return {"status": "ok", "bank_id": bank_id, "action": "created_or_updated"}

    list_response = client.get(
        f"{HINDSIGHT_BASE_URL}/v1/default/banks",
        headers=_headers(),
        timeout=15.0,
    )
    list_response.raise_for_status()
    banks = list_response.json().get("banks", [])
    if any(b.get("bank_id") == bank_id for b in banks):
        return {"status": "ok", "bank_id": bank_id, "action": "already_exists"}
    response.raise_for_status()
    return {"status": "error"}


def _incident_memory_content(incident: dict) -> str:
    return (
        f"Incident: {incident['title']} | Service: {incident['service']} | "
        f"Severity: {incident['severity']} | Category: {incident.get('category', 'unknown')} | "
        f"Error: {incident['error_message'][:300]} | "
        f"Known fix: {incident.get('known_fix', '')[:400]} | "
        f"Typical resolution: {incident.get('resolution_time_minutes', 0)} minutes"
    )


def seed_incidents(client: httpx.Client, bank_id: str, force: bool = False, batch_size: int = 10) -> dict:
    if MIGRATION_MARKER.exists() and not force:
        marker = json.loads(MIGRATION_MARKER.read_text(encoding="utf-8"))
        return {"status": "skipped", "reason": "already_seeded", **marker}

    incidents = json.loads(INCIDENTS_PATH.read_text(encoding="utf-8"))
    items = []
    for incident in incidents:
        items.append(
            {
                "content": _incident_memory_content(incident),
                "context": f"seed:{incident.get('category', 'unknown')}",
                "document_id": f"seed_{incident['id']}",
                "metadata": {
                    "incident_id": incident["id"],
                    "service": incident["service"],
                    "severity": incident["severity"],
                    "category": incident.get("category"),
                    "source": "operaops_migration",
                },
            }
        )

    batches = [items[i : i + batch_size] for i in range(0, len(items), batch_size)]
    total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    seeded = 0

    for idx, batch in enumerate(batches, start=1):
        response = client.post(
            f"{HINDSIGHT_BASE_URL}/v1/default/banks/{bank_id}/memories",
            headers=_headers(),
            json={"items": batch, "async": False},
            timeout=300.0,
        )
        response.raise_for_status()
        body = response.json()
        seeded += body.get("items_count", len(batch))
        usage = body.get("usage") or {}
        for key in total_usage:
            total_usage[key] += usage.get(key, 0) or 0
        print(f"  Hindsight batch {idx}/{len(batches)}: {len(batch)} incidents retained")

    marker = {
        "bank_id": bank_id,
        "seeded_count": seeded,
        "batches": len(batches),
        "hindsight_response": {
            "success": True,
            "items_count": seeded,
            "usage": total_usage,
        },
    }
    MIGRATION_MARKER.write_text(json.dumps(marker, indent=2), encoding="utf-8")
    return {"status": "seeded", **marker}


def run(force: bool = False) -> dict:
    if not HINDSIGHT_API_KEY:
        return {"status": "skipped", "reason": "HINDSIGHT_API_KEY not set"}

    bank_id = HINDSIGHT_BANK_ID
    with httpx.Client() as client:
        health = client.get(f"{HINDSIGHT_BASE_URL}/health", timeout=15.0)
        health.raise_for_status()
        bank_result = ensure_bank(client, bank_id)
        seed_result = seed_incidents(client, bank_id, force=force)

    return {
        "status": "ok",
        "base_url": HINDSIGHT_BASE_URL,
        "bank": bank_result,
        "seed": seed_result,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Hindsight migrations for OperaOps")
    parser.add_argument("--force", action="store_true", help="Re-seed synthetic incidents")
    args = parser.parse_args()
    result = run(force=args.force)
    print(json.dumps(result, indent=2))
