"""Free-tier guarded access to Gemini's asynchronous Batch API.

Batch submission is an explicit provider attempt and counts once against the
same local daily call cap as synchronous generation. Status retrieval does not
consume a generation-call slot and never polls automatically.
"""
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import HTTPException

from app.db.mock_data import usage
from app.services import ai_gateway


logger = logging.getLogger(__name__)


def _persist_usage():
    from app.services.knowledge_extraction import persist_state
    persist_state()


def _client_http_options():
    """One transport attempt only for the legacy Batches resource.

    google-genai 2.23 exposes ``client.batches`` through the legacy API client,
    not the NextGen resource used by ``client.interactions``. For the legacy
    client, ``HttpRetryOptions.attempts`` includes the initial request, so
    attempts=1 means no automatic retry. The Batches object therefore does not
    expose ``sdk_configuration.retry_config`` and must not be treated like the
    Interactions resource.
    """
    return {"timeout": 60000, "retry_options": {"attempts": 1}}


def _generation_preflight():
    current = ai_gateway.status()
    if not current["configured"]:
        raise HTTPException(503, "Add GEMINI_API_KEY to enable AI generation. Manual import remains available.")
    if not current["free_tier_confirmed"]:
        raise HTTPException(503, "Confirm billing is disabled for your Gemini project, then set GEMINI_FREE_TIER_CONFIRMED=true.")
    if current["paused"]:
        raise HTTPException(429, current["reason"] or "AI calls paused. Resume explicitly when quota is available.")
    if current["calls_today"] >= current["daily_call_limit"]:
        raise HTTPException(429, "Local daily call limit reached. Resume tomorrow; no paid fallback is used.")
    return current


def _record_submission_attempt(current):
    """Count only once the code is about to call the provider create method."""
    usage.update(
        day=datetime.now(timezone.utc).date().isoformat(),
        calls=current["calls_today"] + 1,
        last_attempt_at=datetime.now(timezone.utc).isoformat(),
    )
    _persist_usage()


def submit_generate_content_batch(model: str, inline_requests: list, display_name: str):
    """Submit exactly one asynchronous Gemini Batch provider attempt."""
    current = _generation_preflight()

    try:
        with ai_gateway.genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            http_options=_client_http_options(),
        ) as client:
            batches = client.batches
            # Count immediately before the provider create operation. SDK
            # setup/compatibility failures that occur before this point are not
            # provider attempts and should not consume the local daily cap.
            _record_submission_attempt(current)
            return batches.create(
                model=model,
                src=inline_requests,
                config={"display_name": display_name},
            )
    except Exception as error:
        logger.warning(
            "Gemini Batch provider failure diagnostic: %s",
            json.dumps(ai_gateway._provider_diagnostic(error), sort_keys=True),
        )
        quota = getattr(error, "code", None) == 429 or any(
            signal in str(error).lower()
            for signal in ("429", "quota", "resource_exhausted")
        )
        if quota:
            usage.update(
                paused=True,
                reason="Gemini quota exhausted. Progress is saved. Wait for quota to reset, then resume explicitly.",
            )
            _persist_usage()
            raise HTTPException(429, usage["reason"]) from error
        raise HTTPException(502, "AI batch submission failed. Progress is saved; retry manually later.") from error


def get_generate_content_batch(name: str):
    """Retrieve one existing batch job once; never poll or retry automatically."""
    current = ai_gateway.status()
    if not current["configured"]:
        raise HTTPException(503, "Add GEMINI_API_KEY to retrieve the AI batch job.")
    if not current["free_tier_confirmed"]:
        raise HTTPException(503, "Confirm billing is disabled for your Gemini project, then set GEMINI_FREE_TIER_CONFIRMED=true.")

    try:
        with ai_gateway.genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            http_options=_client_http_options(),
        ) as client:
            return client.batches.get(name=name)
    except HTTPException:
        raise
    except Exception as error:
        logger.warning(
            "Gemini Batch status failure diagnostic: %s",
            json.dumps(ai_gateway._provider_diagnostic(error), sort_keys=True),
        )
        raise HTTPException(502, "AI batch status retrieval failed. Progress is saved; retry manually later.") from error
