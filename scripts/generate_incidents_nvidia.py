#!/usr/bin/env python3
"""
Generate synthetic OperaOps incidents with NVIDIA NeMo Data Designer.

Uses seed data from data/incidents.json and NVIDIA Build API (NVIDIA_API_KEY).

Usage:
  python scripts/generate_incidents_nvidia.py --preview
  python scripts/generate_incidents_nvidia.py --count 35
  python scripts/generate_incidents_nvidia.py --count 35 --merge
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import env_loader  # noqa: F401

INCIDENTS_PATH = ROOT / "data" / "incidents.json"
OUTPUT_DIR = ROOT / "data" / "generated"
VALID_CATEGORIES = {"database", "deployment", "memory", "api", "infrastructure"}
VALID_SEVERITIES = {"P1", "P2", "P3"}


class SyntheticIncident(BaseModel):
    title: str = Field(description="Short incident title with service name")
    service: str = Field(description="Microservice name e.g. payments-service")
    severity: str = Field(description="P1, P2, or P3")
    error_message: str = Field(description="Primary error string from logs or alerts")
    stack_trace: str = Field(description="3-6 line stack trace or kube event snippet")
    category: str = Field(description="One of database, deployment, memory, api, infrastructure")
    known_fix: str = Field(description="Specific actionable remediation steps")
    resolution_time_minutes: int = Field(ge=4, le=60, description="Typical minutes to resolve")


def _require_nvidia_key() -> str:
    key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not key:
        raise RuntimeError("NVIDIA_API_KEY not set in .env.local")
    os.environ.setdefault("NVIDIA_API_KEY", key)
    os.environ.setdefault("NEMO_TELEMETRY_ENABLED", "false")
    return key


def _build_config():
    import data_designer.config as dd
    from data_designer.config.default_model_settings import (
        get_builtin_model_configs,
        get_builtin_model_providers,
        resolve_seed_default_model_settings,
    )
    from data_designer.interface import DataDesigner

    resolve_seed_default_model_settings()

    seed_path = INCIDENTS_PATH
    if not seed_path.exists():
        raise FileNotFoundError(f"Seed file missing: {seed_path}")

    model_configs = get_builtin_model_configs()
    if not any(mc.alias == "nvidia-text" for mc in model_configs):
        raise RuntimeError("NeMo Data Designer NVIDIA model configs not available")

    builder = dd.DataDesignerConfigBuilder(model_configs=model_configs)
    builder.with_seed_dataset(
        dd.LocalFileSeedSource(path=str(seed_path)),
        sampling_strategy="shuffle",
    )

    builder.add_column(
        dd.LLMStructuredColumnConfig(
            name="incident",
            model_alias="nvidia-text",
            system_prompt=(
                "You are an expert SRE creating realistic production incident records "
                "for an on-call training dataset. Output must be novel — do not copy seed text."
            ),
            prompt="""\
Generate a NEW production incident inspired by this seed example (same category family, different details).

Seed title: {{ title }}
Seed service: {{ service }}
Seed category: {{ category }}
Seed error: {{ error_message }}
Seed fix pattern: {{ known_fix }}

Requirements:
- Use a different service name and error signature than the seed
- severity must be P1, P2, or P3
- category must be exactly: {{ category }}
- stack_trace: realistic multi-line trace
- known_fix: concrete commands or config changes
""",
            output_format=SyntheticIncident,
        )
    )

    designer = DataDesigner(model_providers=get_builtin_model_providers())
    return builder, designer


def _next_id(existing: list[dict]) -> int:
    nums = []
    for item in existing:
        match = re.match(r"inc_(\d+)", item.get("id", ""))
        if match:
            nums.append(int(match.group(1)))
    return max(nums, default=0) + 1


def _flatten_records(df) -> list[dict]:
    records: list[dict] = []
    for _, row in df.iterrows():
        payload = row.get("incident")
        if isinstance(payload, str):
            payload = json.loads(payload)
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump()
        if not isinstance(payload, dict):
            continue

        if payload.get("category") not in VALID_CATEGORIES:
            continue
        if payload.get("severity") not in VALID_SEVERITIES:
            payload["severity"] = "P2"
        try:
            payload["resolution_time_minutes"] = int(payload.get("resolution_time_minutes", 15))
        except (TypeError, ValueError):
            payload["resolution_time_minutes"] = 15

        if all(str(payload.get(k, "")).strip() for k in (
            "title", "service", "error_message", "stack_trace", "known_fix"
        )):
            records.append(payload)
    return records


def _assign_ids(records: list[dict], existing: list[dict]) -> list[dict]:
    seen_titles = {e["title"] for e in existing}
    next_num = _next_id(existing)
    out: list[dict] = []
    for rec in records:
        if rec["title"] in seen_titles:
            continue
        rec["id"] = f"inc_{next_num:03d}"
        next_num += 1
        seen_titles.add(rec["title"])
        out.append(rec)
    return out


def run(count: int, preview: bool, merge: bool) -> dict:
    _require_nvidia_key()
    builder, designer = _build_config()

    if preview:
        print(f"Previewing {min(count, 5)} incidents via NeMo Data Designer + NVIDIA API...")
        result = designer.preview(config_builder=builder, num_records=min(count, 5))
        df = result.dataset
    else:
        print(f"Generating {count} incidents via NeMo Data Designer + NVIDIA API...")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        result = designer.create(
            config_builder=builder,
            num_records=count,
            dataset_name="operaops_incidents",
            artifact_path=str(OUTPUT_DIR),
        )
        df = result.load_dataset()

    generated = _assign_ids(_flatten_records(df), json.loads(INCIDENTS_PATH.read_text(encoding="utf-8")))

    summary = {
        "status": "ok",
        "engine": "nemo-data-designer",
        "provider": "nvidia-build",
        "requested": count,
        "generated": len(generated),
        "preview": preview,
    }

    if preview:
        summary["sample"] = generated[:3]
        print(json.dumps(summary, indent=2))
        return summary

    out_path = OUTPUT_DIR / "incidents_nvidia.json"
    out_path.write_text(json.dumps(generated, indent=2) + "\n", encoding="utf-8")
    summary["output"] = str(out_path)

    if merge and generated:
        existing = json.loads(INCIDENTS_PATH.read_text(encoding="utf-8"))
        merged = existing + generated
        INCIDENTS_PATH.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        summary["merged_total"] = len(merged)
        summary["merged_into"] = str(INCIDENTS_PATH)

    print(json.dumps(summary, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate incidents with NeMo Data Designer")
    parser.add_argument("--count", type=int, default=35, help="Number of incidents to generate")
    parser.add_argument("--preview", action="store_true", help="Preview only (max 5 records)")
    parser.add_argument("--merge", action="store_true", help="Append results to data/incidents.json")
    args = parser.parse_args()

    try:
        result = run(count=args.count, preview=args.preview, merge=args.merge)
    except Exception as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, indent=2))
        return 1

    if not result.get("generated") and not args.preview:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
