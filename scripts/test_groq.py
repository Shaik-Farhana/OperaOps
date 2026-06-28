"""Quick Groq connectivity test."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import llm_client
from smart_router import TIER_MODELS

USER = 'Return exactly: {"message":"groq ok","ok":true,"tier":"%s"}'


def _run(tier: str) -> llm_client.LLMResult:
    model = TIER_MODELS[tier]["groq"]
    return llm_client.complete(
        messages=[
            {"role": "system", "content": "Respond with JSON only."},
            {"role": "user", "content": USER % tier},
        ],
        tier=tier,
        groq_model=model,
        nim_model=model,
        max_tokens=128,
        json_mode=True,
        _force_groq=True,
    )


def main() -> int:
    status = llm_client.get_llm_status()
    print("LLM status:", json.dumps(status, indent=2))

    if not llm_client.GROQ_API_KEY:
        print("FAIL: GROQ_API_KEY not set in .env.local")
        return 1

    for tier in ("nano", "balanced", "strong"):
        model = TIER_MODELS[tier]["groq"]
        result = _run(tier)
        ok = not result.raw_error and result.diagnosis.get("ok") is True
        print(
            f"\n{'PASS' if ok else 'FAIL'} tier={tier} model={model} "
            f"latency={result.latency_ms}ms"
        )
        if result.raw_error:
            print("  error:", result.raw_error[:160])
        else:
            print("  response:", result.diagnosis)
        if not ok:
            return 1

    print("\nPASS: all Groq tiers working")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
