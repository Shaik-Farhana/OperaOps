"""
rewards.py
RLVR reward function for future NeMo Gym training.
"""

import re


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def compute_rlvr_reward(diagnosis: dict, incident: dict, tokens_used: int = 0) -> float:
    reward = 0.0

    required = ["root_cause", "confidence", "fix", "estimated_resolution_minutes", "escalate_to_human", "rca_summary"]
    if all(k in diagnosis for k in required):
        reward += 0.30
    else:
        return -1.0

    known_fix = incident.get("known_fix")
    if known_fix:
        fix_words = _tokenize(diagnosis.get("fix", ""))
        known_words = _tokenize(known_fix)
        if fix_words and known_words:
            jaccard = len(fix_words & known_words) / len(fix_words | known_words)
            if jaccard >= 0.75:
                reward += 0.30
            elif jaccard >= 0.25:
                reward += 0.15

    severity = incident.get("severity", "P2")
    escalate = diagnosis.get("escalate_to_human", False)
    if severity == "P1" and diagnosis.get("confidence", 1) < 0.6 and escalate:
        reward += 0.20
    elif severity == "P1" and diagnosis.get("confidence", 1) < 0.6 and not escalate:
        reward -= 0.20
    elif severity in ("P2", "P3") and not escalate:
        reward += 0.10

    expected_time = incident.get("resolution_time_minutes")
    if expected_time:
        est = diagnosis.get("estimated_resolution_minutes", 0)
        if abs(est - expected_time) / max(expected_time, 1) <= 0.20:
            reward += 0.10

    if diagnosis.get("memory_informed"):
        reward += 0.10

    reward -= 0.01 * tokens_used
    return round(reward, 4)
