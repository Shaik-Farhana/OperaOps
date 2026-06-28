"""Diagnosis JSON schema validation."""

from pydantic import BaseModel, Field
from typing import Optional


class DiagnosisSchema(BaseModel):
    root_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    fix: str
    estimated_resolution_minutes: int = Field(ge=0)
    escalate_to_human: bool
    escalation_reason: Optional[str] = None
    rca_summary: str
    recalled_incidents: list = []
    memory_informed: bool = False


def validate_diagnosis(diagnosis: dict) -> dict:
    try:
        validated = DiagnosisSchema(**diagnosis)
        return {
            "valid": True,
            "errors": [],
            "diagnosis": validated.model_dump(),
        }
    except Exception as e:
        return {
            "valid": False,
            "errors": [str(e)],
            "diagnosis": diagnosis,
        }
