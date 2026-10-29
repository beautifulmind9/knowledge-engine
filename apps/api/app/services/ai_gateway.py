"""Explicit free-project opt-in, per-attempt allowance and bounded 503 retry."""
import json
import hashlib
from importlib.metadata import PackageNotFoundError, version as package_version
import logging
import os
import time
from copy import deepcopy
from threading import Lock
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from google import genai
from app.db.mock_data import usage
from app.persistence.factory import PERSISTENCE_MODE, get_allowance_store
from app.persistence.allowance import AllowancePersistenceError, legacy_usage_from_state
from app.services.performance_timing import start as timing_start, emit as timing_emit, utf8_size


logger = logging.getLogger(__name__)
PROVIDER_QUOTA_TIMEZONE = ZoneInfo("America/Los_Angeles")
_attempt_admission_lock = Lock()
_MAX_PROVIDER_ATTEMPTS = 2
_TRANSIENT_503_RETRY_DELAY_SECONDS = 2.0


def _sdk_version():
    """Read the installed SDK version from local package metadata only."""
    try:
        return package_version("google-genai")
    except PackageNotFoundError:
        return None


def _quota_day(now=None):
    """Return the provider RPD day, which resets at midnight Pacific time."""
    instant = now or datetime.now(timezone.utc)
    return instant.astimezone(PROVIDER_QUOTA_TIMEZONE).date().isoformat()


def _response_json_in_memory(error):
    """Best-effort provider error JSON for classification only; never log it."""
    response = getattr(error, "response", None)
    if response is None:
        return None
    candidate = getattr(response, "json", None)
    try:
        value = candidate() if callable(candidate) else candidate
    except Exception:
        value = None
    return value if isinstance(value, dict) else None


def _provider_diagnostic(error):
    """Allowlisted metadata only. Never serialize an exception/body/request.

    Raw messages can echo private inputs. They may be inspected in memory only
    to choose a fixed category; they are never returned or logged.
    """
    known_types = {
        'BadRequestError', 'RateLimitError', 'InternalServerError', 'APITimeoutError',
        'APIConnectionError', 'APIStatusError', 'APIResponseValidationError',
        'AuthenticationError', 'PermissionDeniedError', 'NotFoundError', 'ConflictError',
        'UnprocessableEntityError',
        'APIError', 'ClientError', 'ServerError', 'GenAiError', 'GenAiDefaultError',
        'CreateInteractionClientError', 'CreateInteractionServerError',
        'ResponseValidationError', 'NoResponseError', 'ReadTimeout', 'ConnectTimeout',
        'WriteTimeout', 'PoolTimeout', 'ConnectError', 'ReadError', 'WriteError',
        'RemoteProtocolError', 'TimeoutError', 'RuntimeError', 'ValueError', 'TypeError',
    }
    known_statuses = {
        'INVALID_ARGUMENT', 'FAILED_PRECONDITION', 'OUT_OF_RANGE', 'UNAUTHENTICATED',
        'PERMISSION_DENIED', 'NOT_FOUND', 'ALREADY_EXISTS', 'RESOURCE_EXHAUSTED',
        'CANCELLED', 'ABORTED', 'DEADLINE_EXCEEDED', 'INTERNAL', 'UNAVAILABLE',
        'DATA_LOSS', 'UNKNOWN', 'UNIMPLEMENTED',
    }
    known_codes = {
        'invalid_request', 'invalid_request_error', 'invalid_argument',
        'failed_precondition', 'parameter_unknown', 'content_blocked',
        'resource_exhausted', 'rate_limit_exceeded',
    }

    name = type(error).__name__
    diagnostic = {'exception_type': name if name in known_types else 'OtherProviderError'}
    for field in ('status_code', 'code'):
        value = getattr(error, field, None)
        if type(value) is int and 0 <= value <= 599:
            diagnostic[field] = value

    metadata = {}
    message_candidates = []
    containers = [
        getattr(error, 'body', None),
        getattr(error, 'data', None),
        _response_json_in_memory(error),
    ]
    for container in containers:
        if isinstance(container, dict):
            nested = container.get('error', container)
            if isinstance(nested, dict):
                for key, value in nested.items():
                    metadata.setdefault(key, value)
                if isinstance(nested.get('message'), str):
                    message_candidates.append(nested['message'])

    nested_object = getattr(getattr(error, 'data', None), 'error', None)
    for field in ('status', 'reason'):
        value = getattr(error, field, None)
        if value is None and nested_object is not None:
            value = getattr(nested_object, field, None)
        if value is None:
            value = metadata.get(field)
        if isinstance(value, str) and value in known_statuses:
            diagnostic['provider_' + field] = value

    # Preserve the provider's original allowlisted spelling/casing for diagnostics
    # while normalizing only for internal category selection below.
    provider_code = metadata.get('code')
    if isinstance(provider_code, str) and provider_code.lower() in known_codes:
        diagnostic['provider_code'] = provider_code
    provider_type = metadata.get('type')
    if isinstance(provider_type, str) and provider_type.lower() in known_codes:
        diagnostic['provider_type'] = provider_type

    direct_message = getattr(error, 'message', None)
    if isinstance(direct_message, str):
        message_candidates.append(direct_message)
    try:
        rendered = str(error)
    except Exception:
        rendered = ''
    if rendered:
        message_candidates.append(rendered)

    # Inspect provider prose only in memory. Emit a fixed category, never prose.
    text = '\n'.join(message_candidates)[:8192].lower()
    normalized_provider_code = str(diagnostic.get('provider_code', '')).lower()
    normalized_provider_status = str(diagnostic.get('provider_status', '')).lower()
    schema_signal = any(word in text for word in ('schema', 'response_format', 'response format', 'json schema'))
    complexity_signal = any(word in text for word in (
        'complex', 'nested', 'depth', 'too large', 'too many', 'size', 'simplif',
        'combinatorial', 'states for serving',
    ))
    rejection_signal = any(word in text for word in (
        'invalid', 'unsupported', 'not supported', 'invalid_argument', 'bad request',
    ))

    # Explicit provider codes/statuses are more actionable than overlapping prose.
    # For example, "unknown parameter in response_format" mentions response_format
    # but is fundamentally an unsupported request parameter, not a bad schema.
    if normalized_provider_code == 'parameter_unknown':
        category = 'unknown_request_parameter'
    elif normalized_provider_code == 'failed_precondition' or normalized_provider_status == 'failed_precondition':
        category = 'provider_precondition_failed'
    elif normalized_provider_code == 'content_blocked':
        category = 'content_blocked'
    elif schema_signal and complexity_signal:
        category = 'response_schema_complexity_or_size'
    elif schema_signal and rejection_signal:
        category = 'response_schema_rejected'
    elif any(word in text for word in (
        'request too large', 'payload too large', 'request payload size',
        'token limit', 'too many input tokens', 'context length',
    )):
        category = 'request_size_limit'
    elif normalized_provider_code in {'invalid_request', 'invalid_request_error', 'invalid_argument'}:
        category = 'invalid_request_generic'
    elif 'Timeout' in diagnostic['exception_type']:
        category = 'transport_timeout'
    else:
        category = 'provider_message_omitted'
    diagnostic['message_category'] = category
    return diagnostic


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
    limit = max(0, int(os.getenv("GEMINI_DAILY_CALL_LIMIT", "450")))
    current_usage = usage
    if PERSISTENCE_MODE == "hosted":
        try:
            current_usage = get_allowance_store().read(usage)
        except AllowancePersistenceError:
            raise HTTPException(503, "The shared AI allowance could not be confirmed.",
                                headers={"X-KE-Interruption-Category": "allowance_unavailable"}) from None
    calls = current_usage.get("calls", 0) if current_usage.get("day") == _quota_day() else 0
    capped = calls >= limit
    return {"configured": bool(os.getenv("GEMINI_API_KEY")),
            "free_tier_confirmed": os.getenv("GEMINI_FREE_TIER_CONFIRMED") == "true",
            "daily_call_limit": limit,
            "calls_today": calls, "daily_limit_reached": capped,
            "paused": current_usage.get("paused", False) or capped,
            "reason": current_usage.get("reason") or ("Local daily call limit reached. Resume after the next Pacific daily reset; no paid fallback is used." if capped else None),
            "last_attempt_at": current_usage.get("last_attempt_at"),
            "note": "The application cannot verify Google's billing settings. Use a project with billing disabled."}


def current_usage_state():
    if PERSISTENCE_MODE == "hosted":
        try:
            return deepcopy(get_allowance_store().read(usage))
        except AllowancePersistenceError:
            raise HTTPException(503, "The shared AI allowance could not be confirmed.",
                                headers={"X-KE-Interruption-Category": "allowance_unavailable"}) from None
    return deepcopy(usage)


def resume_usage():
    if PERSISTENCE_MODE == "hosted":
        try:
            get_allowance_store().read(usage)
            get_allowance_store().set_paused(False)
        except AllowancePersistenceError:
            raise HTTPException(503, "The shared AI allowance could not be updated.",
                                headers={"X-KE-Interruption-Category": "allowance_unavailable"}) from None
        return status()
    usage.update(paused=False, reason=None)
    from app.services.knowledge_extraction import persist_state
    persist_state()
    return status()


def copy_allowance_to_legacy_snapshot():
    """Controlled rollback step: copy authoritative hosted usage into snapshot."""
    if PERSISTENCE_MODE != "hosted":
        raise RuntimeError("Allowance copy-back is only used for hosted rollback.")
    try:
        state = get_allowance_store().read(usage)
    except AllowancePersistenceError:
        raise RuntimeError("Hosted allowance state could not be confirmed for rollback.") from None
    usage.clear()
    usage.update(deepcopy(legacy_usage_from_state(state)))
    from app.services.knowledge_extraction import persist_state
    persist_state()
    return deepcopy(usage)


def generation_request(model, payload, schema, *, max_output_tokens=None):
    """Exact supported Interactions arguments; defaults preserve existing callers."""
    request = dict(model=model, input=json.dumps(payload, ensure_ascii=False), store=False,
                   response_format={"type":"text", "mime_type":"application/json",
                                    "schema":_gemini_response_schema(schema)})
    if max_output_tokens is not None:
        if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 65536:
            raise ValueError("Invalid experimental output token ceiling.")
        request["generation_config"] = {"max_output_tokens":max_output_tokens}
    return request


def generation_request_sha256(request):
    return hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def generate(model, payload, schema, *, max_output_tokens=None, verified_request_sha256=None, counted_request=None, count_receipt=None):
    from app.services.knowledge_extraction import persist_state
    # Serialize both the payload and response schema once so the bounded 503
    # retry sends byte-for-byte equivalent provider arguments.
    if counted_request is not None:
        from app.services import source_answer_transport as counted
        try:
            counted.verify_receipt(counted_request,count_receipt)
            # Bind the frozen representation to the caller's actual payload/schema.
            body=counted_request.generation_body
            if (model!=counted.MODEL or body['contents'][0]['parts'][0]['text']!=json.dumps(payload,ensure_ascii=False)
                or body['generationConfig']['responseJsonSchema']!=_gemini_response_schema(schema)
                or max_output_tokens not in (None,counted.OUTPUT_LIMIT)
                or verified_request_sha256!=counted_request.fingerprint):
                raise counted.BudgetUnavailable()
        except (ValueError,TypeError):
            raise HTTPException(409,"Counted request is unverified or changed; no provider request sent.") from None
        if PERSISTENCE_MODE!='local' or not counted.generation_authorized(counted_request.fingerprint):
            raise HTTPException(503,"Experimental generation is not authorized; no provider request sent.")
        try:counted.claim_generation(counted_request.fingerprint)
        except counted.BudgetUnavailable:
            raise HTTPException(409,'One-shot generation was already claimed or unauthorized.') from None
        provider_request=counted_request.generation_body
        provider_input=provider_request['contents'][0]['parts'][0]['text']
        response_format=provider_request['generationConfig']
        api_surface='generateContent'
    else:
        provider_request = generation_request(model, payload, schema, max_output_tokens=max_output_tokens)
        if verified_request_sha256 is not None and verified_request_sha256 != generation_request_sha256(provider_request):
            raise HTTPException(409, "Verified request changed; no provider request was sent.")
        provider_input = provider_request["input"]
        response_format = provider_request["response_format"]
        api_surface='interactions'
    response_contract = json.dumps(response_format)
    provider_input_bytes = utf8_size(provider_input)
    response_contract_bytes = utf8_size(response_contract)
    request_fingerprints = {
        "model": model,
        "provider_input_sha256": hashlib.sha256(provider_input.encode("utf-8")).hexdigest(),
        "response_format_sha256": hashlib.sha256(response_contract.encode("utf-8")).hexdigest(),
        "api_surface": api_surface,
        "sdk_version": _sdk_version(),
        "provider_input_bytes": provider_input_bytes,
        "response_contract_bytes": response_contract_bytes,
    }

    for attempt_number in range(1, _MAX_PROVIDER_ATTEMPTS + 1):
        if counted_request is not None:
            try:counted.verify_receipt(counted_request,count_receipt)
            except (counted.BudgetUnavailable,counted.BudgetExceeded):
                raise HTTPException(409,'Count receipt is no longer valid; no further attempt sent.') from None
        attempt_started = timing_start()
        reservation_id = uuid4().hex
        attempted_at = datetime.now(timezone.utc)
        attempt_day = _quota_day(attempted_at)
        # Each dispatch, including the one permitted transient retry, is a new
        # independently admitted and durably reserved allowance attempt.
        with _attempt_admission_lock:
            if not os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_FREE_TIER_CONFIRMED") != "true":
                raise HTTPException(503, "AI is not available in this workspace.", headers={"X-KE-Interruption-Category":"ai_unavailable"})
            if PERSISTENCE_MODE == "hosted":
                reservation_started = timing_start()
                reservation_result = "persistence_error"
                try:
                    allowance_store = get_allowance_store()
                    allowance_store.ensure_migrated(usage)
                    reservation = allowance_store.reserve_attempt(
                        reservation_id=reservation_id, day=attempt_day,
                        limit=max(0, int(os.getenv("GEMINI_DAILY_CALL_LIMIT", "450"))),
                        attempted_at=attempted_at,
                    )
                except AllowancePersistenceError:
                    timing_emit("allowance_reservation", reservation_started,
                                result=reservation_result, destination_category="state",
                                operation_category="provider_attempt_admission",
                                reservation_id=reservation_id,
                                attempt_number=attempt_number,
                                approximate_payload_bytes=utf8_size(json.dumps({
                                    "reservation_id": reservation_id,
                                    "accounting_day": attempt_day,
                                    "attempted_at": attempted_at.isoformat(),
                                })))
                    raise HTTPException(503, "The shared AI allowance could not be confirmed; no provider request was sent.",
                                        headers={"X-KE-Interruption-Category": "allowance_unavailable"}) from None
                reservation_result = "admitted" if reservation.get("admitted") else "denied"
                if reservation.get("duplicate"):
                    reservation_result = "duplicate"
                timing_emit("allowance_reservation", reservation_started,
                            result=reservation_result, destination_category="state",
                            operation_category="provider_attempt_admission",
                            reservation_id=reservation_id, attempt_number=attempt_number,
                            approximate_payload_bytes=utf8_size(json.dumps({
                                "reservation_id": reservation_id,
                                "accounting_day": attempt_day,
                                "attempted_at": attempted_at.isoformat(),
                            })))
                if not reservation.get("admitted"):
                    raise HTTPException(429, "The shared AI allowance is currently unavailable.", headers={"X-KE-Interruption-Category":"allowance_exhausted"})
                if not reservation.get("dispatch_allowed"):
                    raise HTTPException(503, "This provider attempt reservation was already used; no provider request was sent.",
                                        headers={"X-KE-Interruption-Category": "allowance_unavailable"})
            else:
                current = status()
                if not current["configured"] or not current["free_tier_confirmed"]:
                    raise HTTPException(503, "AI is not available in this workspace.", headers={"X-KE-Interruption-Category":"ai_unavailable"})
                if current["paused"] or current["calls_today"] >= current["daily_call_limit"]:
                    raise HTTPException(429, "The shared AI allowance is currently unavailable.", headers={"X-KE-Interruption-Category":"allowance_exhausted"})
                usage.update(day=attempt_day, calls=current["calls_today"]+1,
                             last_attempt_at=attempted_at.isoformat())
                persist_state()

        retry_reason = "transient_503" if attempt_number == 2 else None
        attempt_metadata = {
            "attempt_number": attempt_number,
            "max_attempts": _MAX_PROVIDER_ATTEMPTS,
            "retry_reason": retry_reason,
            **request_fingerprints,
        }
        logger.info("Gemini provider attempt admitted: %s", json.dumps(attempt_metadata, sort_keys=True))
        attempt_started = timing_start()
        try:
            if counted_request is not None:
                raw=counted.post(counted_request,'generateContent',os.environ['GEMINI_API_KEY'])
                response=counted.normalize_response(raw,count_receipt)
            else:
                with genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options={"timeout": 60000, "retry_options": {"attempts": 1}}) as client:
                    interactions = client.interactions
                    # Disable SDK-level retries; only this gateway's single
                    # confirmed-503 retry is permitted.
                    interactions.sdk_configuration.retry_config.strategy = "none"
                    response = interactions.create(**provider_request)
            timing_emit("gemini_attempt", attempt_started, source_id=payload.get("source_id"),
                        chunk_id=payload.get("chunk_id"), attempt_number=attempt_number,
                        attempt_kind="initial" if attempt_number == 1 else "bounded_503_retry",
                        result="success", destination_category="gemini",
                        reservation_id=reservation_id if PERSISTENCE_MODE == "hosted" else None,
                        provider_input_bytes=provider_input_bytes,
                        response_contract_bytes=response_contract_bytes,
                        model=model, api_surface=api_surface, sdk_version=request_fingerprints["sdk_version"],
                        provider_input_sha256=request_fingerprints["provider_input_sha256"],
                        response_format_sha256=request_fingerprints["response_format_sha256"],
                        estimated_request_payload_bytes=(provider_input_bytes+response_contract_bytes)
                        if provider_input_bytes is not None and response_contract_bytes is not None else None)
            return response
        except Exception as error:
            diagnostic = _provider_diagnostic(error)
            diagnostic.update(attempt_metadata)
            timing_emit("gemini_attempt", attempt_started, source_id=payload.get("source_id"),
                        chunk_id=payload.get("chunk_id"), attempt_number=attempt_number,
                        attempt_kind="initial" if attempt_number == 1 else "bounded_503_retry",
                        result="http_503_retryable" if diagnostic.get("status_code") == 503 and attempt_number == 1 else "provider_error",
                        destination_category="gemini", http_status=diagnostic.get("status_code"),
                        reservation_id=reservation_id if PERSISTENCE_MODE == "hosted" else None,
                        provider_input_bytes=provider_input_bytes,
                        response_contract_bytes=response_contract_bytes,
                        model=model, api_surface=api_surface, sdk_version=request_fingerprints["sdk_version"],
                        provider_input_sha256=request_fingerprints["provider_input_sha256"],
                        response_format_sha256=request_fingerprints["response_format_sha256"],
                        estimated_request_payload_bytes=(provider_input_bytes+response_contract_bytes)
                        if provider_input_bytes is not None and response_contract_bytes is not None else None)
            logger.warning("Gemini provider failure diagnostic: %s", json.dumps(diagnostic, sort_keys=True))
            quota = getattr(error, "code", None) == 429 or any(s in str(error).lower() for s in ("429", "quota", "resource_exhausted"))
            if quota:
                pause_reason="Gemini quota exhausted. Progress is saved. Wait for quota to reset, then resume explicitly."
                if PERSISTENCE_MODE == "hosted":
                    try:
                        get_allowance_store().set_paused(True, pause_reason)
                    except AllowancePersistenceError:
                        raise HTTPException(503, "The shared AI allowance state could not be updated.",
                                            headers={"X-KE-Interruption-Category": "allowance_unavailable"}) from None
                else:
                    usage.update(paused=True, reason=pause_reason)
                    persist_state()
                raise HTTPException(429, "The shared AI allowance is currently unavailable.", headers={"X-KE-Interruption-Category":"allowance_exhausted"}) from error

            # Retry only a definite HTTP 503 response. Timeouts, connection
            # failures, validation errors and every other status remain single
            # attempts because their outcome is not the specified condition.
            if diagnostic.get("status_code") == 503 and attempt_number == 1:
                time.sleep(_TRANSIENT_503_RETRY_DELAY_SECONDS)
                continue
            if diagnostic.get("status_code") == 400 and diagnostic.get("message_category") == "invalid_request_generic":
                raise HTTPException(
                    502,
                    "The AI service could not accept this request. Your materials and saved work are unchanged.",
                    headers={"X-KE-Interruption-Category":"provider_rejected"},
                ) from error
            if diagnostic.get("status_code")==400:
                category="provider_rejected"
            elif isinstance(diagnostic.get("status_code"), int) and diagnostic["status_code"] >= 500:
                category="provider_unavailable"
            elif diagnostic.get("message_category")=="transport_timeout":
                # A definite gateway timeout is persisted as failed by the
                # extraction service, allowing explicit continuation.
                category="request_timed_out"
            elif "Connection" in diagnostic.get("exception_type",""):
                category="transport_uncertain"
            else:
                category="transport_uncertain"
            raise HTTPException(502, "The AI request could not be confirmed. Your materials and saved work are unchanged.", headers={"X-KE-Interruption-Category":category}) from error
