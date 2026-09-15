from app.db import mock_data as db
from app.services import source_interpretation
from app.services.knowledge_extraction import persist_state
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
    assert "synthetic provider failure" in result["stopped_reason"]
    pending = [job for job in db.extraction_jobs if job["chunk_id"] == chunks[2]["id"]]
    assert len(pending) == 1
    assert pending[0]["status"] == "pending_ai"
