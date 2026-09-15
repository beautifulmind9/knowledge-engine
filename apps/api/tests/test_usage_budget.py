from app.services import ai_gateway


def test_default_daily_call_limit_is_conservative_free_tier_buffer(monkeypatch):
    monkeypatch.delenv("GEMINI_DAILY_CALL_LIMIT", raising=False)
    assert ai_gateway.status()["daily_call_limit"] == 450


def test_daily_call_limit_remains_configurable(monkeypatch):
    monkeypatch.setenv("GEMINI_DAILY_CALL_LIMIT", "25")
    assert ai_gateway.status()["daily_call_limit"] == 25
