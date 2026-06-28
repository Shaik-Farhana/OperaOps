"""
difficulty_classifier.py
Thinking-budget difficulty classification for OperaOps DECA-IR.
"""

from dataclasses import dataclass
from typing import Literal

DifficultyLevel = Literal["trivial", "easy", "medium", "hard", "critical"]


@dataclass
class DifficultyResult:
    level: DifficultyLevel
    thinking_on: bool
    max_tokens: int
    reason: str


def classify_difficulty(
    severity: str,
    memory_confidence: float,
    trace_length: int,
    expert_score_margin: float,
    llm_skipped: bool = False,
) -> DifficultyResult:
    """
    Map incident signals to difficulty tier and thinking budget.
    trivial is returned when fast path already handled the incident.
    """
    if llm_skipped:
        return DifficultyResult(
            level="trivial",
            thinking_on=False,
            max_tokens=0,
            reason="Memory fast path — no LLM required",
        )

    long_trace = trace_length > 800
    low_margin = expert_score_margin < 0.15
    novel = memory_confidence < 0.5

    if severity == "P1" and novel and long_trace:
        return DifficultyResult(
            level="critical",
            thinking_on=True,
            max_tokens=2048,
            reason="P1 novel incident with long stack trace",
        )

    if severity == "P1" and novel:
        return DifficultyResult(
            level="hard",
            thinking_on=True,
            max_tokens=1024,
            reason="P1 novel incident — deep reasoning required",
        )

    if severity == "P1" and memory_confidence >= 0.6:
        return DifficultyResult(
            level="medium",
            thinking_on=False,
            max_tokens=768,
            reason="P1 with partial memory context",
        )

    if severity in ("P2", "P3") and memory_confidence >= 0.6:
        return DifficultyResult(
            level="easy",
            thinking_on=False,
            max_tokens=512,
            reason="P2/P3 with memory match",
        )

    if long_trace or low_margin:
        return DifficultyResult(
            level="medium",
            thinking_on=False,
            max_tokens=512,
            reason="Long trace or ambiguous expert routing",
        )

    if severity == "P3":
        return DifficultyResult(
            level="easy",
            thinking_on=False,
            max_tokens=256,
            reason="P3 low severity",
        )

    return DifficultyResult(
        level="medium",
        thinking_on=False,
        max_tokens=512,
        reason="Default medium difficulty",
    )
