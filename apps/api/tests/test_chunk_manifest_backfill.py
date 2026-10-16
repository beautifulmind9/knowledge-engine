import json
from pathlib import Path

from app.services.chunk_manifest_backfill import backfill_chunk_manifests


class SyntheticStore:
    def __init__(self, states, texts):
        self.states = states
        self.texts = texts
        self.reads = []
        self.inventory_calls = []

    def status_many(self, paths):
        self.inventory_calls.append(list(paths))
        return {path: self.states.get(path, "missing") for path in dict.fromkeys(paths)}

    def read_text(self, path):
        self.reads.append(path)
        return self.texts[path]


def chunk(source_id, chunk_id):
    return {"id": chunk_id, "source_id": source_id, "text": "synthetic"}


def test_backfill_stages_valid_manifests_once_and_skips_invalid_artifacts():
    sources = [
        {"id": "source_valid", "chunks_path": "chunks/valid.json"},
        {"id": "source_missing", "chunks_path": "chunks/missing.json"},
        {"id": "source_bad_json", "chunks_path": "chunks/bad.json"},
        {"id": "source_bad_ids", "chunks_path": "chunks/ids.json"},
        {"id": "source_mismatch", "chunks_path": "legacy/chunk.json"},
    ]
    states = {Path(item["chunks_path"]): "artifact" for item in sources if item["id"] != "source_missing"}
    texts = {
        Path("chunks/valid.json"): json.dumps([chunk("source_valid", "chunk_source_valid_001")]),
        Path("chunks/bad.json"): "{bad",
        Path("chunks/ids.json"): json.dumps([chunk("source_bad_ids", "duplicate"), chunk("source_bad_ids", "duplicate")]),
        Path("legacy/chunk.json"): json.dumps([chunk("source_other", "chunk_source_other_001")]),
    }
    store = SyntheticStore(states, texts)
    saves = []
    report = backfill_chunk_manifests(source_records=sources, store=store, persist=lambda: saves.append("saved"))
    assert report["updated_count"] == 1
    assert report["updated_source_ids"] == ["source_valid"]
    assert report["skipped_source_ids"] == {
        "missing": ["source_missing"], "other": [], "malformed": ["source_bad_json"],
        "invalid_chunks": ["source_bad_ids", "source_mismatch"]}
    assert len(store.inventory_calls) == 1 and len(store.reads) == 4 and saves == ["saved"]
    assert sources[0]["chunk_manifest"] == {
        "version": 1, "total_parts": 1, "chunk_ids": ["chunk_source_valid_001"]}


def test_backfill_is_idempotent_and_persists_only_once():
    source = {"id": "source_valid", "chunks_path": "chunks/valid.json"}
    path = Path("chunks/valid.json")
    store = SyntheticStore({path: "artifact"}, {path: json.dumps([chunk("source_valid", "chunk_source_valid_001")])})
    saves = []
    first = backfill_chunk_manifests(source_records=[source], store=store, persist=lambda: saves.append(1))
    second = backfill_chunk_manifests(source_records=[source], store=store, persist=lambda: saves.append(2))
    assert first["updated_count"] == 1 and second["updated_count"] == 0
    assert len(store.reads) == 1 and saves == [1]


def test_backfill_dry_run_and_shared_artifact_read_do_not_mutate_or_duplicate_gets():
    path=Path("chunks/shared.json")
    sources=[{"id":"source_valid","chunks_path":str(path)},
             {"id":"source_valid","chunks_path":str(path)}]
    store=SyntheticStore({path:"artifact"},{path:json.dumps([chunk("source_valid","chunk_source_valid_001")])})
    report=backfill_chunk_manifests(source_records=sources,store=store,apply=False)
    assert report["updated_count"]==2 and len(store.reads)==1
    assert all("chunk_manifest" not in item for item in sources)


def test_backfill_restores_staged_memory_on_optimistic_conflict():
    source = {"id": "source_valid", "chunks_path": "chunks/valid.json", "chunk_manifest": {"version": 9}}
    path = Path("chunks/valid.json")
    store = SyntheticStore({path: "artifact"}, {path: json.dumps([chunk("source_valid", "chunk_source_valid_001")])})
    def conflict():
        raise RuntimeError("optimistic conflict")
    try:
        backfill_chunk_manifests(source_records=[source], store=store, persist=conflict)
    except RuntimeError as error:
        assert "optimistic conflict" in str(error)
    else:
        raise AssertionError("conflict should fail closed")
    assert source["chunk_manifest"] == {"version": 9}
