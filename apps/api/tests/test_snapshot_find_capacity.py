"""Snapshot Find admits complete lexical matches without weakening resource limits.

Synthetic, offline and provider-free. Indexed read safeguards remain unchanged.
"""
import pytest
from fastapi import HTTPException

from app.db import mock_data as db
from app.services import evidence_safety as safety
from app.services import knowledge_extraction as extraction


def _install_scope(monkeypatch, *, total=1491, matched=14):
    libraries = [{"id": "marketing", "name": "Marketing"},
                 {"id": "other", "name": "Other"}]
    sources = [
        {"id": f"source_{index}", "library_id": "marketing", "title": "Synthetic"}
        for index in range(11)
    ] + [{"id": "foreign", "library_id": "other", "title": "Foreign"}]
    items = []
    for index in range(total):
        # Include a match after item 1,000 to catch premature scope slicing.
        hit = index < matched - 1 or index == total - 1
        items.append({
            "id": f"asset_{index}",
            "source_id": f"source_{index % 11}",
            "chunk_id": f"chunk_{index}",
            "asset_type": "principle",
            "title": "Social media audience" if hit else f"Unrelated topic {index}",
            "what_it_says": "Social media audience relationships." if hit else "An unrelated observation.",
            "evidence": f"Independent synthetic evidence {index}",
            "keywords": ["social", "media"] if hit else ["unrelated"],
            "confidence_score": 4,
            "active": True,
        })
    # Install the same list references used by the imported retrieval module
    # and its source-validation helpers without mutating global test state.
    monkeypatch.setattr(db, "libraries", libraries)
    monkeypatch.setattr(db, "sources", sources)
    monkeypatch.setattr(db, "knowledge_assets", items)
    monkeypatch.setattr(extraction, "libraries", libraries)
    monkeypatch.setattr(extraction, "sources", sources)
    monkeypatch.setattr(extraction, "knowledge_assets", items)
    monkeypatch.setattr(extraction.authority, "coordinator", lambda: None)
    return items


def test_snapshot_find_1491_assets_admits_complete_small_match_set(monkeypatch):
    items = _install_scope(monkeypatch, total=1491, matched=14)
    results = extraction.search_knowledge_assets(
        "social media", library_id="marketing", limit=None)
    assert len(results) == 14
    expected = set(range(13)) | {1490}
    assert {r["id"] for r in results} == {f"asset_{i}" for i in expected}
    assert {r["source_id"] for r in results} == {
        f"source_{i % 11}" for i in expected
    }
    for result in results:
        source = items[int(result["id"].removeprefix("asset_"))]
        assert result["evidence"] == source["evidence"]
        assert set(result["matched_terms"]) == {"social", "media"}
    assert extraction.search_knowledge_assets(
        "social media", library_id="marketing", limit=10) == results[:10]


def test_snapshot_find_over_1000_real_matches_rejects_without_truncation(monkeypatch):
    _install_scope(monkeypatch, total=1491, matched=1001)
    with pytest.raises(HTTPException) as error:
        extraction.search_knowledge_assets("social media", library_id="marketing", limit=10)
    assert error.value.status_code == 413
    assert error.value.headers["X-KE-Interruption-Category"] == "evidence_capacity_exceeded"
    assert "No evidence was truncated" in error.value.detail


def test_snapshot_find_matched_byte_budget_still_rejects(monkeypatch):
    _install_scope(monkeypatch, total=1491, matched=1)
    monkeypatch.setattr(safety, "MAX_CANDIDATE_BYTES", 100)
    with pytest.raises(HTTPException) as error:
        extraction.search_knowledge_assets("social media", library_id="marketing")
    assert error.value.status_code == 413
    assert error.value.headers["X-KE-Interruption-Category"] == "evidence_capacity_exceeded"


def test_snapshot_find_does_not_import_foreign_library_assets(monkeypatch):
    items = _install_scope(monkeypatch, total=1491, matched=2)
    items.append({**items[0], "id": "foreign_asset", "source_id": "foreign", "chunk_id": "foreign_chunk"})
    results = extraction.search_knowledge_assets(
        "social media", library_id="marketing", limit=None)
    assert len(results) == 2
    assert "foreign_asset" not in {r["id"] for r in results}
