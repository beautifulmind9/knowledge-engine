from copy import deepcopy
from unittest.mock import Mock

import pytest

from app.db import mock_data
from app.db import persistence as persistence_facade
from app.db.persistence import StateMutationConflict
from app.persistence.postgres import StaleStateWriteError, STALE_WRITE_MESSAGE
from app.persistence.reconciliation import StateReconciliationConflict, merge_state_snapshots


def snapshot(*, sources=(), jobs=(), assets=(), usage=None):
    return {
        "schema_version": 2,
        "libraries": [{"id": "library_a", "name": "Research"}],
        "sources": deepcopy(list(sources)),
        "extraction_jobs": deepcopy(list(jobs)),
        "knowledge_assets": deepcopy(list(assets)),
        "outputs": [],
        "usage": deepcopy(usage or {}),
    }


class RacingStore:
    def __init__(self, base, latest, stale_count=1):
        self.latest = deepcopy(latest)
        self._loaded_snapshot = deepcopy(base)
        self.stale_count = stale_count
        self.save_calls = []

    @property
    def loaded_snapshot(self):
        return deepcopy(self._loaded_snapshot)

    def load(self):
        self._loaded_snapshot = deepcopy(self.latest)
        return deepcopy(self.latest)

    def save(self, state):
        self.save_calls.append(deepcopy(state))
        if len(self.save_calls) <= self.stale_count:
            raise StaleStateWriteError(STALE_WRITE_MESSAGE)
        self.latest = deepcopy(state)
        self._loaded_snapshot = deepcopy(state)


@pytest.fixture
def live_state(monkeypatch):
    original = {
        "libraries": deepcopy(mock_data.libraries), "sources": deepcopy(mock_data.sources),
        "extraction_jobs": deepcopy(mock_data.extraction_jobs),
        "knowledge_assets": deepcopy(mock_data.knowledge_assets),
        "outputs": deepcopy(mock_data.outputs), "usage": deepcopy(mock_data.usage),
    }
    mock_data.libraries[:] = [{"id": "library_a", "name": "Research"}]
    mock_data.sources[:] = [{"id": "source_a", "title": "Before", "processing_status": "knowledge_interpreting"}]
    mock_data.extraction_jobs[:] = []
    mock_data.knowledge_assets[:] = []
    mock_data.outputs[:] = []
    mock_data.usage.clear()
    monkeypatch.setattr(persistence_facade, "PERSISTENCE_MODE", "local")
    yield mock_data
    for key in ("libraries", "sources", "extraction_jobs", "knowledge_assets", "outputs"):
        getattr(mock_data, key)[:] = original[key]
    mock_data.usage.clear()
    mock_data.usage.update(original["usage"])


def save_live(store, live):
    return persistence_facade.save_state(
        live.libraries, live.sources, live.extraction_jobs, live.knowledge_assets,
    )


def test_source_creation_rebases_over_concurrent_preparation_progress(monkeypatch, live_state):
    base = snapshot(sources=[{"id": "source_a", "title": "Before", "processing_status": "uploaded"}])
    concurrent = snapshot(
        sources=[{"id": "source_a", "title": "Before", "processing_status": "knowledge_interpreting"}],
        jobs=[{"id": "job_a", "source_id": "source_a", "status": "completed"}],
        assets=[{"id": "asset_a", "source_id": "source_a", "chunk_id": "chunk_a"}],
    )
    store = RacingStore(base, concurrent)
    monkeypatch.setattr(persistence_facade, "get_state_store", lambda: store)
    created = {"id": "source_new", "title": "New upload", "processing_status": "not_started"}
    live_state.sources.append(created)

    save_live(store, live_state)

    persisted = store.latest
    assert {item["id"] for item in persisted["sources"]} == {"source_a", "source_new"}
    assert persisted["sources"][0]["processing_status"] == "knowledge_interpreting"
    assert persisted["extraction_jobs"][0]["id"] == "job_a"
    assert persisted["knowledge_assets"][0]["id"] == "asset_a"
    assert len(store.save_calls) == 2


def test_two_source_creations_from_same_revision_both_survive():
    base = snapshot()
    local = deepcopy(base)
    latest = deepcopy(base)
    local["sources"].append({"id": "source_local", "title": "Local"})
    latest["sources"].append({"id": "source_remote", "title": "Remote"})

    merged = merge_state_snapshots(base, local, latest)

    assert {source["id"] for source in merged["sources"]} == {"source_local", "source_remote"}


def test_progress_for_source_a_and_creation_of_source_b_both_survive():
    base = snapshot(sources=[{"id": "source_a", "title": "A", "processing_status": "uploaded"}])
    local = deepcopy(base)
    latest = deepcopy(base)
    local["sources"][0]["processing_status"] = "knowledge_interpreting"
    local["extraction_jobs"].append({"id": "job_a", "source_id": "source_a", "status": "running"})
    latest["sources"].append({"id": "source_b", "title": "B", "processing_status": "not_started"})

    merged = merge_state_snapshots(base, local, latest)

    by_id = {source["id"]: source for source in merged["sources"]}
    assert by_id["source_a"]["processing_status"] == "knowledge_interpreting"
    assert by_id["source_b"]["title"] == "B"
    assert merged["extraction_jobs"][0]["status"] == "running"


def test_upload_publication_rebases_over_another_sources_progress(monkeypatch, live_state):
    second = {"id": "source_b", "title": "Other", "processing_status": "uploaded"}
    live_state.sources.append(deepcopy(second))
    base = snapshot(sources=[
        {"id": "source_a", "title": "Before", "processing_status": "not_started"}, second,
    ])
    concurrent = snapshot(sources=[
        {"id": "source_a", "title": "Before", "processing_status": "not_started"},
        {"id": "source_b", "title": "Other", "processing_status": "knowledge_interpreting"},
    ], jobs=[{"id": "job_b", "source_id": "source_b", "status": "running"}])
    store = RacingStore(base, concurrent)
    monkeypatch.setattr(persistence_facade, "get_state_store", lambda: store)
    live_state.sources[0].update(file_name="book.pdf", file_path="uploads/new-object.pdf", processing_status="uploaded")

    save_live(store, live_state)

    by_id = {source["id"]: source for source in store.latest["sources"]}
    assert by_id["source_a"]["file_path"] == "uploads/new-object.pdf"
    assert by_id["source_b"]["processing_status"] == "knowledge_interpreting"
    assert store.latest["extraction_jobs"][0]["id"] == "job_b"


def test_independent_mutations_merge_and_concurrent_allowance_increments_sum():
    base = snapshot(
        sources=[{"id": "source_a", "title": "A"}, {"id": "source_b", "title": "B"}],
        usage={"day": "2026-10-14", "calls": 10},
    )
    local = deepcopy(base)
    latest = deepcopy(base)
    local["sources"][0]["title"] = "A updated"
    local["usage"]["calls"] = 11
    latest["sources"][1]["title"] = "B updated"
    latest["usage"]["calls"] = 11

    merged = merge_state_snapshots(base, local, latest)

    by_id = {source["id"]: source for source in merged["sources"]}
    assert by_id["source_a"]["title"] == "A updated"
    assert by_id["source_b"]["title"] == "B updated"
    assert merged["usage"]["calls"] == 12


def test_job_progress_and_identity_edit_to_distinct_fields_merge():
    base = snapshot(
        sources=[{"id": "source_a", "title": "Filename", "author": "", "processing_status": "knowledge_interpreting"}],
        jobs=[{"id": "job_a", "source_id": "source_a", "status": "running", "updated_at": "t1"}],
    )
    local = deepcopy(base)
    latest = deepcopy(base)
    local["sources"][0].update(title="Material title", author="Author", title_origin="user_confirmed")
    latest["extraction_jobs"][0].update(status="completed", updated_at="t2")

    merged = merge_state_snapshots(base, local, latest)

    assert merged["sources"][0]["title"] == "Material title"
    assert merged["sources"][0]["author"] == "Author"
    assert merged["sources"][0]["title_origin"] == "user_confirmed"
    assert merged["extraction_jobs"][0]["status"] == "completed"
    assert merged["extraction_jobs"][0]["updated_at"] == "t2"


def test_reconciliation_is_bounded_after_repeated_stale_conflicts(monkeypatch, live_state):
    base = snapshot(sources=[{"id": "source_a", "title": "Before", "processing_status": "uploaded"}])
    store = RacingStore(base, base, stale_count=10)
    monkeypatch.setattr(persistence_facade, "get_state_store", lambda: store)
    live_state.sources.append({"id": "source_new", "title": "New", "processing_status": "not_started"})

    with pytest.raises(StateMutationConflict, match="changed repeatedly.*Reload and try again"):
        save_live(store, live_state)

    assert len(store.save_calls) == 3  # initial save plus at most two reconciliations
    assert [source["id"] for source in live_state.sources] == ["source_a"]


def test_same_field_conflict_fails_closed_without_overwriting_persisted_state(monkeypatch, live_state):
    base = snapshot(sources=[{"id": "source_a", "title": "Before", "processing_status": "uploaded"}])
    latest = snapshot(sources=[{"id": "source_a", "title": "Concurrent", "processing_status": "uploaded"}])
    store = RacingStore(base, latest)
    monkeypatch.setattr(persistence_facade, "get_state_store", lambda: store)
    live_state.sources[0]["title"] = "Local change"

    with pytest.raises(StateMutationConflict, match="could not be reconciled safely"):
        save_live(store, live_state)

    assert live_state.sources[0]["title"] == "Concurrent"
    assert store.latest["sources"][0]["title"] == "Concurrent"
    assert len(store.save_calls) == 1


@pytest.mark.parametrize("delete_side", ["local", "latest"])
def test_delete_vs_update_of_same_record_fails_closed(delete_side):
    base = snapshot(sources=[{"id": "source_a", "title": "A", "processing_status": "uploaded"}])
    local = deepcopy(base)
    latest = deepcopy(base)
    if delete_side == "local":
        local["sources"].clear()
        latest["sources"][0]["processing_status"] = "knowledge_interpreting"
    else:
        local["sources"][0]["title"] = "A edited"
        latest["sources"].clear()

    with pytest.raises(StateReconciliationConflict):
        merge_state_snapshots(base, local, latest)


def test_delete_of_one_record_preserves_independent_creation():
    base = snapshot(sources=[{"id": "source_delete", "title": "Remove me"}])
    local = deepcopy(base)
    latest = deepcopy(base)
    local["sources"].clear()
    latest["sources"].append({"id": "source_new", "title": "New material"})

    merged = merge_state_snapshots(base, local, latest)

    assert merged["sources"] == [{"id": "source_new", "title": "New material"}]


def test_collection_mutation_preserves_independent_addition():
    base = snapshot(jobs=[{"id": "job_remove", "source_id": "source_a", "status": "failed"}])
    local = deepcopy(base)
    latest = deepcopy(base)
    local["extraction_jobs"].clear()
    latest["extraction_jobs"].append({"id": "job_other", "source_id": "source_b", "status": "pending_ai"})

    merged = merge_state_snapshots(base, local, latest)

    assert merged["extraction_jobs"] == [{"id": "job_other", "source_id": "source_b", "status": "pending_ai"}]


def test_concurrent_collection_reorders_fail_closed_instead_of_choosing_a_winner():
    base = snapshot(sources=[
        {"id": "source_a", "title": "A"},
        {"id": "source_b", "title": "B"},
        {"id": "source_c", "title": "C"},
    ])
    local = deepcopy(base)
    latest = deepcopy(base)
    local["sources"] = [local["sources"][1], local["sources"][0], local["sources"][2]]
    latest["sources"] = [latest["sources"][0], latest["sources"][2], latest["sources"][1]]

    with pytest.raises(StateReconciliationConflict):
        merge_state_snapshots(base, local, latest)


def test_persistence_reconciliation_does_not_repeat_external_provider_work(monkeypatch, live_state):
    base = snapshot(sources=[{"id": "source_a", "title": "Before", "processing_status": "uploaded"}])
    latest = snapshot(sources=[{"id": "source_a", "title": "Before", "processing_status": "knowledge_interpreting"}])
    store = RacingStore(base, latest)
    monkeypatch.setattr(persistence_facade, "get_state_store", lambda: store)
    provider = Mock(return_value={"accepted": True})

    result = provider()
    live_state.sources.append({"id": "source_new", "title": "New", "processing_status": "not_started"})
    save_live(store, live_state)

    assert result == {"accepted": True}
    provider.assert_called_once_with()
    assert len(store.save_calls) == 2


def test_record_merge_is_idempotent_for_same_local_addition():
    base = snapshot()
    local = deepcopy(base)
    latest = deepcopy(base)
    created = {"id": "source_new", "title": "New", "processing_status": "not_started"}
    local["sources"].append(created)
    latest["sources"].append(deepcopy(created))

    merged = merge_state_snapshots(base, local, latest)

    assert merged["sources"].count(created) == 1


def test_conflicting_additions_with_same_id_are_not_silently_overwritten():
    base = snapshot()
    local = deepcopy(base)
    latest = deepcopy(base)
    local["sources"].append({"id": "source_same", "title": "Local"})
    latest["sources"].append({"id": "source_same", "title": "Other"})

    with pytest.raises(StateReconciliationConflict):
        merge_state_snapshots(base, local, latest)
