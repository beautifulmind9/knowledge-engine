import json
import hashlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import ai_gateway


class InternalServerError(Exception):
    status_code = 503
    code = 503
    body = {"error": {"code": "UNAVAILABLE", "status": "UNAVAILABLE"}}


class BadRequestError(Exception):
    status_code = 400
    code = 400
    body = {"error": {"code": "INVALID_ARGUMENT", "status": "INVALID_ARGUMENT"}}


class RateLimitError(Exception):
    status_code = 429
    code = 429
    body = {"error": {"code": "RESOURCE_EXHAUSTED", "status": "RESOURCE_EXHAUSTED"}}


class APITimeoutError(Exception):
    pass


def install_provider(monkeypatch, outcomes):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "true")
    monkeypatch.setenv("GEMINI_DAILY_CALL_LIMIT", "450")
    monkeypatch.setattr("app.services.knowledge_extraction.persist_state", lambda: None)
    calls = []
    remaining = list(outcomes)

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["http_options"]["retry_options"]["attempts"] == 1
            self.interactions = self
            self.sdk_configuration = SimpleNamespace(
                retry_config=SimpleNamespace(strategy="sdk-default")
            )

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def create(self, **kwargs):
            assert self.sdk_configuration.retry_config.strategy == "none"
            calls.append(kwargs)
            outcome = remaining.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(ai_gateway.genai, "Client", FakeClient)
    return calls


def test_first_success_uses_one_provider_attempt(monkeypatch):
    calls = install_provider(monkeypatch, [SimpleNamespace(output_text='{"ok":true}')])

    response = ai_gateway.generate("synthetic-model", {"text": "fixture"}, {"type": "object"})

    assert response.output_text == '{"ok":true}'
    assert len(calls) == 1
    assert ai_gateway.status()["calls_today"] == 1


def test_one_503_then_success_repeats_identical_provider_arguments(monkeypatch, caplog):
    caplog.set_level("INFO", logger="uvicorn.error")
    calls = install_provider(monkeypatch, [InternalServerError("unavailable"), SimpleNamespace(output_text="ok")])
    sleeps = []
    monkeypatch.setattr(ai_gateway.time, "sleep", sleeps.append)
    payload = {"instructions": "PRIVATE_PROMPT_FIXTURE", "evidence": ["PRIVATE_SOURCE_FIXTURE"]}
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}

    result = ai_gateway.generate("synthetic-model", payload, schema)

    assert result.output_text == "ok"
    assert len(calls) == ai_gateway.status()["calls_today"] == 2
    assert calls[0] == calls[1]
    assert calls[0]["model"] == "synthetic-model"
    assert calls[0]["input"] == json.dumps(payload, ensure_ascii=False)
    assert calls[0]["store"] is False
    assert calls[0]["response_format"]["schema"] == ai_gateway._gemini_response_schema(schema)
    assert calls[0]["response_format"] is calls[1]["response_format"]
    assert sleeps == [ai_gateway._TRANSIENT_503_RETRY_DELAY_SECONDS]
    events=[record.getMessage() for record in caplog.records if '"event":"gemini_attempt"' in record.getMessage()]
    assert len(events)==2
    assert '"attempt_number":1' in events[0] and '"attempt_kind":"initial"' in events[0]
    assert '"attempt_number":2' in events[1] and '"attempt_kind":"bounded_503_retry"' in events[1]
    assert '"result":"http_503_retryable"' in events[0]
    assert 'PRIVATE_PROMPT_FIXTURE' not in '\n'.join(events)
    assert 'PRIVATE_SOURCE_FIXTURE' not in '\n'.join(events)
    assert 'PRIVATE_PROMPT_FIXTURE' not in caplog.text
    assert 'PRIVATE_SOURCE_FIXTURE' not in caplog.text
    parsed = [json.loads(event.split("PERF ", 1)[1]) for event in events]
    assert parsed[0]["provider_input_sha256"] == parsed[1]["provider_input_sha256"]
    assert parsed[0]["response_format_sha256"] == parsed[1]["response_format_sha256"]
    assert parsed[0]["provider_input_sha256"] == hashlib.sha256(
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    expected_contract = {"type": "text", "mime_type": "application/json",
                         "schema": ai_gateway._gemini_response_schema(schema)}
    assert parsed[0]["response_format_sha256"] == hashlib.sha256(
        json.dumps(expected_contract).encode("utf-8")
    ).hexdigest()
    for event in parsed:
        assert event["model"] == "synthetic-model"
        assert event["api_surface"] == "interactions"
        assert event["sdk_version"]
        assert event["provider_input_bytes"] == len(json.dumps(payload, ensure_ascii=False).encode())
        assert event["response_contract_bytes"] == len(json.dumps(expected_contract).encode())


def test_two_503_responses_stop_after_two_attempts(monkeypatch):
    calls = install_provider(monkeypatch, [InternalServerError("unavailable"), InternalServerError("unavailable")])
    monkeypatch.setattr(ai_gateway.time, "sleep", lambda _: None)

    with pytest.raises(HTTPException) as failure:
        ai_gateway.generate("model", {"fixture": True}, {"type": "object"})

    assert failure.value.status_code == 502
    assert failure.value.headers["X-KE-Interruption-Category"] == "provider_unavailable"
    assert len(calls) == ai_gateway.status()["calls_today"] == 2


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_category"),
    [
        (BadRequestError("invalid"), 502, "provider_rejected"),
        (RateLimitError("quota"), 429, "allowance_exhausted"),
        (APITimeoutError("uncertain timeout"), 502, "request_timed_out"),
    ],
)
def test_non_503_failure_classes_are_never_retried(monkeypatch, error, expected_status, expected_category):
    calls = install_provider(monkeypatch, [error, SimpleNamespace(output_text="must not be used")])

    with pytest.raises(HTTPException) as failure:
        ai_gateway.generate("model", {"fixture": True}, {"type": "object"})

    assert failure.value.status_code == expected_status
    assert failure.value.headers["X-KE-Interruption-Category"] == expected_category
    assert len(calls) == 1
    assert ai_gateway.status()["calls_today"] == 1


def test_allowance_is_checked_again_before_503_retry(monkeypatch):
    monkeypatch.setenv("GEMINI_DAILY_CALL_LIMIT", "1")
    calls = install_provider(monkeypatch, [InternalServerError("unavailable"), SimpleNamespace(output_text="unused")])
    monkeypatch.setenv("GEMINI_DAILY_CALL_LIMIT", "1")
    monkeypatch.setattr(ai_gateway.time, "sleep", lambda _: None)

    with pytest.raises(HTTPException) as failure:
        ai_gateway.generate("model", {"fixture": True}, {"type": "object"})

    assert failure.value.status_code == 429
    assert failure.value.headers["X-KE-Interruption-Category"] == "allowance_exhausted"
    assert len(calls) == 1
    assert ai_gateway.status()["calls_today"] == 1
