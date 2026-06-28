"""
guardrails.py
Lightweight output guardrails for OperaOps (NeMo Guardrails stub).
"""

import re

DESTRUCTIVE_PATTERNS = [
    (r"\bdrop\s+database\b", "drop database"),
    (r"\brm\s+-rf\s+/", "rm -rf /"),
    (r"\bdelete\s+from\s+\w+\s*;", "delete without WHERE clause"),
    (r"\btruncate\s+table\b", "truncate table"),
    (r"\bformat\s+c:\b", "format system drive"),
]


def apply_guardrails(diagnosis: dict) -> dict:
    """
    Scan fix text for destructive patterns. Force escalation if blocked.
    Returns updated diagnosis with guardrail metadata.
    """
    fix = diagnosis.get("fix", "").lower()
    blocked = []

    for pattern, label in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, fix, re.IGNORECASE):
            if "where" not in fix and "delete from" in label:
                blocked.append(label)
            elif "delete from" not in label:
                blocked.append(label)

    result = dict(diagnosis)
    if blocked:
        result["escalate_to_human"] = True
        result["escalation_reason"] = (
            f"Guardrail blocked potentially destructive fix: {', '.join(blocked)}. "
            "Human review required."
        )
        result["guardrail_blocked"] = True
        result["guardrail_patterns"] = blocked
    else:
        result["guardrail_blocked"] = False
        result["guardrail_patterns"] = []

    return result
