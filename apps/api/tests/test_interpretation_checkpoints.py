import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.db import mock_data
from app.db import persistence as persistence_facade
from app.persistence.postgres import StaleStateWriteError
from app.persistence.reconciliation import merge_state_snapshots
from app.persistence.factory import STORAGE_ROOT
from app.services import ai_gateway, knowledge_extraction


class HostedAllowance:
    def __init__(self, calls=0):
        self.calls = calls
        self.paused = False
        self.reason = None
        self.reservations = []

    def read(self, _legacy):
        return {"day": ai_gateway._quota_day(), "calls": self.calls,
                "paused": self.paused, "reason": self.reason,
                "last_attempt_at": None, "migration_version": 1}

    def reserve_attempt(self, *, reservation_id, day, limit, attempted_at):
        if self.paused or (self.calls if self.read({})["day"] == day else 0) >= limit:
            return {"admitted": False}
        self.calls = self.calls + 1 if self.read({})["day"] == day else 1
        self.reservations.append((reservation_id, day, self.calls, attempted_at))
        return {"admitted": True, "dispatch_allowed": True, "attempt_number": self.calls}

    def set_paused(self, paused, reason=None):
        self.paused, self.reason = paused, reason
        return self.read({})


class Provider503(Exception):
    code = status_code = 503
    body = {"error": {"code": "UNAVAILABLE", "status": "UNAVAILABLE"}}


class Provider429(Exception):
    code = status_code = 429
    body = {"error": {"code": "RESOURCE_EXHAUSTED", "status": "RESOURCE_EXHAUSTED"}}


class SimulatedCrash(BaseException):
    pass


def install_hosted_provider(monkeypatch, allowance, outcomes, *, crash_after_dispatch=False):
    monkeypatch.setattr(ai_gateway, "PERSISTENCE_MODE", "hosted")
    monkeypatch.setattr(ai_gateway, "get_allowance_store", lambda: allowance)
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "true")
    monkeypatch.setenv("GEMINI_DAILY_CALL_LIMIT", "450")
    monkeypatch.setattr(ai_gateway.time, "sleep", lambda _delay: None)
    calls = []
    remaining = list(outcomes)

    class FakeClient:
        def __init__(self, **_):
            self.interactions = self
            self.sdk_configuration = SimpleNamespace(retry_config=SimpleNamespace(strategy="default"))
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def create(self, **kwargs):
            calls.append(kwargs)
            if crash_after_dispatch:
                raise SimulatedCrash("synthetic process loss after dispatch")
            result = remaining.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(ai_gateway.genai, "Client", FakeClient)
    return calls


def count_full_snapshot_writes(monkeypatch):
    original = knowledge_extraction.save_state
    writes = []
    def counted(*args, **kwargs):
        writes.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(knowledge_extraction, "save_state", counted)
    return writes


def test_hosted_one_attempt_success_has_two_snapshots_and_one_reservation(
    client, source, asset, monkeypatch, caplog
):
    caplog.set_level("INFO", logger="uvicorn.error")
    allowance = HostedAllowance()
    calls = install_hosted_provider(monkeypatch, allowance, [SimpleNamespace(
        output_text=json.dumps({"assets": [asset]}), id="synthetic-model-response"
    )])
    writes = count_full_snapshot_writes(monkeypatch)
    response = client.post(f"/sources/{source[0]['id']}/interpret?max_chunks=1")
    assert response.status_code == 200, response.text
    assert response.json()["processed_this_run"] == 1
    assert len(calls) == 1 and len(allowance.reservations) == 1
    assert len(writes) == 2
    assert sum(1 for item in mock_data.knowledge_assets if item.get("active", True)) == 1
    events = [json.loads(record.message.removeprefix("PERF ")) for record in caplog.records
              if record.message.startswith("PERF ")]
    reservations = [event for event in events if event["event"] == "allowance_reservation"]
    assert len(reservations) == 1
    assert reservations[0]["result"] == "admitted"
    assert reservations[0]["approximate_payload_bytes"] > 0


def test_hosted_503_retry_success_has_two_snapshots_and_two_reservations(
    client, source, asset, monkeypatch, caplog
):
    caplog.set_level("INFO", logger="uvicorn.error")
    allowance = HostedAllowance()
    calls = install_hosted_provider(monkeypatch, allowance, [Provider503("busy"), SimpleNamespace(
        output_text=json.dumps({"assets": [asset]}), id="synthetic-model-response"
    )])
    writes = count_full_snapshot_writes(monkeypatch)
    response = client.post(f"/sources/{source[0]['id']}/interpret?max_chunks=1")
    assert response.status_code == 200, response.text
    assert response.json()["processed_this_run"] == 1
    assert len(calls) == 2 and allowance.calls == 2
    assert len({item[0] for item in allowance.reservations}) == 2
    assert len(writes) == 2
    events = [json.loads(record.message.removeprefix("PERF ")) for record in caplog.records
              if record.message.startswith("PERF ")]
    assert len([event for event in events if event["event"] == "allowance_reservation"]) == 2


def test_two_503_failures_have_two_snapshots_two_reservations_and_failed_job(
    client, source, monkeypatch
):
    allowance = HostedAllowance()
    calls = install_hosted_provider(monkeypatch, allowance, [Provider503("one"), Provider503("two")])
    writes = count_full_snapshot_writes(monkeypatch)
    response = client.post(f"/sources/{source[0]['id']}/interpret?max_chunks=1")
    assert response.status_code == 200, response.text
    assert response.json()["processed_this_run"] == 0
    assert len(calls) == allowance.calls == 2 and len(writes) == 2
    assert mock_data.extraction_jobs[-1]["status"] == "failed"


def test_strict_validation_failure_settles_without_accepting_assets(client, source, monkeypatch):
    allowance = HostedAllowance()
    calls = install_hosted_provider(monkeypatch, allowance, [SimpleNamespace(
        output_text='{"assets":[{"asset_type":"not_a_type"}]}', id="invalid"
    )])
    writes = count_full_snapshot_writes(monkeypatch)
    response = client.post(f"/sources/{source[0]['id']}/interpret?max_chunks=1")
    assert response.status_code == 200
    assert response.json()["interruption_category"] == "validation_failed"
    assert len(calls) == allowance.calls == 1 and len(writes) == 2
    assert not mock_data.knowledge_assets
    assert mock_data.extraction_jobs[-1]["status"] == "failed"


def test_failed_coalesced_replacement_keeps_prior_accepted_asset(source, asset, monkeypatch):
    from app.services import gemini_knowledge_extraction
    from app.models.knowledge_asset import KnowledgeAsset
    from pydantic import TypeAdapter
    from app.services.knowledge_extraction import (
        capture_interpretation_state, complete_extraction_job,
        create_extraction_job, persist_interpretation_checkpoint,
    )

    source_id, chunk_id = source[0]["id"], source[1]["id"]
    original_job = create_extraction_job(source_id, chunk_id)
    accepted = complete_extraction_job(
        original_job["id"], [TypeAdapter(KnowledgeAsset).validate_python(asset)]
    )["assets"][0]
    durable = capture_interpretation_state()
    replacement = create_extraction_job(source_id, chunk_id, reprocess=True, persist=False)
    allowance = HostedAllowance()
    calls = install_hosted_provider(monkeypatch, allowance, [SimpleNamespace(output_text="not-json")])
    with pytest.raises(gemini_knowledge_extraction.ExtractionValidationError):
        gemini_knowledge_extraction.run_gemini_knowledge_extraction(
            replacement["id"], coalesce_interpretation=True,
            rollback_state=durable, on_checkpoint=lambda state: durable.update(state),
        )

    assert len(calls) == allowance.calls == 1
    assert replacement["status"] == "failed"
    assert accepted["active"] is True
    assert [item for item in mock_data.knowledge_assets if item.get("active", True)] == [accepted]
    persist_interpretation_checkpoint(durable)
    assert [item for item in mock_data.knowledge_assets if item.get("active", True)] == [accepted]


def test_allowance_exhaustion_before_dispatch_has_two_checkpoints_and_no_call(
    client, source, monkeypatch
):
    allowance = HostedAllowance(calls=450)
    calls = install_hosted_provider(monkeypatch, allowance, [SimpleNamespace(output_text="unused")])
    writes = count_full_snapshot_writes(monkeypatch)
    response = client.post(f"/sources/{source[0]['id']}/interpret?max_chunks=1")
    assert response.status_code == 200
    assert response.json()["interruption_category"] == "allowance_exhausted"
    assert calls == [] and allowance.calls == 450 and len(writes) == 2
    assert mock_data.extraction_jobs[-1]["status"] == "failed"


def test_provider_429_counts_attempt_pauses_allowance_and_settles_once(client, source, monkeypatch):
    allowance = HostedAllowance()
    calls = install_hosted_provider(monkeypatch, allowance, [Provider429("quota")])
    writes = count_full_snapshot_writes(monkeypatch)
    response = client.post(f"/sources/{source[0]['id']}/interpret?max_chunks=1")
    assert response.status_code == 200
    assert response.json()["interruption_category"] == "allowance_exhausted"
    assert len(calls) == allowance.calls == 1 and allowance.paused
    assert len(writes) == 2


def test_process_loss_after_provider_dispatch_leaves_durable_unconfirmed_job(
    source, monkeypatch
):
    from app.services import source_interpretation

    allowance = HostedAllowance()
    calls = install_hosted_provider(monkeypatch, allowance, [], crash_after_dispatch=True)
    writes = count_full_snapshot_writes(monkeypatch)
    with pytest.raises(SimulatedCrash):
        source_interpretation.interpret_source(source[0]["id"], max_chunks=1)
    assert len(calls) == allowance.calls == 1
    assert len(writes) == 1
    assert mock_data.extraction_jobs[-1]["status"] == "running"
    # Continuation is blocked until explicit stale-running recovery; no provider replay.
    retry = source_interpretation.interpret_source(source[0]["id"], max_chunks=1)
    assert retry["processed_this_run"] == 0
    assert len(calls) == 1


def test_process_loss_after_reservation_before_dispatch_is_conservative_and_not_replayed(
    source, monkeypatch
):
    from app.services import source_interpretation

    class CrashAfterDurableReservation(HostedAllowance):
        def reserve_attempt(self, **kwargs):
            super().reserve_attempt(**kwargs)
            raise SimulatedCrash("lost after reservation commit, before dispatch")

    allowance = CrashAfterDurableReservation()
    calls = install_hosted_provider(monkeypatch, allowance, [])
    writes = count_full_snapshot_writes(monkeypatch)
    with pytest.raises(SimulatedCrash):
        source_interpretation.interpret_source(source[0]["id"], max_chunks=1)

    assert allowance.calls == 1 and calls == [] and len(writes) == 1
    assert mock_data.extraction_jobs[-1]["status"] == "running"
    retry = source_interpretation.interpret_source(source[0]["id"], max_chunks=1)
    assert retry["processed_this_run"] == 0 and calls == []


def test_process_loss_after_provider_success_before_settlement_is_not_replayed(
    source, asset, monkeypatch
):
    from app.services import gemini_knowledge_extraction, source_interpretation

    allowance = HostedAllowance()
    calls = install_hosted_provider(monkeypatch, allowance, [SimpleNamespace(
        output_text=json.dumps({"assets": [asset]}), id="synthetic"
    )])
    writes = count_full_snapshot_writes(monkeypatch)
    monkeypatch.setattr(gemini_knowledge_extraction, "complete_extraction_job",
                        lambda **_: (_ for _ in ()).throw(SimulatedCrash("lost before settlement")))

    with pytest.raises(SimulatedCrash):
        source_interpretation.interpret_source(source[0]["id"], max_chunks=1)

    assert len(calls) == allowance.calls == 1 and len(writes) == 1
    assert mock_data.extraction_jobs[-1]["status"] == "running"
    assert not mock_data.knowledge_assets
    retry = source_interpretation.interpret_source(source[0]["id"], max_chunks=1)
    assert retry["processed_this_run"] == 0 and len(calls) == 1


def test_process_loss_after_precheckpoint_keeps_job_running_without_reservation(
    source, monkeypatch
):
    from app.services import gemini_knowledge_extraction, source_interpretation

    allowance = HostedAllowance()
    monkeypatch.setattr(ai_gateway, "PERSISTENCE_MODE", "hosted")
    monkeypatch.setattr(ai_gateway, "get_allowance_store", lambda: allowance)
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "true")
    writes = count_full_snapshot_writes(monkeypatch)
    monkeypatch.setattr(gemini_knowledge_extraction, "generate_structured_interaction",
                        lambda **_: (_ for _ in ()).throw(SimulatedCrash("lost after precheckpoint")))

    with pytest.raises(SimulatedCrash):
        source_interpretation.interpret_source(source[0]["id"], max_chunks=1)
    assert len(writes) == 1 and allowance.calls == 0
    assert mock_data.extraction_jobs[-1]["status"] == "running"


def test_settlement_save_failure_does_not_report_or_leave_uncommitted_knowledge(
    client, source, asset, monkeypatch
):
    allowance = HostedAllowance()
    calls = install_hosted_provider(monkeypatch, allowance, [SimpleNamespace(
        output_text=json.dumps({"assets": [asset]}), id="synthetic"
    )])
    original = knowledge_extraction.save_state
    writes = []
    def fail_settlement(*args, **kwargs):
        writes.append(True)
        if len(writes) == 2:
            raise RuntimeError("synthetic settlement store outage")
        return original(*args, **kwargs)
    monkeypatch.setattr(knowledge_extraction, "save_state", fail_settlement)
    response = client.post(f"/sources/{source[0]['id']}/interpret?max_chunks=1")
    assert response.status_code == 400
    assert len(calls) == allowance.calls == 1 and len(writes) == 2
    assert not mock_data.knowledge_assets
    assert mock_data.extraction_jobs[-1]["status"] == "running"


def test_process_loss_during_settlement_keeps_precheckpoint_as_recovery_point(
    source, asset, monkeypatch
):
    from app.services import source_interpretation
    from app.services.knowledge_extraction import (
        capture_interpretation_state, restore_interpretation_state,
    )

    allowance = HostedAllowance()
    calls = install_hosted_provider(monkeypatch, allowance, [SimpleNamespace(
        output_text=json.dumps({"assets": [asset]}), id="synthetic"
    )])
    original = knowledge_extraction.save_state
    writes = []
    durable_precheckpoint = []

    def lose_process_during_settlement(*args, **kwargs):
        writes.append(True)
        if len(writes) == 1:
            result = original(*args, **kwargs)
            durable_precheckpoint.append(capture_interpretation_state())
            return result
        raise SimulatedCrash("lost during settlement persistence")

    monkeypatch.setattr(knowledge_extraction, "save_state", lose_process_during_settlement)
    with pytest.raises(SimulatedCrash):
        source_interpretation.interpret_source(source[0]["id"], max_chunks=1)

    assert len(writes) == 2 and len(calls) == allowance.calls == 1
    assert durable_precheckpoint[0]["extraction_jobs"][-1]["status"] == "running"
    assert durable_precheckpoint[0]["knowledge_assets"] == []
    # Simulate a new process loading the committed pre-provider checkpoint.
    restore_interpretation_state(durable_precheckpoint[0])
    monkeypatch.setattr(knowledge_extraction, "save_state", original)
    retry = source_interpretation.interpret_source(source[0]["id"], max_chunks=1)
    assert retry["processed_this_run"] == 0 and len(calls) == 1


class RacingStateStore:
    def __init__(self, snapshot, stale_on):
        self.latest = deepcopy(snapshot)
        self._loaded_snapshot = deepcopy(snapshot)
        self.stale_on = stale_on
        self.save_count = 0
    @property
    def loaded_snapshot(self):
        return deepcopy(self._loaded_snapshot)
    def load(self):
        self._loaded_snapshot = deepcopy(self.latest)
        return deepcopy(self.latest)
    def save(self, state):
        self.save_count += 1
        if self.save_count == self.stale_on:
            self.latest = deepcopy(self._loaded_snapshot)
            self.latest["libraries"].append({"id": "library_concurrent", "name": "Concurrent"})
            raise StaleStateWriteError("synthetic stale revision")
        self.latest = deepcopy(state)
        self._loaded_snapshot = deepcopy(state)


def _hosted_snapshot():
    def relative_sources():
        result = deepcopy(mock_data.sources)
        for source in result:
            for key in ("file_path", "extracted_text_path", "chunks_path"):
                if source.get(key):
                    source[key] = Path(source[key]).relative_to(STORAGE_ROOT).as_posix()
        return result
    return {"schema_version": 2, "libraries": deepcopy(mock_data.libraries),
            "sources": relative_sources(), "extraction_jobs": deepcopy(mock_data.extraction_jobs),
            "knowledge_assets": deepcopy(mock_data.knowledge_assets),
            "outputs": deepcopy(mock_data.outputs), "usage": deepcopy(mock_data.usage)}


@pytest.mark.parametrize("stale_on", [1, 2], ids=["pre-checkpoint", "settlement"])
def test_stale_reconciliation_at_each_checkpoint_never_repeats_provider(
    client, source, asset, monkeypatch, stale_on
):
    allowance = HostedAllowance()
    calls = install_hosted_provider(monkeypatch, allowance, [SimpleNamespace(
        output_text=json.dumps({"assets": [asset]}), id="synthetic"
    )])
    state_store = RacingStateStore(_hosted_snapshot(), stale_on)
    monkeypatch.setattr(persistence_facade, "PERSISTENCE_MODE", "hosted")
    monkeypatch.setattr(persistence_facade, "get_state_store", lambda: state_store)

    response = client.post(f"/sources/{source[0]['id']}/interpret?max_chunks=1")

    assert response.status_code == 200, response.text
    assert response.json()["processed_this_run"] == 1
    assert len(calls) == allowance.calls == 1
    assert state_store.save_count == 3  # one stale CAS, its persistence-only rebase, then the other checkpoint
    assert any(item["id"] == "library_concurrent" for item in state_store.latest["libraries"])
    assert any(item.get("active", True) for item in state_store.latest["knowledge_assets"])

