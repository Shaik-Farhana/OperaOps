"""
agent.py
Core OperaOps incident response agent.
Orchestrates: Hindsight recall → cascadeflow routing → Groq LLM → Hindsight store
"""

import os
import time
import json
from groq import Groq
from dotenv import load_dotenv
from hindsight_client import hindsight
from cascade_router import cascade

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """You are OperaOps, an expert incident response agent for engineering teams.
You diagnose production incidents, suggest fixes, and write RCA drafts.

When given an incident, you:
1. Identify the most likely root cause based on the error and stack trace
2. Provide a specific, actionable fix (not generic advice)
3. Estimate time to resolution
4. Flag if human escalation is required
5. Write a concise RCA summary

Use any recalled past incidents to inform your diagnosis. If a similar incident was resolved before, reference it.

Always respond in this exact JSON format:
{
  "root_cause": "one clear sentence identifying the root cause",
  "confidence": 0.0-1.0,
  "fix": "specific step-by-step fix",
  "estimated_resolution_minutes": number,
  "escalate_to_human": boolean,
  "escalation_reason": "why (or null if not escalating)",
  "rca_summary": "2-3 sentence RCA suitable for a post-mortem",
  "recalled_incidents": ["inc_id1", "inc_id2"] or [],
  "memory_informed": boolean
}"""


async def run_agent_pipeline(incident: dict) -> dict:
    """
    Full agent pipeline for a single incident.
    Returns complete diagnosis with audit trail.
    """
    incident_id = incident["id"]
    start_time = time.time()
    pipeline_log = []

    # ── STEP 1: RECALL ────────────────────────────────────────────────────────
    recall_query = f"{incident['error_message']} {incident['service']} {incident.get('category', '')}"
    recalled_memories = await hindsight.recall(recall_query, top_k=3)

    has_memory = len(recalled_memories) > 0
    memory_confidence = 0.0

    recalled_context = ""
    recalled_ids = []

    if recalled_memories:
        # Build context string from recalled memories
        memory_parts = []
        for i, mem in enumerate(recalled_memories):
            content = mem.get("content", "")
            memory_confidence = max(memory_confidence, mem.get("_score", 0.5) / 10)
            recalled_ids.append(mem.get("metadata", {}).get("incident_id", f"past_{i}"))
            memory_parts.append(f"Past incident {i+1}: {content[:400]}")
        recalled_context = "\n".join(memory_parts)
        memory_confidence = min(memory_confidence, 0.95)

    pipeline_log.append({
        "step": "recall",
        "memories_found": len(recalled_memories),
        "memory_confidence": memory_confidence,
    })

    # ── STEP 2: ROUTE (cascadeflow) ───────────────────────────────────────────
    incident_budget_remaining = cascade.budget_usd - cascade.get_incident_cost(incident_id)
    model, routing_reason = cascade.select_model(
        incident_severity=incident["severity"],
        has_memory_match=has_memory,
        memory_confidence=memory_confidence,
        incident_budget_remaining=incident_budget_remaining,
    )

    pipeline_log.append({
        "step": "route",
        "model_selected": model,
        "routing_reason": routing_reason,
        "budget_remaining": round(incident_budget_remaining, 4),
    })

    # ── STEP 3: BUILD PROMPT ──────────────────────────────────────────────────
    memory_section = ""
    if recalled_context:
        memory_section = f"\n\nRECALLED PAST INCIDENTS (from Hindsight memory):\n{recalled_context}"

    user_prompt = f"""INCIDENT REPORT:
ID: {incident_id}
Title: {incident['title']}
Service: {incident['service']}
Severity: {incident['severity']}
Error: {incident['error_message']}
Stack Trace:
{incident.get('stack_trace', 'Not available')}
{memory_section}

Diagnose this incident and provide a resolution plan."""

    # ── STEP 4: LLM CALL (via Groq) ──────────────────────────────────────────
    llm_start = time.time()
    escalated = model == cascade.strong_model

    # Map cascadeflow model names to Groq model IDs
    groq_model_map = {
        "qwen/qwen3-32b": "qwen-qwq-32b",
        "openai/gpt-oss-120b": "llama-3.3-70b-versatile",  # Best available on Groq free tier
    }
    groq_model = groq_model_map.get(model, "qwen-qwq-32b")

    try:
        completion = groq_client.chat.completions.create(
            model=groq_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )
        raw_response = completion.choices[0].message.content
        diagnosis = json.loads(raw_response)

    except Exception as e:
        # Graceful fallback
        print(f"[Agent] LLM error: {e}")
        diagnosis = {
            "root_cause": f"Unable to diagnose automatically: {str(e)[:100]}",
            "confidence": 0.0,
            "fix": "Manual investigation required",
            "estimated_resolution_minutes": 30,
            "escalate_to_human": True,
            "escalation_reason": "LLM call failed",
            "rca_summary": "Automated diagnosis failed. Manual review needed.",
            "recalled_incidents": recalled_ids,
            "memory_informed": has_memory,
        }

    llm_latency = int((time.time() - llm_start) * 1000)

    # ── STEP 5: LOG TO cascadeflow AUDIT TRAIL ────────────────────────────────
    call_number = len(cascade.get_incident_audit(incident_id)) + 1
    estimated_tokens = len(user_prompt.split()) + len(str(diagnosis).split())
    cost = cascade.estimate_cost(model, estimated_tokens)

    audit_entry = cascade.log_decision(
        incident_id=incident_id,
        model_used=model,
        routing_reason=routing_reason,
        cost_usd=cost,
        latency_ms=llm_latency,
        escalated=escalated,
        call_number=call_number,
    )

    pipeline_log.append({
        "step": "llm_call",
        "model": groq_model,
        "latency_ms": llm_latency,
        "cost_usd": cost,
        "escalated": escalated,
    })

    # ── STEP 6: STORE IN HINDSIGHT ────────────────────────────────────────────
    memory_content = (
        f"Incident: {incident['title']} | Service: {incident['service']} | "
        f"Severity: {incident['severity']} | Category: {incident.get('category', 'unknown')} | "
        f"Error: {incident['error_message'][:200]} | "
        f"Root cause: {diagnosis.get('root_cause', '')} | "
        f"Fix: {diagnosis.get('fix', '')[:300]} | "
        f"Resolution time: {diagnosis.get('estimated_resolution_minutes', 0)} min"
    )

    await hindsight.store(
        incident_id=incident_id,
        content=memory_content,
        metadata={
            "severity": incident["severity"],
            "service": incident["service"],
            "category": incident.get("category", "unknown"),
            "confidence": diagnosis.get("confidence", 0),
        },
    )

    pipeline_log.append({"step": "store", "memory_stored": True})

    # ── STEP 7: CHECK FOR PATTERNS (reflect) ──────────────────────────────────
    pattern_insight = await hindsight.reflect(
        f"{incident.get('category', '')} incidents"
    )

    # ── COMPILE RESULT ────────────────────────────────────────────────────────
    total_time = int((time.time() - start_time) * 1000)

    return {
        "incident_id": incident_id,
        "diagnosis": {
            **diagnosis,
            "recalled_incidents": recalled_ids,
            "memory_informed": has_memory,
            "memories_recalled": len(recalled_memories),
        },
        "routing": {
            "model_used": model,
            "groq_model": groq_model,
            "routing_reason": routing_reason,
            "escalated": escalated,
            "cost_usd": cost,
            "latency_ms": llm_latency,
        },
        "audit_entry": audit_entry,
        "pattern_insight": pattern_insight,
        "pipeline_log": pipeline_log,
        "total_time_ms": total_time,
    }
