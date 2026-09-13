"""Explicit free-project opt-in, bounded calls, no automatic quota retries."""
import json
import os
from datetime import datetime, timezone
from fastapi import HTTPException
from google import genai
from app.db.mock_data import usage


# Gemini structured outputs support only a subset of JSON Schema. Keep the
# internal Pydantic schema strict, but translate unsupported keywords before
# sending it to the provider. In particular, Pydantic uses `const` for Literal
# values and discriminated unions add `discriminator`; Gemini supports `enum`
# plus oneOf/anyOf instead.
def _gemini_response_schema(value):
    if isinstance(value, list):
        return [_gemini_response_schema(item) for item in value]
    if not isinstance(value, dict):
        return value

    normalized = {}
    for key, item in value.items():
        if key in {"discriminator", "default", "minLength", "maxLength"}:
            continue
        if key == "const":
            normalized["enum"] = [_gemini_response_schema(item)]
            continue
        normalized[key] = _gemini_response_schema(item)
    return normalized


def status():
    limit = max(0, int(os.getenv("GEMINI_DAILY_CALL_LIMIT", "20")))
    calls = usage.get("calls", 0) if usage.get("day") == datetime.now(timezone.utc).date().isoformat() else 0
    capped = calls >= limit
    return {"configured": bool(os.getenv("GEMINI_API_KEY")),
            "free_tier_confirmed": os.getenv("GEMINI_FREE_TIER_CONFIRMED") == "true",
            "daily_call_limit": limit,
            "calls_today": calls, "daily_limit_reached": capped,
            "paused": usage.get("paused", False) or capped,
            "reason": usage.get("reason") or ("Local daily call limit reached. Resume tomorrow; no paid fallback is used." if capped else None),
            "last_attempt_at": usage.get("last_attempt_at"),
            "note": "The application cannot verify Google's billing settings. Use a project with billing disabled."}


def generate(model, payload, schema):
    from app.services.knowledge_extraction import persist_state
    current = status()
    if not current["configured"]:
        raise HTTPException(503, "Add GEMINI_API_KEY to enable AI generation. Manual import remains available.")
    if not current["free_tier_confirmed"]:
        raise HTTPException(503, "Confirm billing is disabled for your Gemini project, then set GEMINI_FREE_TIER_CONFIRMED=true.")
    if current["paused"]:
        raise HTTPException(429, current["reason"] or "AI calls paused. Resume explicitly when quota is available.")
    if current["calls_today"] >= current["daily_call_limit"]:
        raise HTTPException(429, "Local daily call limit reached. Resume tomorrow; no paid fallback is used.")
    usage.update(day=datetime.now(timezone.utc).date().isoformat(), calls=current["calls_today"]+1,
                 last_attempt_at=datetime.now(timezone.utc).isoformat())
    persist_state()
    try:
        with genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options={"timeout": 60000, "retry_options": {"attempts": 1}}) as client:
            interactions = client.interactions
            # The pinned SDK maps attempts=1 to one *retry* for Interactions,
            # and normalizes attempts=0 back to 1. Disable that resource's
            # retry strategy explicitly, including transport-error retries.
            # Fail closed if this SDK surface changes; contract tests cover it.
            interactions.sdk_configuration.retry_config.strategy = "none"
            return interactions.create(model=model, input=json.dumps(payload, ensure_ascii=False), store=False,
                response_format={"type":"text", "mime_type":"application/json", "schema":_gemini_response_schema(schema)})
    except Exception as error:
        quota = getattr(error, "code", None) == 429 or any(s in str(error).lower() for s in ("429", "quota", "resource_exhausted"))
        if quota:
            usage.update(paused=True, reason="Gemini quota exhausted. Progress is saved. Wait for quota to reset, then resume explicitly.")
            persist_state()
            raise HTTPException(429, usage["reason"]) from error
        raise HTTPException(502, "AI provider request failed. Progress is saved; retry manually later.") from error
