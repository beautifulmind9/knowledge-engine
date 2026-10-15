import json
from types import SimpleNamespace

from app.services import performance_timing


def test_timing_collection_failure_never_escapes(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("logging unavailable")

    monkeypatch.setattr(performance_timing.logger, "info", fail)
    performance_timing.emit("synthetic", performance_timing.start(), source_id="source-safe")


def test_timing_event_contains_only_explicit_safe_metadata(caplog):
    caplog.set_level("INFO", logger="ke.performance")
    performance_timing.emit("synthetic", duration_ms=12.5, result="error", source_id="source-safe")
    assert '"duration_ms":12.5' in caplog.records[-1].getMessage()
    assert "source-safe" in caplog.records[-1].getMessage()


def test_synthetic_snapshot_size_grows_with_sources_chunks_and_assets():
    base={"sources":[],"extraction_jobs":[],"knowledge_assets":[]}
    source_added={**base,"sources":[{"id":"s1","title":"Synthetic"}]}
    chunk_added={**source_added,"extraction_jobs":[{"id":"j1","chunk_id":"c1","status":"completed"}]}
    asset_added={**chunk_added,"knowledge_assets":[{"id":"a1","source_id":"s1","evidence":"synthetic evidence"}]}
    sizes=[performance_timing.snapshot_utf8_size(value) for value in (base,source_added,chunk_added,asset_added)]
    assert all(type(size) is int for size in sizes)
    assert sizes[0] < sizes[1] < sizes[2] < sizes[3]


def test_nested_operation_context_preserves_request_correlation(caplog):
    caplog.set_level("INFO", logger="ke.performance")
    with performance_timing.operation_context(request_id="request-safe", operation_category="material_preparation_request"):
        with performance_timing.operation_context(source_id="source-safe", chunk_id="chunk-safe", operation_category="interpretation_part"):
            performance_timing.emit("synthetic", duration_ms=1)
    event=caplog.records[-1].getMessage()
    assert "request-safe" in event and "source-safe" in event and "chunk-safe" in event


def test_interpretation_request_correlates_provider_and_state_saves_without_real_provider(
    client, source, asset, monkeypatch, caplog
):
    from app.services import ai_gateway

    caplog.set_level("INFO", logger="ke.performance")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "true")
    monkeypatch.setenv("GEMINI_DAILY_CALL_LIMIT", "450")

    class FakeClient:
        def __init__(self, **_):
            self.interactions=self
            self.sdk_configuration=SimpleNamespace(retry_config=SimpleNamespace(strategy="default"))
        def __enter__(self): return self
        def __exit__(self,*_): return False
        def create(self, **_): return SimpleNamespace(output_text=json.dumps({"assets":[asset]}),id="synthetic-id")

    monkeypatch.setattr(ai_gateway.genai,"Client",FakeClient)
    caplog.clear()
    response=client.post(f"/sources/{source[0]['id']}/interpret?max_chunks=1")
    assert response.status_code==200,response.text
    events=[]
    for record in caplog.records:
        message=record.getMessage()
        if message.startswith("PERF "):
            events.append(json.loads(message[5:]))
    provider=next(event for event in events if event["event"]=="gemini_attempt")
    matched_saves=[event for event in events if event["event"]=="state_persistence_attempt"
                   and event.get("request_id")==provider.get("request_id")]
    assert provider.get("request_id")
    assert provider["source_id"]==source[0]["id"] and provider["chunk_id"]==source[1]["id"]
    assert len(matched_saves)>=4
    part_saves=[event for event in matched_saves if event.get("chunk_id")==source[1]["id"]]
    assert len(part_saves)>=3
