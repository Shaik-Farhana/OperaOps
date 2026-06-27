"""
cascade_router.py
cascadeflow integration for intelligent model routing and budget enforcement.
cascadeflow docs: https://docs.cascadeflow.ai/
cascadeflow GitHub: https://github.com/lemony-ai/cascadeflow
"""

import os
import time
import uuid
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Budget and model config
BUDGET_USD = float(os.getenv("CASCADE_BUDGET_USD", "5.00"))
CHEAP_MODEL = os.getenv("CASCADE_CHEAP_MODEL", "qwen/qwen3-32b")
STRONG_MODEL = os.getenv("CASCADE_STRONG_MODEL", "openai/gpt-oss-120b")

# Cost estimates per 1K tokens (approximate)
MODEL_COSTS = {
    CHEAP_MODEL: 0.0004,    # ~$0.0004/1K tokens
    STRONG_MODEL: 0.0040,   # ~$0.004/1K tokens
}


class CascadeRouter:
    """
    Runtime intelligence layer for OperaOps.
    Routes LLM calls to appropriate models based on task complexity,
    enforces per-incident budget, and maintains a full audit trail.
    """

    def __init__(self):
        self.budget_usd = BUDGET_USD
        self.cheap_model = CHEAP_MODEL
        self.strong_model = STRONG_MODEL
        self.audit_log: list[dict] = []
        self.session_spend = 0.0

        # Try to import cascadeflow — fall back to manual routing if unavailable
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
        """
        Decide which model to use for this incident.
        Returns (model_name, routing_reason).

        Routing logic:
        - P1 + no memory match → strong model (novel critical incident)
        - P1 + high confidence memory → cheap model (known pattern)
        - P2/P3 + any memory → cheap model
        - Budget < 20% remaining → cheap model regardless
        """
        budget_pct = incident_budget_remaining / self.budget_usd

        if budget_pct < 0.20:
            return self.cheap_model, "Budget below 20% — routing to efficient model"

        if incident_severity == "P1" and not has_memory_match:
            return self.strong_model, "P1 incident with no prior memory — escalating to strong model"

        if incident_severity == "P1" and memory_confidence > 0.75:
            return self.cheap_model, f"P1 but memory confidence {memory_confidence:.0%} — known pattern, cheap model sufficient"

        if incident_severity in ("P2", "P3") and has_memory_match:
            return self.cheap_model, "P2/P3 with memory match — cheap model sufficient"

        if incident_severity in ("P2", "P3") and not has_memory_match:
            return self.cheap_model, "P2/P3 novel — cheap model first, escalate if needed"

        return self.cheap_model, "Default routing — cheap model"

    def estimate_cost(self, model: str, estimated_tokens: int = 800) -> float:
        """Estimate cost for a model call."""
        cost_per_1k = MODEL_COSTS.get(model, 0.001)
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
    ) -> dict:
        """Log every model routing decision to the audit trail."""
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
        }
        self.audit_log.append(entry)
        self.session_spend += cost_usd
        return entry

    def get_incident_audit(self, incident_id: str) -> list[dict]:
        """Return all audit entries for a specific incident."""
        return [e for e in self.audit_log if e["incident_id"] == incident_id]

    def get_incident_cost(self, incident_id: str) -> float:
        """Return total cost for a specific incident."""
        return sum(e["cost_usd"] for e in self.get_incident_audit(incident_id))

    def get_session_summary(self) -> dict:
        """Return session-level cost and model usage summary."""
        if not self.audit_log:
            return {
                "total_spend": 0.0,
                "total_calls": 0,
                "cheap_calls": 0,
                "strong_calls": 0,
                "escalations": 0,
                "avg_cost_per_call": 0.0,
                "model_distribution": {},
            }

        cheap_calls = sum(1 for e in self.audit_log if e["model_used"] == self.cheap_model)
        strong_calls = sum(1 for e in self.audit_log if e["model_used"] == self.strong_model)
        escalations = sum(1 for e in self.audit_log if e["escalated"])

        return {
            "total_spend": round(self.session_spend, 4),
            "total_calls": len(self.audit_log),
            "cheap_calls": cheap_calls,
            "strong_calls": strong_calls,
            "escalations": escalations,
            "avg_cost_per_call": round(self.session_spend / len(self.audit_log), 5),
            "model_distribution": {
                "cheap_pct": round(cheap_calls / len(self.audit_log) * 100, 1),
                "strong_pct": round(strong_calls / len(self.audit_log) * 100, 1),
            },
        }


# Singleton instance
cascade = CascadeRouter()
