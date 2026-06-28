"""
agent.py
OperaOps DECA-IR incident response agent.
Parallel perceive → MoE route → ReAct loop → guardrails → store → flywheel.
"""

import asyncio
import time
import json
import env_loader  # noqa: F401 — loads .env.local from project root

from hindsight_client import hindsight
from cascade_router import cascade
from moe_router import route_incident
from difficulty_classifier import classify_difficulty
from smart_router import smart_route
import llm_client
from guardrails import apply_guardrails
from flywheel import log_trajectory
from tools.memory import recall_incidents, store_resolution
from tools.runbook import fetch_runbook
from tools.validator import validate_diagnosis
from tools.eval_tool import compare_to_known_fix
from tools.policy import escalation_check

BASE_SYSTEM_PROMPT = """You are OperaOps, an expert incident response agent for engineering teams.
You diagnose production incidents, suggest fixes, and write RCA drafts.

When given an incident, you:
1. Identify the most likely root cause based on the error and stack trace
2. Provide a specific, actionable fix (not generic advice)
3. Estimate time to resolution
4. Flag if human escalation is required
5. Write a concise RCA summary

Use any recalled past incidents and runbook steps to inform your diagnosis.

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

REACT_MAX_STEPS = 3
CONFIDENCE_ESCALATION_THRESHOLD = 0.6


def _build_memory_section(recalled_memories: list[dict]) -> str:
    if not recalled_memories:
        return ""
    parts = []
    for i, mem in enumerate(recalled_memories):
        parts.append(f"Past incident {i+1}: {mem.get('content', '')[:400]}")
    return "\n\nRECALLED PAST INCIDENTS (from Hindsight memory):\n" + "\n".join(parts)


def _build_user_prompt(incident: dict, incident_id: str, compressed_trace: str, memory_section: str, runbook_snippet: str) -> str:
    runbook_block = f"\n\nRUNBOOK ({incident.get('category', 'general')}):\n{runbook_snippet}" if runbook_snippet else ""
    return f"""INCIDENT REPORT:
ID: {incident_id}
Title: {incident['title']}
Service: {incident['service']}
Severity: {incident['severity']}
Category: {incident.get('category', 'unknown')}
Error: {incident['error_message']}
Stack Trace:
{compressed_trace}
{memory_section}{runbook_block}

Diagnose this incident and provide a resolution plan."""


async def run_agent_pipeline(incident: dict) -> dict:
    incident_id = incident["id"]
    start_time = time.time()
    pipeline_log = []
    react_log = []

    recall_query = f"{incident['error_message']} {incident['service']} {incident.get('category', '')}"

    # ── PARALLEL PERCEIVE ─────────────────────────────────────────────────────
    recall_task = recall_incidents(recall_query, top_k=3)
    runbook_task = asyncio.to_thread(fetch_runbook, incident.get("category", "unknown"))

    recall_result, runbook = await asyncio.gather(recall_task, runbook_task)

    recalled_memories = recall_result["memories"]
    recalled_ids = recall_result["ids"]
    has_memory = len(recalled_memories) > 0

    moe_result = route_incident(incident, recalled_memories, recalled_ids)

    pipeline_log.append({
        "step": "parallel_perceive",
        "memories_found": len(recalled_memories),
        "memory_confidence": moe_result.memory_confidence,
        "expert": moe_result.activated_expert,
        "context_path": moe_result.context_path,
    })

    trace_len = len(incident.get("stack_trace", ""))
    difficulty = classify_difficulty(
        severity=incident["severity"],
        memory_confidence=moe_result.memory_confidence,
        trace_length=trace_len,
        expert_score_margin=moe_result.expert_score_margin,
        llm_skipped=moe_result.llm_skipped,
    )

    budget_remaining = cascade.budget_usd - cascade.get_incident_cost(incident_id)

    # ── FAST PATH ─────────────────────────────────────────────────────────────
    if moe_result.llm_skipped and moe_result.fast_path_diagnosis:
        diagnosis = apply_guardrails(moe_result.fast_path_diagnosis)
        total_time = int((time.time() - start_time) * 1000)

        audit_entry = cascade.log_decision(
            incident_id=incident_id,
            model_used="memory_fast_path",
            routing_reason="Memory fast path — faithfulness >= threshold",
            cost_usd=0.0,
            latency_ms=total_time,
            escalated=False,
            call_number=1,
            expert_id=moe_result.activated_expert,
            routing_mode="deca_ir_fast_path",
            llm_skipped=True,
            difficulty=difficulty.level,
            provider="none",
            tokens_saved=moe_result.tokens_saved_estimate + 800,
        )

        await _finalize_store(incident, incident_id, diagnosis)
        fms = compare_to_known_fix(diagnosis, incident.get("known_fix"))

        await log_trajectory({
            "incident_id": incident_id,
            "input": {"title": incident["title"], "severity": incident["severity"]},
            "expert": moe_result.activated_expert,
            "difficulty": difficulty.level,
            "llm_skipped": True,
            "diagnosis": diagnosis,
            "cost_usd": 0.0,
            "latency_ms": total_time,
            "fms_score": fms.get("score"),
        })

        return _compile_result(
            incident_id, diagnosis, moe_result, difficulty, None,
            audit_entry, pipeline_log, react_log, total_time,
            cost=0.0, latency=total_time, llm_skipped=True,
        )

    # ── SMART ROUTE ───────────────────────────────────────────────────────────
    route = smart_route(
        expert_preferred_tier=moe_result.expert_config["preferred_tier"],
        expert_thinking_budget=moe_result.expert_config["thinking_budget"],
        difficulty=difficulty,
        severity=incident["severity"],
        memory_confidence=moe_result.memory_confidence,
        budget_remaining=budget_remaining,
        total_budget=cascade.budget_usd,
        trace_length=trace_len,
    )

    pipeline_log.append({
        "step": "smart_route",
        "tier": route.model_tier,
        "difficulty": route.difficulty,
        "max_tokens": route.max_tokens,
        "thinking_on": route.thinking_on,
    })

    system_prompt = BASE_SYSTEM_PROMPT + "\n\n" + moe_result.expert_config["system_prompt_suffix"]
    memory_section = _build_memory_section(recalled_memories)
    user_prompt = _build_user_prompt(
        incident, incident_id, moe_result.compressed_trace,
        memory_section, runbook.get("snippet", ""),
    )

    # ── REACT LOOP ────────────────────────────────────────────────────────────
    diagnosis = {}
    llm_result = None
    total_cost = 0.0
    total_llm_latency = 0
    escalated_once = False

    for step in range(REACT_MAX_STEPS):
        force_strong = escalated_once and step > 0
        if force_strong:
            route = smart_route(
                expert_preferred_tier="strong",
                expert_thinking_budget=1024,
                difficulty=difficulty,
                severity=incident["severity"],
                memory_confidence=moe_result.memory_confidence,
                budget_remaining=budget_remaining - total_cost,
                total_budget=cascade.budget_usd,
                trace_length=trace_len,
                force_strong=True,
            )

        react_log.append({"step": step + 1, "action": "llm_diagnose", "tier": route.model_tier})

        llm_result = llm_client.complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            tier=route.model_tier,
            groq_model=route.groq_model_id,
            nim_model=route.nim_model_id,
            max_tokens=route.max_tokens,
            thinking_on=route.thinking_on,
        )

        diagnosis = llm_result.diagnosis
        diagnosis["recalled_incidents"] = recalled_ids
        diagnosis["memory_informed"] = has_memory
        diagnosis["memories_recalled"] = len(recalled_memories)

        est_tokens = llm_result.prompt_tokens + llm_result.completion_tokens or 800
        call_cost = cascade.estimate_cost(route.model_tier, est_tokens)
        total_cost += call_cost
        total_llm_latency += llm_result.latency_ms

        cascade.log_decision(
            incident_id=incident_id,
            model_used=route.model_tier,
            routing_reason=route.routing_reason,
            cost_usd=call_cost,
            latency_ms=llm_result.latency_ms,
            escalated=route.escalated,
            call_number=step + 1,
            expert_id=moe_result.activated_expert,
            routing_mode="deca_ir_react",
            difficulty=route.difficulty,
            provider=llm_result.provider,
            tokens_saved=moe_result.tokens_saved_estimate,
        )

        validation = validate_diagnosis(diagnosis)
        react_log.append({"step": step + 1, "action": "validate_diagnosis", "valid": validation["valid"]})

        if not validation["valid"]:
            user_prompt += "\n\nYour previous response failed JSON validation. Fix the schema and respond again."
            continue

        confidence = diagnosis.get("confidence", 0)
        if confidence < CONFIDENCE_ESCALATION_THRESHOLD and not escalated_once and step < REACT_MAX_STEPS - 1:
            escalated_once = True
            react_log.append({"step": step + 1, "action": "escalate_tier", "reason": f"confidence {confidence} < {CONFIDENCE_ESCALATION_THRESHOLD}"})
            continue

        policy = escalation_check(diagnosis, incident["severity"], moe_result.memory_confidence)
        react_log.append({"step": step + 1, "action": "escalation_check", "passed": policy["passed"]})
        break

    diagnosis = apply_guardrails(diagnosis)
    faithfulness = hindsight.compute_faithfulness(diagnosis, recalled_memories)
    fms = compare_to_known_fix(diagnosis, incident.get("known_fix"))

    await _finalize_store(incident, incident_id, diagnosis)
    pattern_insight = await hindsight.reflect(f"{incident.get('category', '')} incidents")

    total_time = int((time.time() - start_time) * 1000)

    await log_trajectory({
        "incident_id": incident_id,
        "input": {"title": incident["title"], "severity": incident["severity"]},
        "expert": moe_result.activated_expert,
        "difficulty": difficulty.level,
        "routing": {"tier": route.model_tier, "provider": llm_result.provider if llm_result else None},
        "diagnosis": diagnosis,
        "tools_called": [r["action"] for r in react_log],
        "cost_usd": total_cost,
        "latency_ms": total_time,
        "fms_score": fms.get("score"),
        "faithfulness": faithfulness,
    })

    last_audit = cascade.get_incident_audit(incident_id)[-1] if cascade.get_incident_audit(incident_id) else {}

    return _compile_result(
        incident_id, diagnosis, moe_result, difficulty, route,
        last_audit, pipeline_log, react_log, total_time,
        cost=total_cost, latency=total_llm_latency, llm_skipped=False,
        llm_result=llm_result, faithfulness=faithfulness, fms=fms,
        pattern_insight=pattern_insight,
    )


async def _finalize_store(incident: dict, incident_id: str, diagnosis: dict):
    memory_content = (
        f"Incident: {incident['title']} | Service: {incident['service']} | "
        f"Severity: {incident['severity']} | Category: {incident.get('category', 'unknown')} | "
        f"Error: {incident['error_message'][:200]} | "
        f"Root cause: {diagnosis.get('root_cause', '')} | "
        f"Fix: {diagnosis.get('fix', '')[:300]} | "
        f"Resolution time: {diagnosis.get('estimated_resolution_minutes', 0)} min"
    )
    await store_resolution(
        incident_id=incident_id,
        content=memory_content,
        metadata={
            "severity": incident["severity"],
            "service": incident["service"],
            "category": incident.get("category", "unknown"),
            "confidence": diagnosis.get("confidence", 0),
        },
    )


def _compile_result(
    incident_id, diagnosis, moe_result, difficulty, route,
    audit_entry, pipeline_log, react_log, total_time,
    cost, latency, llm_skipped, llm_result=None, faithfulness=0.0,
    fms=None, pattern_insight=None,
):
    return {
        "incident_id": incident_id,
        "diagnosis": diagnosis,
        "moe": {
            "activated_expert": moe_result.activated_expert,
            "expert_scores": moe_result.expert_scores,
            "routing_mode": "deca_ir",
            "context_path": moe_result.context_path,
            "llm_skipped": llm_skipped,
            "tokens_saved_estimate": moe_result.tokens_saved_estimate,
            "memory_confidence": moe_result.memory_confidence,
        },
        "difficulty": {
            "level": difficulty.level,
            "thinking_on": difficulty.thinking_on,
            "max_tokens": difficulty.max_tokens,
            "reason": difficulty.reason,
        },
        "routing": {
            "model_used": route.model_tier if route else "memory_fast_path",
            "groq_model": route.groq_model_id if route else None,
            "nim_model": route.nim_model_id if route else None,
            "routing_reason": route.routing_reason if route else "memory fast path",
            "escalated": route.escalated if route else False,
            "cost_usd": cost,
            "latency_ms": latency,
            "provider": llm_result.provider if llm_result else "none",
            "thinking_on": route.thinking_on if route else False,
        },
        "react_log": react_log,
        "eval": {
            "faithfulness": faithfulness,
            "fix_match_score": fms.get("score") if fms else None,
        },
        "audit_entry": audit_entry,
        "pattern_insight": pattern_insight,
        "pipeline_log": pipeline_log,
        "total_time_ms": total_time,
    }
