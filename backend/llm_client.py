"""
llm_client.py
Unified LLM client — Groq primary, NIM optional when NVIDIA_API_KEY is set.
"""

import os
import re
import time
import json
from dataclasses import dataclass
from typing import Optional
import env_loader  # noqa: F401 — loads .env.local from project root

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NIM_BASE_URL = os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
LLM_PROVIDER_PREFERENCE = os.getenv("LLM_PROVIDER_PREFERENCE", "groq").lower()

GROQ_JSON_FALLBACK_MODEL = "llama-3.3-70b-versatile"

THINKING_INSTRUCTION = (
    "Think step by step internally before answering. "
    "Reason through root cause carefully, then output only the final JSON diagnosis."
)


@dataclass
class LLMResult:
    content: str
    diagnosis: dict
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    raw_error: Optional[str] = None


def _get_groq_client():
    from groq import Groq
    return Groq(api_key=GROQ_API_KEY)


def _get_nim_client():
    from openai import OpenAI
    return OpenAI(base_url=NIM_BASE_URL, api_key=NVIDIA_API_KEY)


def _select_provider(tier: str, groq_model: str, nim_model: str) -> tuple[str, str]:
    """Return (provider, model_id). Groq first unless preference is nim and key exists."""
    if LLM_PROVIDER_PREFERENCE == "nim" and NVIDIA_API_KEY:
        return "nim", nim_model
    if LLM_PROVIDER_PREFERENCE == "auto" and NVIDIA_API_KEY and tier == "strong":
        return "nim", nim_model
    if GROQ_API_KEY:
        return "groq", groq_model
    if NVIDIA_API_KEY:
        return "nim", nim_model
    raise RuntimeError("No LLM API key configured (GROQ_API_KEY or NVIDIA_API_KEY)")


def _is_json_mode_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "json_validate_failed" in msg or "failed to validate json" in msg


def _extract_json_object(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        raise json.JSONDecodeError("empty response", text, 0)

    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _error_result(provider: str, model: str, exc: Exception, latency_ms: int) -> LLMResult:
    return LLMResult(
        content="{}",
        diagnosis={
            "root_cause": f"LLM error: {str(exc)[:120]}",
            "confidence": 0.0,
            "fix": "Manual investigation required",
            "estimated_resolution_minutes": 30,
            "escalate_to_human": True,
            "escalation_reason": "LLM call failed",
            "rca_summary": "Automated diagnosis failed.",
            "recalled_incidents": [],
            "memory_informed": False,
        },
        provider=provider,
        model=model,
        prompt_tokens=0,
        completion_tokens=0,
        latency_ms=latency_ms,
        raw_error=str(exc),
    )


def _invoke_completion(
    provider: str,
    model: str,
    messages: list[dict],
    max_tokens: int,
    json_mode: bool,
    temperature: float,
) -> tuple[str, int, int]:
    if provider == "groq":
        client = _get_groq_client()
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        completion = client.chat.completions.create(**kwargs)
        raw = completion.choices[0].message.content or "{}"
        usage = completion.usage
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        return raw, prompt_tokens, completion_tokens

    client = _get_nim_client()
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    completion = client.chat.completions.create(**kwargs)
    raw = completion.choices[0].message.content or "{}"
    usage = completion.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    return raw, prompt_tokens, completion_tokens


def complete(
    messages: list[dict],
    tier: str,
    groq_model: str,
    nim_model: str,
    max_tokens: int = 1024,
    thinking_on: bool = False,
    json_mode: bool = True,
    temperature: float = 0.2,
    _force_groq: bool = False,
) -> LLMResult:
    """Execute chat completion via Groq or NIM with JSON retry fallbacks."""
    if _force_groq and GROQ_API_KEY:
        provider, model = "groq", groq_model
    else:
        provider, model = _select_provider(tier, groq_model, nim_model)

    final_messages = [dict(m) for m in messages]
    if thinking_on and final_messages and final_messages[0]["role"] == "system":
        final_messages[0] = {
            **final_messages[0],
            "content": THINKING_INSTRUCTION + "\n\n" + final_messages[0]["content"],
        }

    attempts: list[tuple[bool, str | None]] = [(json_mode, None)]
    if json_mode:
        attempts.append((False, None))
    if provider == "groq" and model != GROQ_JSON_FALLBACK_MODEL:
        attempts.append((False, GROQ_JSON_FALLBACK_MODEL))

    start = time.time()
    last_exc: Exception | None = None
    total_prompt = 0
    total_completion = 0
    used_model = model
    used_provider = provider

    for use_json_mode, model_override in attempts:
        try:
            attempt_provider = provider
            attempt_model = model_override or model
            if model_override and provider == "groq":
                attempt_model = model_override

            raw, prompt_tokens, completion_tokens = _invoke_completion(
                attempt_provider,
                attempt_model,
                final_messages,
                max_tokens,
                use_json_mode,
                temperature,
            )
            diagnosis = _extract_json_object(raw)
            total_prompt += prompt_tokens
            total_completion += completion_tokens
            used_model = attempt_model
            used_provider = attempt_provider
            latency = int((time.time() - start) * 1000)
            return LLMResult(
                content=raw,
                diagnosis=diagnosis,
                provider=used_provider,
                model=used_model,
                prompt_tokens=total_prompt,
                completion_tokens=total_completion,
                latency_ms=latency,
            )
        except Exception as exc:
            last_exc = exc
            if not (_is_json_mode_error(exc) or isinstance(exc, json.JSONDecodeError)):
                break

    latency = int((time.time() - start) * 1000)

    if provider == "nim" and GROQ_API_KEY and not _force_groq:
        try:
            return complete(
                messages,
                tier,
                groq_model,
                nim_model,
                max_tokens,
                thinking_on,
                json_mode,
                temperature,
                _force_groq=True,
            )
        except Exception:
            pass

    return _error_result(used_provider, used_model, last_exc or RuntimeError("LLM call failed"), latency)


def get_llm_status() -> dict:
    return {
        "groq_configured": bool(GROQ_API_KEY),
        "nim_configured": bool(NVIDIA_API_KEY),
        "preference": LLM_PROVIDER_PREFERENCE,
        "active_provider": "groq" if GROQ_API_KEY else ("nim" if NVIDIA_API_KEY else "none"),
    }
