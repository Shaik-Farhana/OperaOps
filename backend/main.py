"""
main.py
OperaOps FastAPI backend — DECA-IR incident response agent API
"""

import os
import json
import uuid
import time
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import env_loader  # noqa: F401 — loads .env.local from project root

from agent import run_agent_pipeline
from cascade_router import cascade
from hindsight_client import hindsight
from moe_router import get_moe_stats, list_experts
from llm_client import get_llm_status
from flywheel import get_trajectory_stats
from eval_harness import run_eval, get_latest_results

app = FastAPI(
    title="OperaOps API",
    description="DECA-IR AI incident response agent with MoE routing and persistent memory",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:5173"), "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

incidents_db: dict[str, dict] = {}
results_db: dict[str, dict] = {}

SYNTHETIC_INCIDENTS_PATH = Path(__file__).parent.parent / "data" / "incidents.json"
with open(SYNTHETIC_INCIDENTS_PATH) as f:
    SYNTHETIC_INCIDENTS = json.load(f)


class IncidentCreate(BaseModel):
    title: str
    service: str
    severity: str
    error_message: str
    stack_trace: Optional[str] = ""
    category: Optional[str] = "unknown"


class IncidentTrigger(BaseModel):
    synthetic_id: Optional[str] = None
    custom: Optional[IncidentCreate] = None


class EvalRequest(BaseModel):
    runs: int = 1
    incident_ids: Optional[list[str]] = None


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "OperaOps",
        "version": "2.0.0-deca-ir",
        "hindsight_mode": hindsight.mode if not hindsight._mock_mode else "mock",
        "cascadeflow": "active",
        "moe": "active",
        "llm": get_llm_status(),
        "flywheel": get_trajectory_stats(1),
    }


@app.get("/incidents/synthetic")
def list_synthetic():
    return SYNTHETIC_INCIDENTS


@app.post("/incidents/trigger")
async def trigger_incident(payload: IncidentTrigger):
    if payload.synthetic_id:
        incident = next(
            (i for i in SYNTHETIC_INCIDENTS if i["id"] == payload.synthetic_id), None
        )
        if not incident:
            raise HTTPException(status_code=404, detail=f"Synthetic incident {payload.synthetic_id} not found")
        incident = {**incident, "id": f"run_{str(uuid.uuid4())[:8]}", "source_id": payload.synthetic_id}
    elif payload.custom:
        incident = {"id": f"run_{str(uuid.uuid4())[:8]}", **payload.custom.model_dump()}
    else:
        raise HTTPException(status_code=400, detail="Provide either synthetic_id or custom incident")

    incident["timestamp"] = time.time()
    incident["status"] = "diagnosing"
    incidents_db[incident["id"]] = incident

    result = await run_agent_pipeline(incident)

    incidents_db[incident["id"]]["status"] = "resolved"
    incidents_db[incident["id"]]["result"] = result
    results_db[incident["id"]] = result

    return {"incident": incidents_db[incident["id"]], "result": result}


@app.get("/incidents")
def list_incidents():
    return list(incidents_db.values())


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str):
    if incident_id not in incidents_db:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"incident": incidents_db[incident_id], "result": results_db.get(incident_id)}


@app.post("/memory/recall")
async def recall_memory(payload: dict):
    query = payload.get("query", "")
    top_k = payload.get("top_k", 3)
    memories = await hindsight.recall_hybrid(query, top_k=top_k)
    return {"memories": memories, "count": len(memories)}


@app.get("/memory/stats")
def memory_stats():
    store_count = len(hindsight._mock_store) if hindsight._mock_mode else "live"
    return {
        "mode": hindsight.mode if not hindsight._mock_mode else "mock",
        "stored_memories": store_count,
        "bank_id": hindsight.bank_id if hindsight._use_bank_api else None,
        "pipeline_id": hindsight.pipeline_id if hindsight._use_pipeline_api else None,
    }


@app.get("/costs/summary")
def cost_summary():
    summary = cascade.get_session_summary()
    summary["moe"] = cascade.get_moe_summary()
    return summary


@app.get("/costs/audit")
def full_audit_log():
    return {
        "audit_log": cascade.audit_log,
        "total_entries": len(cascade.audit_log),
        "session_spend": round(cascade.session_spend, 4),
    }


@app.get("/costs/incident/{incident_id}")
def incident_cost(incident_id: str):
    audit = cascade.get_incident_audit(incident_id)
    total = cascade.get_incident_cost(incident_id)
    return {"incident_id": incident_id, "total_cost_usd": round(total, 5), "calls": audit}


@app.get("/moe/stats")
def moe_stats():
    return cascade.get_moe_summary()


@app.get("/moe/experts")
def moe_experts():
    return {"experts": list_experts()}


@app.post("/eval/run")
async def eval_run(payload: EvalRequest):
    result = await run_eval(runs=payload.runs, incident_ids=payload.incident_ids)
    return result


@app.get("/eval/results")
def eval_results():
    results = get_latest_results()
    if not results:
        return {"message": "No eval runs yet. POST /eval/run first."}
    return results


@app.get("/flywheel/trajectories")
def flywheel_trajectories():
    return get_trajectory_stats(limit=10)


@app.post("/demo/run-sequence")
async def run_demo_sequence():
    demo_ids = ["inc_001", "inc_006", "inc_011", "inc_001", "inc_006"]
    results = []

    for i, sid in enumerate(demo_ids):
        incident = next(i for i in SYNTHETIC_INCIDENTS if i["id"] == sid)
        incident = {
            **incident,
            "id": f"demo_{i+1}_{str(uuid.uuid4())[:6]}",
            "source_id": sid,
            "timestamp": time.time(),
            "status": "diagnosing",
        }
        incidents_db[incident["id"]] = incident
        result = await run_agent_pipeline(incident)
        incidents_db[incident["id"]]["status"] = "resolved"
        incidents_db[incident["id"]]["result"] = result
        results_db[incident["id"]] = result
        results.append({
            "sequence": i + 1,
            "incident_id": incident["id"],
            "cost_usd": result["routing"]["cost_usd"],
            "memories_recalled": result["diagnosis"].get("memories_recalled", 0),
            "model_used": result["routing"]["model_used"],
            "latency_ms": result["total_time_ms"],
            "expert_used": result["moe"]["activated_expert"],
            "llm_skipped": result["moe"]["llm_skipped"],
            "difficulty": result["difficulty"]["level"],
        })

    return {
        "sequence_results": results,
        "session_summary": cascade.get_session_summary(),
        "moe_stats": cascade.get_moe_summary(),
        "story": "DECA-IR: memory fast path + MoE experts reduce cost on repeat incidents.",
    }
