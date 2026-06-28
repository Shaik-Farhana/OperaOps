"""
smart_router.py
Multi-signal fusion router for OperaOps DECA-IR.
Combines MoE expert hints, difficulty, severity, memory, and budget.
"""

from dataclasses import dataclass
from typing import Literal

from difficulty_classifier import DifficultyResult

ModelTier = Literal["nano", "balanced", "strong"]

TIER_MODELS = {
    "nano": {
        "groq": "openai/gpt-oss-20b",
        "nim": "nvidia/nemotron-3-nano",
        "cascade_key": "cheap",
    },
    "balanced": {
        "groq": "llama-3.3-70b-versatile",
        "nim": "meta/llama-3.3-70b-instruct",
        "cascade_key": "cheap",
    },
    "strong": {
        "groq": "openai/gpt-oss-120b",
        "nim": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
        "cascade_key": "strong",
    },
}


@dataclass
class SmartRouteResult:
    model_tier: ModelTier
    groq_model_id: str
    nim_model_id: str
    cascade_model_key: str
    routing_reason: str
    max_tokens: int
    thinking_on: bool
    difficulty: str
    escalated: bool


def _tier_from_expert(preferred: str) -> ModelTier:
    mapping = {"nano": "nano", "balanced": "balanced", "strong": "strong"}
    return mapping.get(preferred, "balanced")


def _fuse_tier(
    expert_tier: ModelTier,
    difficulty: DifficultyResult,
    severity: str,
    memory_confidence: float,
    budget_pct: float,
    trace_length: int,
) -> tuple[ModelTier, str]:
    """Weighted fusion of routing signals."""
    reasons = []

    if budget_pct < 0.20:
        return "nano", "Budget below 20% — forced nano tier"

    tier_scores = {"nano": 0.0, "balanced": 0.0, "strong": 0.0}

    # Expert hint (0.25)
    tier_scores[expert_tier] += 0.25
    reasons.append(f"expert→{expert_tier}")

    # Severity (0.30)
    if severity == "P1":
        tier_scores["strong"] += 0.30
    elif severity == "P2":
        tier_scores["balanced"] += 0.30
    else:
        tier_scores["nano"] += 0.30

    # Memory confidence (0.25) — high memory → cheaper
    if memory_confidence >= 0.75:
        tier_scores["nano"] += 0.25
    elif memory_confidence >= 0.4:
        tier_scores["balanced"] += 0.25
    else:
        tier_scores["strong"] += 0.25

    # Trace length (0.05)
    if trace_length > 1500:
        tier_scores["strong"] += 0.05
    elif trace_length > 400:
        tier_scores["balanced"] += 0.05
    else:
        tier_scores["nano"] += 0.05

    # Difficulty override
    diff_map = {
        "critical": "strong",
        "hard": "strong",
        "medium": "balanced",
        "easy": "nano",
        "trivial": "nano",
    }
    diff_tier = diff_map.get(difficulty.level, "balanced")
    tier_scores[diff_tier] += 0.15
    reasons.append(f"difficulty→{difficulty.level}")

    winner = max(tier_scores, key=tier_scores.get)
    reason = f"Hybrid MoE fusion: {', '.join(reasons)} → {winner}"
    return winner, reason


def smart_route(
    expert_preferred_tier: str,
    expert_thinking_budget: int,
    difficulty: DifficultyResult,
    severity: str,
    memory_confidence: float,
    budget_remaining: float,
    total_budget: float,
    trace_length: int,
    force_strong: bool = False,
) -> SmartRouteResult:
    """Produce final model tier and token budget."""
    budget_pct = budget_remaining / total_budget if total_budget > 0 else 1.0
    expert_tier = _tier_from_expert(expert_preferred_tier)

    if force_strong:
        tier = "strong"
        reason = "Confidence escalation — retrying with strong tier"
    else:
        tier, reason = _fuse_tier(
            expert_tier, difficulty, severity, memory_confidence, budget_pct, trace_length
        )

    max_tokens = min(difficulty.max_tokens, expert_thinking_budget)
    if tier == "nano":
        max_tokens = min(max_tokens, 512)
    elif tier == "strong" and difficulty.thinking_on:
        max_tokens = max(max_tokens, 1024)

    models = TIER_MODELS[tier]
    return SmartRouteResult(
        model_tier=tier,
        groq_model_id=models["groq"],
        nim_model_id=models["nim"],
        cascade_model_key=models["cascade_key"],
        routing_reason=reason,
        max_tokens=max_tokens,
        thinking_on=difficulty.thinking_on and tier == "strong",
        difficulty=difficulty.level,
        escalated=tier == "strong",
    )
