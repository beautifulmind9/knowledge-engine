import io
import json
import logging
from types import SimpleNamespace

import pytest

from app.services import performance_timing


@pytest.fixture
def perf_caplog(caplog):
    logger=performance_timing.logger
    old_level=logger.level
    old_propagate=logger.propagate
    logger.setLevel(logging.INFO)
    logger.propagate=False
    logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)
        logger.setLevel(old_level)
        logger.propagate=old_propagate


def test_timing_collection_failure_never_escapes(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("logging unavailable")

    monkeypatch.setattr(performance_timing.logger, "info", fail)
    performance_timing.emit("synthetic", performance_timing.start(), source_id="source-safe")


def test_timing_event_contains_only_explicit_safe_metadata(perf_caplog):
    perf_caplog.clear()
    performance_timing.emit("synthetic", duration_ms=12.5, result="error", source_id="source-safe")
    assert '"duration_ms":12.5' in perf_caplog.records[-1].getMessage()
    assert "source-safe" in perf_caplog.records[-1].getMessage()


def test_info_event_uses_uvicorn_stream_once_without_content():
    uvicorn_logger=logging.getLogger("uvicorn")
    error_logger=logging.getLogger("uvicorn.error")
    original_uvicorn=(uvicorn_logger.level, list(uvicorn_logger.handlers), uvicorn_logger.propagate)
    original_error=(error_logger.level, list(error_logger.handlers), error_logger.propagate)
    stream=io.StringIO()
    handler=logging.StreamHandler(stream)
    try:
        # Mirrors Uvicorn's default hierarchy: uvicorn.error propagates to the
        # INFO-level uvicorn logger, which owns the sole stream handler.
        uvicorn_logger.handlers=[handler]
        uvicorn_logger.setLevel(logging.INFO)
        uvicorn_logger.propagate=False
        error_logger.handlers=[]
        error_logger.setLevel(logging.INFO)
        error_logger.propagate=True

        performance_timing.emit("synthetic", duration_ms=3.25,
                                result="success", source_id="source-safe",
                                operation_category="interpretation_part")

        lines=stream.getvalue().splitlines()
        assert len(lines)==1
        assert lines[0].startswith("PERF ")
        event=json.loads(lines[0][5:])
        assert event=={"duration_ms":3.25,"event":"synthetic",
                       "operation_category":"interpretation_part",
                       "result":"success","source_id":"source-safe"}
        for forbidden in ("source text", "prompt text", "model output", "private filename", "secret"):
            assert forbidden not in lines[0]
    finally:
        uvicorn_logger.handlers=original_uvicorn[1]
        uvicorn_logger.setLevel(original_uvicorn[0])
        uvicorn_logger.propagate=original_uvicorn[2]
        error_logger.handlers=original_error[1]
        error_logger.setLevel(original_error[0])
        error_logger.propagate=original_error[2]


def test_synthetic_snapshot_size_grows_with_sources_chunks_and_assets():
    base={"sources":[],"extraction_jobs":[],"knowledge_assets":[]}
    source_added={**base,"sources":[{"id":"s1","title":"Synthetic"}]}
    chunk_added={**source_added,"extraction_jobs":[{"id":"j1","chunk_id":"c1","status":"completed"}]}
    asset_added={**chunk_added,"knowledge_assets":[{"id":"a1","source_id":"s1","evidence":"synthetic evidence"}]}
    sizes=[performance_timing.snapshot_utf8_size(value) for value in (base,source_added,chunk_added,asset_added)]
    assert all(type(size) is int for size in sizes)
    assert sizes[0] < sizes[1] < sizes[2] < sizes[3]


def test_nested_operation_context_preserves_request_correlation(perf_caplog):
    perf_caplog.clear()
    with performance_timing.operation_context(request_id="request-safe", operation_category="material_preparation_request"):
        with performance_timing.operation_context(source_id="source-safe", chunk_id="chunk-safe", operation_category="interpretation_part"):
            performance_timing.emit("synthetic", duration_ms=1)
    event=perf_caplog.records[-1].getMessage()
    assert "request-safe" in event and "source-safe" in event and "chunk-safe" in event


def test_interpretation_request_correlates_provider_and_state_saves_without_real_provider(
    client, source, asset, monkeypatch, perf_caplog
):
    from app.services import ai_gateway

    perf_caplog.clear()
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
    perf_caplog.clear()
    response=client.post(f"/sources/{source[0]['id']}/interpret?max_chunks=1")
    assert response.status_code==200,response.text
    events=[]
    for record in perf_caplog.records:
        message=record.getMessage()
        if message.startswith("PERF "):
            events.append(json.loads(message[5:]))
    provider=next(event for event in events if event["event"]=="gemini_attempt")
    matched_saves=[event for event in events if event["event"]=="state_persistence_attempt"
                   and event.get("request_id")==provider.get("request_id")]
    assert provider.get("request_id")
    assert provider["source_id"]==source[0]["id"] and provider["chunk_id"]==source[1]["id"]
    # Local allowance admission remains snapshot-backed; hosted admission uses
    # its separate ledger and the two interpretation checkpoints.
    assert len(matched_saves)==3
    part_saves=[event for event in matched_saves if event.get("chunk_id")==source[1]["id"]]
    assert len(part_saves)==2
