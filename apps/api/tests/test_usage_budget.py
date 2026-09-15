from datetime import datetime, timezone
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
