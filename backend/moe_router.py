"""
moe_router.py
Application-level Latent MoE router for OperaOps DECA-IR.
Domain experts, Mamba-style trace compression, memory fast path.
"""

import os
import math
import re
from dataclasses import dataclass, field
from typing import Optional
import env_loader  # noqa: F401 — loads .env.local from project root

MEMORY_BYPASS_THRESHOLD = float(os.getenv("MOE_MEMORY_BYPASS_THRESHOLD", "0.85"))
MAMBA_THRESHOLD = int(os.getenv("MOE_MAMBA_THRESHOLD", "800"))
MAMBA_CHUNK_SIZE = int(os.getenv("MOE_MAMBA_CHUNK_SIZE", "400"))
VERIFY_ON_P1 = os.getenv("MOE_VERIFY_ON_P1", "false").lower() == "true"

# Category → expert mapping
CATEGORY_EXPERT = {
    "database": "db_expert",
    "memory": "mem_expert",
    "deployment": "deploy_expert",
    "api": "api_expert",
    "infrastructure": "infra_expert",
}

EXPERTS = {
    "db_expert": {
        "id": "db_expert",
        "domain": "database",
        "keywords": [
            "postgres", "sql", "connection", "pool", "replication", "database",
            "fatal", "remaining connection slots", "replica", "lsn",
        ],
        "system_prompt_suffix": (
            "You specialize in database incidents: connection pools, replication lag, "
            "query timeouts, and PostgreSQL/MySQL configuration. Focus on pool sizing, "
            "max_connections, and replica catch-up strategies."
        ),
        "thinking_budget": 768,
        "preferred_tier": "balanced",
    },
    "mem_expert": {
        "id": "mem_expert",
        "domain": "memory",
        "keywords": ["oom", "heap", "leak", "memory", "rss", "container", "limit", "oomkilled"],
        "system_prompt_suffix": (
            "You specialize in memory incidents: OOM kills, heap leaks, container limits, "
            "and JVM/Python memory profiling. Recommend immediate mitigation and root-cause patches."
        ),
        "thinking_budget": 512,
        "preferred_tier": "nano",
    },
    "deploy_expert": {
        "id": "deploy_expert",
        "domain": "deployment",
        "keywords": [
            "crashloop", "imagepull", "rollout", "kubernetes", "k8s", "deployment",
            "pod", "container", "kubelet", "image",
        ],
        "system_prompt_suffix": (
            "You specialize in deployment incidents: CrashLoopBackOff, ImagePullBackOff, "
            "failed rollouts, missing env vars, and kubectl recovery steps."
        ),
        "thinking_budget": 512,
        "preferred_tier": "balanced",
    },
    "api_expert": {
        "id": "api_expert",
        "domain": "api",
        "keywords": ["rate limit", "timeout", "5xx", "stripe", "api", "gateway", "429", "502", "503"],
        "system_prompt_suffix": (
            "You specialize in API incidents: rate limits, timeouts, retry/backoff, "
            "circuit breakers, and third-party integration failures."
        ),
        "thinking_budget": 512,
        "preferred_tier": "nano",
    },
    "infra_expert": {
        "id": "infra_expert",
        "domain": "infrastructure",
        "keywords": ["ssl", "cert", "certificate", "dns", "network", "nginx", "expired", "tls"],
        "system_prompt_suffix": (
            "You specialize in infrastructure incidents: SSL/TLS certificates, DNS, "
            "load balancers, and network connectivity. Include cert renewal commands."
        ),
        "thinking_budget": 512,
        "preferred_tier": "balanced",
    },
    "general_expert": {
        "id": "general_expert",
        "domain": "general",
        "keywords": [],
        "system_prompt_suffix": (
            "You are a general incident response expert. Apply systematic root-cause analysis "
            "across any domain."
        ),
        "thinking_budget": 1024,
        "preferred_tier": "balanced",
    },
}

# Session-level expert activation tracking
_expert_activations: dict[str, int] = {}
_fast_path_hits = 0
_tokens_saved_estimate = 0


@dataclass
class MoERouteResult:
    activated_expert: str
    expert_scores: dict[str, float]
    expert_config: dict
    compressed_trace: str
    context_path: str  # "full" | "mamba_compressed"
    tokens_saved_estimate: int
    fast_path_diagnosis: Optional[dict] = None
    llm_skipped: bool = False
    memory_confidence: float = 0.0
    recalled_ids: list = field(default_factory=list)
    expert_score_margin: float = 0.0


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def _keyword_overlap(text: str, keywords: list[str]) -> float:
    if not keywords:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw in text_lower)
    return hits / len(keywords)


def _normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    total = sum(scores.values())
    if total <= 0:
        n = len(scores)
        return {k: 1.0 / n for k in scores}
    return {k: v / total for k, v in scores.items()}


def _encode_latent(incident: dict, memory_confidence: float) -> dict[str, float]:
    """Build feature vector for latent MoE scoring."""
    error = incident.get("error_message", "")
    trace = incident.get("stack_trace", "")
    category = incident.get("category", "unknown")
    combined = f"{error} {trace} {incident.get('title', '')}"

    features = {}
    for expert_id, cfg in EXPERTS.items():
        if expert_id == "general_expert":
            features[expert_id] = 0.1
        elif category == cfg["domain"]:
            features[expert_id] = 0.9
        else:
            features[expert_id] = _keyword_overlap(combined, cfg["keywords"])

    # Severity boost for strong-tier experts on P1
    if incident.get("severity") == "P1":
        for eid in ("db_expert", "deploy_expert", "infra_expert"):
            features[eid] = features.get(eid, 0) + 0.15

    features["general_expert"] += max(0, 0.3 - memory_confidence)
    return _normalize_scores(features)


def score_experts(incident: dict, memory_confidence: float) -> tuple[str, dict[str, float], float]:
    """Latent MoE k=1: return activated expert, all scores, margin."""
    scores = _encode_latent(incident, memory_confidence)
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    activated = sorted_scores[0][0]
    margin = sorted_scores[0][1] - (sorted_scores[1][1] if len(sorted_scores) > 1 else 0)
    _expert_activations[activated] = _expert_activations.get(activated, 0) + 1
    return activated, scores, margin


def mamba_compress_trace(stack_trace: str) -> tuple[str, str, int]:
    """
    O(n) chunk-and-select compression for long stack traces.
    Returns (compressed_text, context_path, tokens_saved_estimate).
    """
    if not stack_trace or len(stack_trace) <= MAMBA_THRESHOLD:
        return stack_trace or "Not available", "full", 0

    chunks = []
    for i in range(0, len(stack_trace), MAMBA_CHUNK_SIZE):
        chunks.append(stack_trace[i : i + MAMBA_CHUNK_SIZE])

    if len(chunks) <= 3:
        return stack_trace, "full", 0

    error_keywords = {
        "error", "fatal", "exception", "failed", "at ", "warning", "oom",
        "backoff", "timeout", "connection", "killed",
    }

    def chunk_score(idx: int, chunk: str) -> float:
        lower = chunk.lower()
        kw_hits = sum(1 for kw in error_keywords if kw in lower)
        line_hits = chunk.count("\n")
        return kw_hits * 2 + line_hits * 0.5 + (0.5 if idx == 0 else 0) + (0.5 if idx == len(chunks) - 1 else 0)

    scored = [(i, c, chunk_score(i, c)) for i, c in enumerate(chunks)]
    scored.sort(key=lambda x: x[2], reverse=True)

    selected_indices = {0, len(chunks) - 1}
    for i, _, _ in scored[:2]:
        selected_indices.add(i)

    selected = [chunks[i] for i in sorted(selected_indices)]
    compressed = (
        f"Stack trace compressed: {len(chunks)} segments → {len(selected)} relevant segments\n"
        + "\n---\n".join(selected)
    )
    original_tokens = len(stack_trace.split())
    compressed_tokens = len(compressed.split())
    saved = max(0, original_tokens - compressed_tokens)
    return compressed, "mamba_compressed", saved


def _parse_memory_fields(content: str) -> dict:
    """Extract root cause and fix from stored memory content."""
    root_cause = ""
    fix = ""
    resolution_time = 15

    if "Root cause:" in content:
        part = content.split("Root cause:")[1]
        root_cause = part.split("|")[0].strip() if "|" in part else part.strip()[:200]
    if "Fix:" in content:
        part = content.split("Fix:")[1]
        fix = part.split("|")[0].strip() if "|" in part else part.strip()[:400]
    if "Resolution time:" in content:
        try:
            resolution_time = int(re.search(r"Resolution time:\s*(\d+)", content).group(1))
        except (AttributeError, ValueError):
            pass

    return {"root_cause": root_cause, "fix": fix, "resolution_time": resolution_time}


def _memory_confidence_from_recall(recalled_memories: list[dict]) -> float:
    if not recalled_memories:
        return 0.0
    scores = []
    for mem in recalled_memories:
        raw = mem.get("_score", 0)
        if raw > 1:
            normalized = min(raw / 10.0, 0.95)
        else:
            normalized = min(float(raw), 0.95)
        scores.append(normalized)
    return max(scores) if scores else 0.0


def try_fast_path(
    incident: dict,
    recalled_memories: list[dict],
    memory_confidence: float,
    recalled_ids: list,
) -> Optional[dict]:
    """Return diagnosis dict if memory fast path applies, else None."""
    global _fast_path_hits

    if memory_confidence < MEMORY_BYPASS_THRESHOLD or not recalled_memories:
        return None

    best = recalled_memories[0]
    parsed = _parse_memory_fields(best.get("content", ""))
    if not parsed["root_cause"] or not parsed["fix"]:
        return None

    severity = incident.get("severity", "P2")
    if severity == "P1" and VERIFY_ON_P1 and memory_confidence < 0.92:
        return None

    _fast_path_hits += 1
    return {
        "root_cause": parsed["root_cause"],
        "confidence": min(memory_confidence, 0.95),
        "fix": parsed["fix"],
        "estimated_resolution_minutes": parsed["resolution_time"],
        "escalate_to_human": severity == "P1" and memory_confidence < 0.90,
        "escalation_reason": "P1 with partial memory match — human verification recommended" if severity == "P1" else None,
        "rca_summary": (
            f"Resolved using recalled incident pattern. Root cause: {parsed['root_cause'][:150]}. "
            f"Applied known fix from Hindsight memory."
        ),
        "recalled_incidents": recalled_ids,
        "memory_informed": True,
        "memories_recalled": len(recalled_memories),
        "fast_path": True,
    }


def route_incident(
    incident: dict,
    recalled_memories: list[dict],
    recalled_ids: Optional[list] = None,
) -> MoERouteResult:
    """Full MoE routing: expert selection, compression, fast path check."""
    global _tokens_saved_estimate

    memory_confidence = _memory_confidence_from_recall(recalled_memories)
    ids = recalled_ids or [
        m.get("metadata", {}).get("incident_id", f"past_{i}")
        for i, m in enumerate(recalled_memories)
    ]

    activated, scores, margin = score_experts(incident, memory_confidence)
    expert_config = EXPERTS[activated]

    trace = incident.get("stack_trace", "")
    compressed, context_path, saved = mamba_compress_trace(trace)
    _tokens_saved_estimate += saved

    fast_diag = try_fast_path(incident, recalled_memories, memory_confidence, ids)

    return MoERouteResult(
        activated_expert=activated,
        expert_scores=scores,
        expert_config=expert_config,
        compressed_trace=compressed,
        context_path=context_path,
        tokens_saved_estimate=saved,
        fast_path_diagnosis=fast_diag,
        llm_skipped=fast_diag is not None,
        memory_confidence=memory_confidence,
        recalled_ids=ids,
        expert_score_margin=margin,
    )


def get_moe_stats() -> dict:
    """Session MoE statistics for API."""
    total = sum(_expert_activations.values()) or 1
    distribution = {
        k: round(v / total * 100, 1) for k, v in _expert_activations.items()
    }
    collapsed = [k for k, pct in distribution.items() if pct > 60]
    return {
        "expert_activations": dict(_expert_activations),
        "expert_distribution_pct": distribution,
        "fast_path_hits": _fast_path_hits,
        "tokens_saved_estimate": _tokens_saved_estimate,
        "load_balance_warnings": collapsed,
        "routing_mode": "hybrid_moe",
    }


def list_experts() -> list[dict]:
    """Return expert configs for API (without internal weights)."""
    return [
        {
            "id": cfg["id"],
            "domain": cfg["domain"],
            "thinking_budget": cfg["thinking_budget"],
            "preferred_tier": cfg["preferred_tier"],
        }
        for cfg in EXPERTS.values()
    ]
