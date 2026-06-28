"""
eval_harness.py
Benchmark runner against data/incidents.json
"""

import asyncio
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, asdict

from agent import run_agent_pipeline
from tools.eval_tool import compare_to_known_fix
from tools.validator import validate_diagnosis
from tools.policy import escalation_check
from cascade_router import cascade
from hindsight_client import hindsight

INCIDENTS_PATH = Path(__file__).parent.parent / "data" / "incidents.json"

_latest_results: dict = {}


@dataclass
class EvalRunResult:
    incident_id: str
    fms_score: float | None
    json_valid: bool
    escalation_ok: bool
    cost_usd: float
    latency_ms: int
    llm_skipped: bool
    expert: str


async def _run_single(incident: dict) -> EvalRunResult:
    incident = {**incident, "id": f"eval_{incident['id']}"}
    result = await run_agent_pipeline(incident)
    diagnosis = result["diagnosis"]
    validation = validate_diagnosis(diagnosis)
    fms = compare_to_known_fix(diagnosis, incident.get("known_fix"))
    policy = escalation_check(diagnosis, incident["severity"], result["moe"]["memory_confidence"])

    return EvalRunResult(
        incident_id=incident["id"],
        fms_score=fms.get("score"),
        json_valid=validation["valid"],
        escalation_ok=policy["passed"],
        cost_usd=result["routing"]["cost_usd"],
        latency_ms=result["total_time_ms"],
        llm_skipped=result["moe"]["llm_skipped"],
        expert=result["moe"]["activated_expert"],
    )


async def run_eval(runs: int = 1, incident_ids: list[str] | None = None) -> dict:
    global _latest_results

    with open(INCIDENTS_PATH) as f:
        incidents = json.load(f)

    if incident_ids:
        incidents = [i for i in incidents if i["id"] in incident_ids]

    all_results: list[EvalRunResult] = []
    for _ in range(runs):
        for inc in incidents:
            all_results.append(await _run_single(inc))

    n = len(all_results)
    fms_scores = [r.fms_score for r in all_results if r.fms_score is not None]
    summary = {
        "total_runs": n,
        "json_validity_rate": sum(1 for r in all_results if r.json_valid) / n,
        "avg_fms": sum(fms_scores) / len(fms_scores) if fms_scores else 0,
        "avg_cost_usd": sum(r.cost_usd for r in all_results) / n,
        "avg_latency_ms": sum(r.latency_ms for r in all_results) / n,
        "fast_path_rate": sum(1 for r in all_results if r.llm_skipped) / n,
        "escalation_pass_rate": sum(1 for r in all_results if r.escalation_ok) / n,
        "session_summary": cascade.get_session_summary(),
        "results": [asdict(r) for r in all_results],
    }
    _latest_results = summary
    return summary


def get_latest_results() -> dict:
    return _latest_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--config", default="optimized")
    args = parser.parse_args()
    result = asyncio.run(run_eval(runs=args.runs))
    print(json.dumps(result, indent=2))
