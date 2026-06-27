"""
main.py
OperaOps FastAPI backend — incident response agent API
"""

import os
import json
import uuid
import time
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from agent import run_agent_pipeline
from cascade_router import cascade
from hindsight_client import hindsight

load_dotenv()

app = FastAPI(
    title="OperaOps API",
    description="AI incident response agent with persistent memory and runtime intelligence",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:5173"), "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory incident store (replace with Supabase in production)
incidents_db: dict[str, dict] = {}
results_db: dict[str, dict] = {}

# Load synthetic incidents from JSON
SYNTHETIC_INCIDENTS_PATH = Path(__file__).parent.parent / "data" / "incidents.json"
with open(SYNTHETIC_INCIDENTS_PATH) as f:
    SYNTHETIC_INCIDENTS = json.load(f)


# ── Pydantic Models ───────────────────────────────────────────────────────────

class IncidentCreate(BaseModel):
    title: str
    service: str
    severity: str  # P1, P2, P3
    error_message: str
    stack_trace: Optional[str] = ""
    category: Optional[str] = "unknown"


class IncidentTrigger(BaseModel):
    synthetic_id: Optional[str] = None  # use a preset synthetic incident
    custom: Optional[IncidentCreate] = None  # or provide custom incident


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "OperaOps",
        "hindsight_mode": "mock" if hindsight._mock_mode else "live",
        "cascadeflow": "active",
    }


# ── Incidents ─────────────────────────────────────────────────────────────────

@app.get("/incidents/synthetic")
def list_synthetic():
    """Return all available synthetic incidents for the demo."""
    return SYNTHETIC_INCIDENTS


@app.post("/incidents/trigger")
async def trigger_incident(payload: IncidentTrigger):
    """
    Trigger an incident through the full agent pipeline.
    Uses either a synthetic incident by ID or a custom payload.
    """
    # Resolve incident data
    if payload.synthetic_id:
        incident = next(
            (i for i in SYNTHETIC_INCIDENTS if i["id"] == payload.synthetic_id), None
        )
        if not incident:
            raise HTTPException(status_code=404, detail=f"Synthetic incident {payload.synthetic_id} not found")
        # Give it a fresh ID for this run
        incident = {**incident, "id": f"run_{str(uuid.uuid4())[:8]}", "source_id": payload.synthetic_id}
    elif payload.custom:
        incident = {
            "id": f"run_{str(uuid.uuid4())[:8]}",
            **payload.custom.model_dump(),
        }
    else:
        raise HTTPException(status_code=400, detail="Provide either synthetic_id or custom incident")

    incident["timestamp"] = time.time()
    incident["status"] = "diagnosing"
    incidents_db[incident["id"]] = incident

    # Run agent pipeline
    result = await run_agent_pipeline(incident)

    # Update incident status
    incidents_db[incident["id"]]["status"] = "resolved"
    incidents_db[incident["id"]]["result"] = result
    results_db[incident["id"]] = result

    return {
        "incident": incidents_db[incident["id"]],
        "result": result,
    }


@app.get("/incidents")
def list_incidents():
    """List all incidents processed in this session."""
    return list(incidents_db.values())


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str):
    """Get a specific incident with its full agent result."""
    if incident_id not in incidents_db:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {
        "incident": incidents_db[incident_id],
        "result": results_db.get(incident_id),
    }


# ── Memory (Hindsight) ────────────────────────────────────────────────────────

@app.post("/memory/recall")
async def recall_memory(payload: dict):
    """Query Hindsight for past similar incidents."""
    query = payload.get("query", "")
    top_k = payload.get("top_k", 3)
    memories = await hindsight.recall(query, top_k=top_k)
    return {"memories": memories, "count": len(memories)}


@app.get("/memory/stats")
def memory_stats():
    """Return memory stats for the UI."""
    store_count = len(hindsight._mock_store) if hindsight._mock_mode else "live"
    return {
        "mode": "mock" if hindsight._mock_mode else "live",
        "stored_memories": store_count,
        "pipeline_id": hindsight.pipeline_id,
    }


# ── Cost / Audit (cascadeflow) ────────────────────────────────────────────────

@app.get("/costs/summary")
def cost_summary():
    """Return session-level cost summary from cascadeflow audit trail."""
    return cascade.get_session_summary()


@app.get("/costs/audit")
def full_audit_log():
    """Return the full cascadeflow audit trail for all incidents."""
    return {
        "audit_log": cascade.audit_log,
        "total_entries": len(cascade.audit_log),
        "session_spend": round(cascade.session_spend, 4),
    }


@app.get("/costs/incident/{incident_id}")
def incident_cost(incident_id: str):
    """Return cost breakdown for a specific incident."""
    audit = cascade.get_incident_audit(incident_id)
    total = cascade.get_incident_cost(incident_id)
    return {
        "incident_id": incident_id,
        "total_cost_usd": round(total, 5),
        "calls": audit,
    }


# ── Demo helper ───────────────────────────────────────────────────────────────

@app.post("/demo/run-sequence")
async def run_demo_sequence():
    """
    Run 5 incidents in sequence to demonstrate the memory learning curve.
    Incident 1 = no memory, Incident 5 = fully informed by past context.
    Uses DB timeout incidents to show the clear before/after delta.
    """
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
            "memories_recalled": result["diagnosis"]["memories_recalled"],
            "model_used": result["routing"]["model_used"],
            "latency_ms": result["routing"]["latency_ms"],
        })

    return {
        "sequence_results": results,
        "session_summary": cascade.get_session_summary(),
        "story": "Incident #1 had no memory. By incident #5, OperaOps recalled past fixes and routed to a cheaper model.",
    }
