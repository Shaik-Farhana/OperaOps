"""
cascade_router.py
cascadeflow integration for intelligent model routing and budget enforcement.
"""

import os
import time
import uuid
from typing import Optional
import env_loader  # noqa: F401 — loads .env.local from project root

BUDGET_USD = float(os.getenv("CASCADE_BUDGET_USD", "5.00"))
CHEAP_MODEL = os.getenv("CASCADE_CHEAP_MODEL", "openai/gpt-oss-20b")
STRONG_MODEL = os.getenv("CASCADE_STRONG_MODEL", "openai/gpt-oss-120b")

MODEL_COSTS = {
    CHEAP_MODEL: 0.0004,
    STRONG_MODEL: 0.0040,
    "nano": 0.0003,
    "balanced": 0.0015,
    "strong": 0.0040,
}

_fast_path_audit_count = 0
_tokens_saved_session = 0


class CascadeRouter:
    def __init__(self):
        self.budget_usd = BUDGET_USD
        self.cheap_model = CHEAP_MODEL
        self.strong_model = STRONG_MODEL
        self.audit_log: list[dict] = []
        self.session_spend = 0.0

        try:
            import cascadeflow as cf
            self._cf = cf
            self._has_cascadeflow = True
            print("[cascadeflow] Library loaded successfully")
        except ImportError:
            self._has_cascadeflow = False
            print("[cascadeflow] Library not available — using manual routing logic")

    def select_model(
        self,
        incident_severity: str,
        has_memory_match: bool,
        memory_confidence: float,
        incident_budget_remaining: float,
    ) -> tuple[str, str]:
        budget_pct = incident_budget_remaining / self.budget_usd

        if budget_pct < 0.20:
            return self.cheap_model, "Budget below 20% — routing to efficient model"

        if incident_severity == "P1" and not has_memory_match:
            return self.strong_model, "P1 incident with no prior memory — escalating to strong model"

        if incident_severity == "P1" and memory_confidence > 0.75:
            return self.cheap_model, f"P1 but memory confidence {memory_confidence:.0%} — known pattern"

        if incident_severity in ("P2", "P3") and has_memory_match:
            return self.cheap_model, "P2/P3 with memory match — cheap model sufficient"

        if incident_severity in ("P2", "P3") and not has_memory_match:
            return self.cheap_model, "P2/P3 novel — cheap model first"

        return self.cheap_model, "Default routing — cheap model"

    def estimate_cost(self, model: str, estimated_tokens: int = 800) -> float:
        cost_per_1k = MODEL_COSTS.get(model, MODEL_COSTS.get("balanced", 0.001))
        return (estimated_tokens / 1000) * cost_per_1k

    def log_decision(
        self,
        incident_id: str,
        model_used: str,
        routing_reason: str,
        cost_usd: float,
        latency_ms: int,
        escalated: bool,
        call_number: int,
        expert_id: Optional[str] = None,
        routing_mode: str = "cascadeflow",
        llm_skipped: bool = False,
        difficulty: Optional[str] = None,
        provider: Optional[str] = None,
        tokens_saved: int = 0,
    ) -> dict:
        global _fast_path_audit_count, _tokens_saved_session

        if llm_skipped:
            _fast_path_audit_count += 1
        _tokens_saved_session += tokens_saved

        entry = {
            "id": str(uuid.uuid4())[:8],
            "incident_id": incident_id,
            "call_number": call_number,
            "model_used": model_used,
            "routing_reason": routing_reason,
            "cost_usd": round(cost_usd, 5),
            "latency_ms": latency_ms,
            "escalated": escalated,
            "timestamp": time.time(),
            "expert_id": expert_id,
            "routing_mode": routing_mode,
            "llm_skipped": llm_skipped,
            "difficulty": difficulty,
            "provider": provider,
            "tokens_saved": tokens_saved,
        }
        self.audit_log.append(entry)
        self.session_spend += cost_usd
        return entry

    def get_incident_audit(self, incident_id: str) -> list[dict]:
        return [e for e in self.audit_log if e["incident_id"] == incident_id]

    def get_incident_cost(self, incident_id: str) -> float:
        return sum(e["cost_usd"] for e in self.get_incident_audit(incident_id))

    def get_moe_summary(self) -> dict:
        from moe_router import get_moe_stats
        moe = get_moe_stats()
        return {
            **moe,
            "fast_path_audit_entries": _fast_path_audit_count,
            "session_tokens_saved": _tokens_saved_session,
        }

    def get_session_summary(self) -> dict:
        if not self.audit_log:
            return {
                "total_spend": 0.0,
                "total_calls": 0,
                "cheap_calls": 0,
                "strong_calls": 0,
                "escalations": 0,
                "fast_path_hits": _fast_path_audit_count,
                "avg_cost_per_call": 0.0,
                "model_distribution": {},
            }

        cheap_calls = sum(
            1 for e in self.audit_log
            if not e.get("escalated") and not e.get("llm_skipped")
        )
        strong_calls = sum(1 for e in self.audit_log if e.get("escalated"))
        escalations = strong_calls
        llm_calls = sum(1 for e in self.audit_log if not e.get("llm_skipped"))

        return {
            "total_spend": round(self.session_spend, 4),
            "total_calls": len(self.audit_log),
            "llm_calls": llm_calls,
            "cheap_calls": cheap_calls,
            "strong_calls": strong_calls,
            "escalations": escalations,
            "fast_path_hits": _fast_path_audit_count,
            "avg_cost_per_call": round(self.session_spend / max(llm_calls, 1), 5),
            "model_distribution": {
                "cheap_pct": round(cheap_calls / max(len(self.audit_log), 1) * 100, 1),
                "strong_pct": round(strong_calls / max(len(self.audit_log), 1) * 100, 1),
            },
        }


cascade = CascadeRouter()
