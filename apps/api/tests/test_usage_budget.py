from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
import json
import pytest
from app.services import ai_gateway


def test_default_daily_call_limit_is_conservative_free_tier_buffer(monkeypatch):
    monkeypatch.delenv("GEMINI_DAILY_CALL_LIMIT", raising=False)
    assert ai_gateway.status()["daily_call_limit"] == 450


def test_daily_call_limit_remains_configurable(monkeypatch):
    monkeypatch.setenv("GEMINI_DAILY_CALL_LIMIT", "25")
    assert ai_gateway.status()["daily_call_limit"] == 25


def test_quota_day_tracks_provider_midnight_pacific():
    # September is daylight-saving time in Los Angeles, so midnight Pacific is 07:00 UTC.
    assert ai_gateway._quota_day(datetime(2026, 9, 16, 6, 59, tzinfo=timezone.utc)) == "2026-09-15"
    assert ai_gateway._quota_day(datetime(2026, 9, 16, 7, 0, tzinfo=timezone.utc)) == "2026-09-16"


def test_quota_day_handles_winter_offset():
    # In January, midnight Pacific is 08:00 UTC. ZoneInfo must handle the DST change.
    assert ai_gateway._quota_day(datetime(2026, 1, 15, 7, 59, tzinfo=timezone.utc)) == "2026-01-14"
    assert ai_gateway._quota_day(datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)) == "2026-01-15"


def test_concurrent_attempts_cannot_both_admit_the_last_daily_slot(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "true")
    monkeypatch.setenv("GEMINI_DAILY_CALL_LIMIT", "1")
    usage = {}
    monkeypatch.setattr(ai_gateway, "usage", usage)
    monkeypatch.setattr("app.services.knowledge_extraction.persist_state", lambda: None)
    provider_started, release_provider = Event(), Event()
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            self.interactions = self
            self.sdk_configuration = SimpleNamespace(retry_config=SimpleNamespace(strategy="retry"))
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def create(self, **kwargs):
            self.sdk_configuration.retry_config.strategy = "none"
            calls.append(kwargs)
            provider_started.set()
            assert release_provider.wait(timeout=5)
            return SimpleNamespace(output_text=json.dumps({"ok": True}), id="synthetic")

    monkeypatch.setattr(ai_gateway.genai, "Client", FakeClient)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(ai_gateway.generate, "model", {}, {"type": "object"})
        assert provider_started.wait(timeout=5)
        second = pool.submit(ai_gateway.generate, "model", {}, {"type": "object"})
        with pytest.raises(Exception) as rejected:
            second.result(timeout=5)
        assert getattr(rejected.value, "status_code", None) == 429
        release_provider.set()
        assert first.result(timeout=5).output_text == '{"ok": true}'

    assert len(calls) == 1
    assert usage["calls"] == 1
