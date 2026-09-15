import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.db import mock_data as db
from app.services import ai_gateway
from app.services import gemini_batch_gateway as batch_gateway
from app.services import gemini_source_batch as source_batch
from app.services.knowledge_extraction import persist_state
from app.services.text_chunking import save_chunks


def _install_chunks(source, count=3):
    s, _ = source
    chunks = [
        {
            "id": f"chunk_async_{i}",
            "source_id": s["id"],
            "text": f"Chunk {i} teaches practice method {i} for workshop participants.",
            "chapter_or_section": f"Section {i}",
        }
        for i in range(count)
    ]
    db.sources[0]["chunks_path"] = save_chunks(s["id"], chunks)
    persist_state()
    return s, chunks


def _asset_for(index):
    return {
        "asset_type": "principle",
        "title": f"Practice method {index}",
        "what_it_says": f"Use practice method {index} for workshop participants.",
        "evidence": f"Chunk {index} teaches practice method {index} for workshop participants.",
        "keywords": ["practice", f"method-{index}"],
        "confidence_score": 5,
    }


def _submit(source, monkeypatch, count=3):
    s, chunks = _install_chunks(source, count=count)
    captured = {}

    def fake_submit(model, inline_requests, display_name):
        captured["model"] = model
        captured["requests"] = inline_requests
        captured["display_name"] = display_name
        return SimpleNamespace(
            name="batches/test-source",
            state=SimpleNamespace(name="JOB_STATE_PENDING"),
        )

    monkeypatch.setattr(source_batch, "submit_generate_content_batch", fake_submit)
    result = source_batch.submit_source_batch(s["id"])
    jobs = [j for j in db.extraction_jobs if j["source_id"] == s["id"]]
    return s, chunks, jobs, captured, result


def test_source_batch_uses_independent_structured_requests(source, monkeypatch):
    s, chunks, jobs, captured, result = _submit(source, monkeypatch, count=3)

    assert result["submitted"] is True
    assert result["chunk_count"] == 3
    assert len(captured["requests"]) == 3
    assert len(jobs) == 3
    assert all(j["status"] == "running" for j in jobs)
    assert all(j["provider_batch_name"] == "batches/test-source" for j in jobs)

    for index, request in enumerate(captured["requests"]):
        payload = json.loads(request.contents[0].parts[0].text)
        assert payload["chunk_id"] == chunks[index]["id"]
        assert payload["chunk_text"] == chunks[index]["text"]
        assert "Every candidate asset must include" in payload["instructions"]
        for other_index, other in enumerate(chunks):
            if other_index != index:
                assert other["text"] not in request.contents[0].parts[0].text
        assert request.metadata["job_id"] == jobs[index]["id"]
        assert request.metadata["chunk_id"] == chunks[index]["id"]
        schema = request.config.response_schema
        assert schema["required"] == ["assets"]
        asset_schema = schema["properties"]["assets"]["items"]
        assert set(asset_schema["required"]) == {
            "asset_type",
            "title",
            "what_it_says",
            "evidence",
            "keywords",
            "confidence_score",
        }


def test_successful_batch_refresh_validates_and_stores_each_chunk(source, monkeypatch):
    s, chunks, jobs, _, _ = _submit(source, monkeypatch, count=3)

    responses = [
        SimpleNamespace(
            metadata={"job_id": job["id"], "chunk_id": job["chunk_id"]},
            error=None,
            response=SimpleNamespace(
                text=json.dumps({"assets": [_asset_for(index)]}),
                response_id=f"response-{index}",
            ),
        )
        for index, job in enumerate(jobs)
    ]
    monkeypatch.setattr(
        source_batch,
        "get_generate_content_batch",
        lambda name: SimpleNamespace(
            state=SimpleNamespace(name="JOB_STATE_SUCCEEDED"),
            dest=SimpleNamespace(inlined_responses=responses),
        ),
    )

    result = source_batch.refresh_source_batch(s["id"])

    assert result["collected"] is True
    assert len(result["results"]) == 3
    assert result["failures"] == []
    assert len(db.knowledge_assets) == 3
    assert all(j["status"] == "completed" for j in jobs)
    for asset, chunk in zip(db.knowledge_assets, chunks):
        assert asset["source_id"] == s["id"]
        assert asset["chunk_id"] == chunk["id"]


def test_invalid_batch_item_isolated_without_blocking_valid_sibling(source, monkeypatch):
    s, _, jobs, _, _ = _submit(source, monkeypatch, count=2)
    valid = _asset_for(0)
    invalid = {
        **_asset_for(1),
        "asset_type": "decision_rule",
        # Strict internal validation must still require action.
    }
    responses = [
        SimpleNamespace(
            metadata={"job_id": jobs[0]["id"], "chunk_id": jobs[0]["chunk_id"]},
            error=None,
            response=SimpleNamespace(text=json.dumps({"assets": [valid]}), response_id="ok"),
        ),
        SimpleNamespace(
            metadata={"job_id": jobs[1]["id"], "chunk_id": jobs[1]["chunk_id"]},
            error=None,
            response=SimpleNamespace(text=json.dumps({"assets": [invalid]}), response_id="bad"),
        ),
    ]
    monkeypatch.setattr(
        source_batch,
        "get_generate_content_batch",
        lambda name: SimpleNamespace(
            state=SimpleNamespace(name="JOB_STATE_SUCCEEDED"),
            dest=SimpleNamespace(inlined_responses=responses),
        ),
    )

    result = source_batch.refresh_source_batch(s["id"])

    assert len(result["results"]) == 1
    assert len(result["failures"]) == 1
    assert jobs[0]["status"] == "completed"
    assert jobs[1]["status"] == "failed"
    assert len(db.knowledge_assets) == 1
    assert db.knowledge_assets[0]["chunk_id"] == jobs[0]["chunk_id"]


def test_pending_refresh_does_not_poll_or_save_automatically(source, monkeypatch):
    s, _, jobs, _, _ = _submit(source, monkeypatch, count=2)
    checks = []

    def fake_get(name):
        checks.append(name)
        return SimpleNamespace(state=SimpleNamespace(name="JOB_STATE_RUNNING"), dest=None)

    monkeypatch.setattr(source_batch, "get_generate_content_batch", fake_get)
    result = source_batch.refresh_source_batch(s["id"])

    assert checks == ["batches/test-source"]
    assert result["collected"] is False
    assert not db.knowledge_assets
    assert all(j["status"] == "running" for j in jobs)


def test_batch_gateway_counts_one_submission_and_uses_one_transport_attempt(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fixture-key")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "true")
    calls = []
    client_kwargs = []

    class FakeBatches:
        # Deliberately no sdk_configuration: google-genai 2.23's Batches
        # resource is backed by the legacy API client.
        def create(self, **kwargs):
            calls.append(("create", kwargs))
            return SimpleNamespace(name="batches/gateway", state=SimpleNamespace(name="JOB_STATE_PENDING"))

        def get(self, **kwargs):
            calls.append(("get", kwargs))
            return SimpleNamespace(name="batches/gateway", state=SimpleNamespace(name="JOB_STATE_RUNNING"))

    class FakeClient:
        def __init__(self, **kwargs):
            client_kwargs.append(kwargs)
            self.batches = FakeBatches()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    monkeypatch.setattr(ai_gateway.genai, "Client", FakeClient)
    before = client.get("/usage").json()["calls_today"]

    submitted = batch_gateway.submit_generate_content_batch(
        model="gemini-3.1-flash-lite",
        inline_requests=[{"contents": [{"parts": [{"text": "test"}]}]}],
        display_name="test-batch",
    )
    assert submitted.name == "batches/gateway"
    assert client.get("/usage").json()["calls_today"] == before + 1

    checked = batch_gateway.get_generate_content_batch("batches/gateway")
    assert checked.name == "batches/gateway"
    assert client.get("/usage").json()["calls_today"] == before + 1
    assert [kind for kind, _ in calls] == ["create", "get"]
    assert len(client_kwargs) == 2
    for kwargs in client_kwargs:
        assert kwargs["http_options"]["retry_options"]["attempts"] == 1


def test_batch_gateway_setup_failure_before_create_does_not_consume_call(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fixture-key")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "true")

    class BrokenClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            raise RuntimeError("local SDK setup failed")

        def __exit__(self, *args):
            return None

    monkeypatch.setattr(ai_gateway.genai, "Client", BrokenClient)
    before = client.get("/usage").json()["calls_today"]

    with pytest.raises(HTTPException) as captured:
        batch_gateway.submit_generate_content_batch(
            model="gemini-3.1-flash-lite",
            inline_requests=[{"contents": [{"parts": [{"text": "test"}]}]}],
            display_name="test-batch",
        )

    assert captured.value.status_code == 502
    assert client.get("/usage").json()["calls_today"] == before
