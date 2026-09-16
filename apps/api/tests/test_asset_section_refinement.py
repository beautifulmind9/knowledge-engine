from app.db import mock_data as db
from app.routers import structure as structure_router
from app.services.source_structure import assign_outline_sections_to_assets_from_evidence


def test_evidence_refinement_corrects_cross_boundary_chunk_label():
    assets = [
        {
            "id": "a1",
            "evidence": "My favorite solution is to talk in circles, which means that you begin lecturing at normal volume.",
            "chapter_or_section": "Answering student questions",
        }
    ]
    summary = assign_outline_sections_to_assets_from_evidence(
        assets,
        page_texts=[
            "Questions from students and how to answer them.",
            "My favorite solution is to talk in circles, which means that you begin lecturing at normal volume.",
        ],
        sections=[
            {"title": "Answering student questions", "page_number": 1, "level": 0},
            {"title": "How to recover the crowd after an exercise", "page_number": 2, "level": 0},
        ],
    )

    assert assets[0]["chapter_or_section"] == "How to recover the crowd after an exercise"
    assert summary["evidence_matched_asset_count"] == 1
    assert summary["evidence_updated_asset_count"] == 1


def test_evidence_refinement_leaves_ambiguous_cross_section_matches_unchanged():
    assets = [
        {
            "id": "a1",
            "evidence": "Use the same exact grounded phrase for this example.",
            "chapter_or_section": "Chapter One",
        }
    ]
    summary = assign_outline_sections_to_assets_from_evidence(
        assets,
        page_texts=[
            "Use the same exact grounded phrase for this example.",
            "Use the same exact grounded phrase for this example.",
        ],
        sections=[
            {"title": "Chapter One", "page_number": 1, "level": 0},
            {"title": "Chapter Two", "page_number": 2, "level": 0},
        ],
    )

    assert assets[0]["chapter_or_section"] == "Chapter One"
    assert summary["evidence_ambiguous_asset_count"] == 1
    assert summary["evidence_updated_asset_count"] == 0


def test_refine_asset_sections_endpoint_persists_metadata_only(client, source, knowledge, monkeypatch):
    source_record, _ = source
    stored_source = next(item for item in db.sources if item["id"] == source_record["id"])
    stored_source["file_type"] = ".pdf"
    stored_asset = next(item for item in db.knowledge_assets if item["id"] == knowledge["id"])
    original_claim = stored_asset["what_it_says"]
    original_evidence = stored_asset["evidence"]
    stored_asset["chapter_or_section"] = "Coarse chunk section"

    def fake_refinement(file_path, assets):
        assert len(assets) == 1
        assets[0]["chapter_or_section"] = "Evidence section"
        return {
            "evidence_matched_asset_count": 1,
            "evidence_updated_asset_count": 1,
            "evidence_ambiguous_asset_count": 0,
            "evidence_unmatched_asset_count": 0,
        }

    monkeypatch.setattr(structure_router, "annotate_pdf_assets_with_outline_from_evidence", fake_refinement)
    response = client.post(f"/sources/{source_record['id']}/refine-asset-sections")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["updated_asset_count"] == 1
    assert payload["structure_status"] == "pdf_evidence_refined"

    refreshed = next(item for item in db.knowledge_assets if item["id"] == knowledge["id"])
    assert refreshed["chapter_or_section"] == "Evidence section"
    assert refreshed["what_it_says"] == original_claim
    assert refreshed["evidence"] == original_evidence
