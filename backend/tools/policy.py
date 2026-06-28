"""Escalation policy checks."""


def escalation_check(diagnosis: dict, severity: str, memory_confidence: float) -> dict:
    escalate = diagnosis.get("escalate_to_human", False)
    issues = []

    if severity == "P1" and memory_confidence < 0.5 and not escalate:
        issues.append("P1 novel incident should escalate to human")
    if severity == "P1" and diagnosis.get("confidence", 0) < 0.6 and not escalate:
        issues.append("Low confidence on P1 — recommend escalation")
    if escalate and not diagnosis.get("escalation_reason"):
        issues.append("escalate_to_human=true but no escalation_reason provided")

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "should_escalate": severity == "P1" and memory_confidence < 0.5,
    }
