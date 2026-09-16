from pathlib import Path

from app.db import mock_data as db
from app.routers import sources as sources_router
from app.services.source_structure import assign_outline_sections_to_chunks


def test_assign_outline_sections_to_existing_chunks_without_changing_text():
    chunks = [
        {"id": "c1", "start_word_index": 0, "text": "front matter"},
        {"id": "c2", "start_word_index": 120, "text": "chapter one text"},
        {"id": "c3", "start_word_index": 260, "text": "chapter two text"},
    ]
    annotated, summary = assign_outline_sections_to_chunks(
        chunks,
        page_word_counts=[100, 100, 100],
        sections=[
            {"title": "Chapter One", "page_number": 2, "level": 0},
            {"title": "Chapter Two", "page_number": 3, "level": 0},
        ],
    )

    assert annotated[0]["chapter_or_section"] is None
    assert annotated[1]["chapter_or_section"] == "Chapter One"
    assert annotated[2]["chapter_or_section"] == "Chapter Two"
    assert annotated[1]["text"] == "chapter one text"
    assert summary["annotated_chunk_count"] == 2
    assert summary["section_count"] == 2


def test_recover_structure_backfills_existing_chunks_and_assets(client, source, knowledge, monkeypatch):
    source_record, chunk = source
    stored = next(item for item in db.sources if item["id"] == source_record["id"])
    stored["file_type"] = ".pdf"

    # The normal Markdown fixture already carries the '# Focus' heading into both
    # the chunk and the extracted asset. This test is specifically for the legacy
    # PDF case we are repairing, where existing chunks/assets have no structure
    # metadata yet, so clear the fixture metadata before running recovery.
    stored_asset = next(item for item in db.knowledge_assets if item["id"] == knowledge["id"])
    stored_asset["chapter_or_section"] = None

    def fake_outline_recovery(file_path, chunks):
        assert Path(file_path).exists()
        chunks[0]["chapter_or_section"] = "Recovered chapter"
        chunks[0]["source_page_start"] = 7
        return chunks, {
            "outline_entry_count": 3,
            "annotated_chunk_count": 1,
            "unannotated_chunk_count": 0,
            "section_count": 1,
            "sections": ["Recovered chapter"],
        }

    monkeypatch.setattr(sources_router, "annotate_pdf_chunks_with_outline", fake_outline_recovery)
    response = client.post(f"/sources/{source_record['id']}/recover-structure")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["updated_asset_count"] == 1
    assert payload["structure_status"] == "pdf_outline_recovered"

    refreshed_chunk = client.get(f"/sources/{source_record['id']}/chunks").json()["items"][0]
    assert refreshed_chunk["chapter_or_section"] == "Recovered chapter"
    refreshed_asset = next(item for item in db.knowledge_assets if item["id"] == knowledge["id"])
    assert refreshed_asset["chapter_or_section"] == "Recovered chapter"


def test_recover_structure_preserves_existing_asset_section(client, source, knowledge, monkeypatch):
    source_record, _ = source
    stored = next(item for item in db.sources if item["id"] == source_record["id"])
    stored["file_type"] = ".pdf"

    stored_asset = next(item for item in db.knowledge_assets if item["id"] == knowledge["id"])
    stored_asset["chapter_or_section"] = "Existing section"

    def fake_outline_recovery(file_path, chunks):
        chunks[0]["chapter_or_section"] = "Recovered chapter"
        return chunks, {
            "outline_entry_count": 1,
            "annotated_chunk_count": 1,
            "unannotated_chunk_count": 0,
            "section_count": 1,
            "sections": ["Recovered chapter"],
        }

    monkeypatch.setattr(sources_router, "annotate_pdf_chunks_with_outline", fake_outline_recovery)
    response = client.post(f"/sources/{source_record['id']}/recover-structure")
    assert response.status_code == 200, response.text
    assert response.json()["updated_asset_count"] == 0
    refreshed_asset = next(item for item in db.knowledge_assets if item["id"] == knowledge["id"])
    assert refreshed_asset["chapter_or_section"] == "Existing section"


def test_recover_structure_rejects_non_pdf_source(client, source):
    source_record, _ = source
    response = client.post(f"/sources/{source_record['id']}/recover-structure")
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]
