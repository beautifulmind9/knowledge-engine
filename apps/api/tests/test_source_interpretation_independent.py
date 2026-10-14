from fastapi import HTTPException
import pytest

from app.db import mock_data as db
from app.services import source_interpretation
from app.services.knowledge_extraction import complete_extraction_job, create_extraction_job, get_extraction_job, mark_extraction_job_failed, persist_state
from app.services.text_chunking import save_chunks


def _install_chunks(source, count=3):
    s, _ = source
    chunks = [
        {
            "id": f"chunk_independent_{index}",
            "source_id": s["id"],
            "text": f"Chunk {index} contains reusable knowledge {index}.",
            "chapter_or_section": f"Section {index}",
        }
        for index in range(count)
    ]
    db.sources[0]["chunks_path"] = save_chunks(s["id"], chunks)
    persist_state()
    return s, chunks


def test_source_interpretation_calls_single_chunk_runner_once_per_chunk(source, monkeypatch):
    s, chunks = _install_chunks(source, count=3)
    calls = []

    def fake_run(job_id):
        job = next(job for job in db.extraction_jobs if job["id"] == job_id)
        calls.append(job["chunk_id"])
        job["status"] = "completed"
        job["asset_count"] = 0
        return {"job": job, "assets": []}

    monkeypatch.setattr(source_interpretation, "run_gemini_knowledge_extraction", fake_run)

    result = source_interpretation.interpret_source(s["id"], max_chunks=3)

    assert calls == [chunk["id"] for chunk in chunks]
    assert result["processed_this_run"] == 3
    assert result["stopped_reason"] is None
    assert result["progress"]["completed_chunks"] == 3


def test_source_interpretation_stops_after_first_failed_independent_request(source, monkeypatch):
    s, chunks = _install_chunks(source, count=3)
    calls = []

    def fake_run(job_id):
        job = next(job for job in db.extraction_jobs if job["id"] == job_id)
        calls.append(job["chunk_id"])
        if len(calls) == 2:
            job["status"] = "failed"
            raise RuntimeError("synthetic provider failure")
        job["status"] = "completed"
        job["asset_count"] = 0
        return {"job": job, "assets": []}

    monkeypatch.setattr(source_interpretation, "run_gemini_knowledge_extraction", fake_run)

    result = source_interpretation.interpret_source(s["id"], max_chunks=3)

    assert calls == [chunks[0]["id"], chunks[1]["id"]]
    assert result["processed_this_run"] == 1
    assert result["stopped_reason"] == "Interpretation stopped after an unexpected preparation error."
    assert result["interruption_category"] == "preparation_failed"
    pending = [job for job in db.extraction_jobs if job["chunk_id"] == chunks[2]["id"]]
    assert len(pending) == 1
    assert pending[0]["status"] == "pending_ai"


def test_explicit_build_retries_failed_part_without_reset_and_skips_completed_parts(client, source, monkeypatch):
    s, chunks = _install_chunks(source, count=3)
    calls = []

    def fake_run(job_id):
        job = get_extraction_job(job_id)
        calls.append((job_id, job['chunk_id']))
        if len(calls) == 2:
            mark_extraction_job_failed(job_id, 'Synthetic provider failure')
            raise RuntimeError('Synthetic provider failure')
        return complete_extraction_job(job_id, [])

    monkeypatch.setattr(source_interpretation, 'run_gemini_knowledge_extraction', fake_run)
    path = f"/sources/{s['id']}/interpret?max_chunks=1"
    assert client.post(path).json()['processed_this_run'] == 1
    assert client.post(path).json()['stopped_reason']
    failed_id = calls[-1][0]
    facts = client.get(f"/sources/{s['id']}/summary").json()
    assert facts['attention_category'] == 'build_stopped'
    assert facts['next_action'] == 'continue_building'
    assert facts['recovery'][0]['allowed']  # Permitted reset does not mean required reset.

    assert client.post(path).json()['processed_this_run'] == 1
    assert [part for _, part in calls] == [chunks[0]['id'], chunks[1]['id'], chunks[1]['id']]
    assert calls[-1][0] != failed_id
    assert get_extraction_job(failed_id)['status'] == 'failed'
    assert get_extraction_job(calls[-1][0])['extraction_version'] == 2
    facts = client.get(f"/sources/{s['id']}/summary").json()
    assert facts['completed_parts'] == 2 and facts['attention_category'] is None
    assert not db.usage  # The test uses a synthetic runner, never the provider.
def test_provider_503_is_returned_as_safe_known_interruption_without_retry(client, source, monkeypatch):
    s, _ = _install_chunks(source, count=3)
    calls = []

    def fake_run(job_id):
        calls.append(job_id)
        raise HTTPException(502, "synthetic safe provider failure",
                            headers={"X-KE-Interruption-Category":"provider_unavailable"})

    monkeypatch.setattr(source_interpretation, "run_gemini_knowledge_extraction", fake_run)
    result = client.post(f"/sources/{s['id']}/interpret?max_chunks=1")
    assert result.status_code == 200
    assert result.json()["processed_this_run"] == 0
    assert result.json()["interruption_category"] == "provider_unavailable"
    assert len(calls) == 1
    assert "synthetic safe provider failure" not in result.text
    summary = client.get(f"/sources/{s['id']}/summary").json()
    assert summary["attention_category"] == "build_stopped"
    assert summary["completed_parts"] == 0


@pytest.mark.parametrize('completed_before_timeout', [0, 3, 5])
def test_confirmed_timeout_persists_and_explicit_continuation_skips_completed_parts(
    client, source, knowledge, monkeypatch, completed_before_timeout
):
    s, chunks = _install_chunks(source, count=6)
    completed_ids = []
    for chunk in chunks[:completed_before_timeout]:
        job = create_extraction_job(source_id=s['id'], chunk_id=chunk['id'])
        complete_extraction_job(job['id'], [])
        completed_ids.append(chunk['id'])

    calls = []
    timed_out = False

    def fake_run(job_id):
        nonlocal timed_out
        job = get_extraction_job(job_id)
        calls.append((job_id, job['chunk_id']))
        if job['chunk_id'] == chunks[completed_before_timeout]['id'] and not timed_out:
            timed_out = True
            mark_extraction_job_failed(job_id, 'Synthetic timeout diagnostic')
            raise HTTPException(502, 'Synthetic timeout diagnostic',
                                headers={'X-KE-Interruption-Category': 'request_timed_out'})
        return complete_extraction_job(job_id, [])

    monkeypatch.setattr(source_interpretation, 'run_gemini_knowledge_extraction', fake_run)
    path = f"/sources/{s['id']}/interpret?max_chunks=1"
    for _ in range(completed_before_timeout + 1):
        result = client.post(path)
        assert result.status_code == 200
        if result.json()['stopped_reason']:
            assert result.json()['interruption_category'] == 'request_timed_out'
            break
        assert result.json()['processed_this_run'] == 1
    assert timed_out

    persisted = client.get(f"/sources/{s['id']}/summary").json()  # Same persisted state a reopened page reads.
    assert persisted['readiness'] == ('partly_ready' if completed_before_timeout else 'ready_to_build')
    assert persisted['next_action'] == ('continue_building' if completed_before_timeout else 'build_knowledge')
    assert persisted['attention_category'] == 'build_stopped'
    assert persisted['completed_parts'] == completed_before_timeout
    failed_attempt_id = calls[-1][0]
    assert get_extraction_job(failed_attempt_id)['status'] == 'failed'
    assert any(asset['id'] == knowledge['id'] and asset.get('active', True) for asset in db.knowledge_assets)

    # A new explicit call is the continuation. The server skips completed chunks,
    # gives the failed chunk a fresh attempt, then processes the remaining chunks.
    before_continue = len(calls)
    for _ in range(6 - completed_before_timeout):
        resumed = client.post(path)
        assert resumed.status_code == 200
        assert resumed.json()['processed_this_run'] == 1
        assert resumed.json()['stopped_reason'] is None

    continued_chunks = [chunk_id for _, chunk_id in calls[before_continue:]]
    assert continued_chunks == [chunk['id'] for chunk in chunks[completed_before_timeout:]]
    assert not any(chunk_id in completed_ids for chunk_id in continued_chunks)
    assert sum(chunk_id == chunks[completed_before_timeout]['id'] for _, chunk_id in calls) == 2
    assert calls[before_continue][0] != failed_attempt_id
    assert get_extraction_job(calls[before_continue][0])['extraction_version'] == 2
    ready = client.get(f"/sources/{s['id']}/summary").json()
    assert ready['readiness'] == 'ready'
    assert ready['completed_parts'] == 6
    assert ready['has_usable_knowledge'] is True
    assert any(asset['id'] == knowledge['id'] and asset.get('active', True) for asset in db.knowledge_assets)
