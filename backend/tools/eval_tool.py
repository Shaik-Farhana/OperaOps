"""Compare diagnosis fix to known ground truth."""

import re


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def compare_to_known_fix(diagnosis: dict, known_fix: str | None) -> dict:
    if not known_fix:
        return {"score": None, "matched": None, "message": "No ground truth available"}

    fix = diagnosis.get("fix", "")
    a = _tokenize(fix)
    b = _tokenize(known_fix)
    if not a or not b:
        return {"score": 0.0, "matched": False, "message": "Empty fix text"}

    jaccard = len(a & b) / len(a | b)
    return {
        "score": round(jaccard, 3),
        "matched": jaccard >= 0.25,
        "message": f"Fix match score: {jaccard:.0%}",
    }
