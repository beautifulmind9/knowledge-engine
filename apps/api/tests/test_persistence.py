"""Characterize snapshot storage independently of domain validation and providers."""
from copy import deepcopy
import json
import sqlite3

import pytest

from app.db import mock_data as db
from app.db import persistence
from app.persistence.contracts import StateStore
from app.persistence.sqlite import SQLiteStateStore


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "storage"
    return SQLiteStateStore(root, root / "state.json", root / "knowledge.sqlite3", tmp_path / "api")


@pytest.fixture
def snapshot():
    asset = {"id": "asset_old", "source_id": "source_one", "chunk_id": "chunk_one",
             "active": False, "superseded_by_job_id": "job_new", "extraction_version": 1,
             "evidence": "Café practice", "keywords": ["practice", "learning"]}
    provenance = [{"canonical_asset": deepcopy(asset), "source_ids": ["source_one"],
                   "evidence_trail": [{"source_id": "source_one", "chunk_id": "chunk_one",
                                       "asset_id": "asset_old", "evidence": "Café practice"}]}]
    return {"libraries": [{"id": "library_one"}],
            "sources": [{"id": "source_one", "library_id": "library_one"}],
            "extraction_jobs": [{"id": "job_new", "status": "completed"}],
            "knowledge_assets": [asset, {**asset, "id": "asset_new", "active": True,
                                         "superseded_by_job_id": None, "extraction_version": 2}],
            "outputs": [{"id": "output_one", "root_output_id": "output_one", "parent_output_id": None,
                         "version": 1, "knowledge_snapshot": deepcopy(provenance)},
                        {"id": "output_two", "root_output_id": "output_one", "parent_output_id": "output_one",
                         "version": 2, "knowledge_snapshot": deepcopy(provenance)}],
            "usage": {"day": "2026-09-21", "calls": 7, "paused": True, "reason": "quota"},
            "schema_version": 2}


def payload_rows(store):
    with sqlite3.connect(store.db_path) as conn:
        return conn.execute("SELECT id, payload FROM state").fetchall()


def test_complete_snapshot_round_trip(store, snapshot):
    contract: StateStore = store
    original = deepcopy(snapshot)
    assert contract.save(snapshot) is None
    assert snapshot == original
    assert contract.load() == original
    assert payload_rows(store) == [(1, json.dumps(original, ensure_ascii=False))]
    snapshot["outputs"][0]["knowledge_snapshot"].clear()
    reopened = SQLiteStateStore(store.storage_root, store.state_path, store.db_path, store.api_root)
    assert reopened.load() == original


def test_facade_preserves_complete_snapshot_and_collection_identity(store, snapshot, monkeypatch):
    for name, value in (("STORAGE_ROOT", store.storage_root), ("STATE_PATH", store.state_path),
                        ("DB_PATH", store.db_path), ("API_ROOT", store.api_root)):
        monkeypatch.setattr(persistence, name, value)
    collections = (db.libraries, db.sources, db.extraction_jobs, db.knowledge_assets, db.outputs, db.usage)
    for name in ("libraries", "sources", "extraction_jobs", "knowledge_assets", "outputs"):
        getattr(db, name).extend(deepcopy(snapshot[name]))
    db.usage.update(snapshot["usage"])
    assert persistence.save_state(db.libraries, db.sources, db.extraction_jobs, db.knowledge_assets) is None
    assert persistence.load_state() == snapshot
    assert all(before is after for before, after in zip(collections,
               (db.libraries, db.sources, db.extraction_jobs, db.knowledge_assets, db.outputs, db.usage)))


def test_empty_store_and_existing_sqlite_precedence(store, snapshot):
    assert store.load() is None
    assert payload_rows(store) == []
    store.save(snapshot)
    store.state_path.write_text("{invalid legacy JSON", encoding="utf-8")
    assert store.load() == snapshot
    assert store.state_path.read_text(encoding="utf-8") == "{invalid legacy JSON"


def test_legacy_migration_preserves_original_and_serialization(store, snapshot):
    store.storage_root.mkdir()
    snapshot["sources"][0].update(file_path="storage/uploads/source.pdf",
                                  extracted_text_path="old/source.txt",
                                  chunks_path=str(store.storage_root / "chunks/source.json"))
    original = json.dumps(snapshot, indent=4, ensure_ascii=False).encode("utf-8")
    store.state_path.write_bytes(original)
    expected = deepcopy(snapshot)
    expected["sources"][0].update(file_path=str(store.storage_root / "uploads/source.pdf"),
                                  extracted_text_path=str(store.api_root / "old/source.txt"))
    assert store.load() == expected
    assert store.state_path.read_bytes() == original
    assert payload_rows(store) == [(1, json.dumps(expected))]
    assert store.load() == expected


@pytest.mark.parametrize("legacy", ["{bad JSON", '{"libraries": {}}'])
def test_corrupt_legacy_fails_without_replacement(store, legacy):
    store.storage_root.mkdir()
    store.state_path.write_text(legacy, encoding="utf-8")
    error = json.JSONDecodeError if legacy == "{bad JSON" else RuntimeError
    with pytest.raises(error):
        store.load()
    assert store.state_path.read_text(encoding="utf-8") == legacy
    assert payload_rows(store) == []


def test_corrupt_sqlite_payload_does_not_fall_back_to_legacy(store, snapshot):
    store.save(snapshot)
    store.state_path.write_text(json.dumps(snapshot), encoding="utf-8")
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE state SET payload = ?", ("{bad JSON",))
    with pytest.raises(json.JSONDecodeError):
        store.load()
    assert payload_rows(store) == [(1, "{bad JSON")]


def test_failed_sqlite_write_rolls_back_prior_snapshot(store, snapshot):
    store.save(snapshot)
    original_rows = payload_rows(store)
    # Fail after SQLite has applied the update, exercising transaction rollback.
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("""CREATE TRIGGER reject_snapshot AFTER UPDATE ON state
                        BEGIN SELECT RAISE(FAIL, 'simulated write failure'); END""")
    changed = deepcopy(snapshot)
    changed["usage"]["calls"] += 1
    with pytest.raises(sqlite3.IntegrityError, match="simulated write failure"):
        store.save(changed)
    assert payload_rows(store) == original_rows
    assert store.load() == snapshot


def test_serialization_failure_preserves_prior_snapshot(store, snapshot):
    store.save(snapshot)
    changed = {**snapshot, "invalid": object()}
    with pytest.raises(TypeError):
        store.save(changed)
    assert store.load() == snapshot
