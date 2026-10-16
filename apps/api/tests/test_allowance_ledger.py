from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from threading import Barrier
from types import SimpleNamespace

import psycopg
import pytest
from fastapi import HTTPException

from app.persistence import allowance
from app.services import ai_gateway


class FakeDatabase:
    def __init__(self):
        from threading import RLock
        self.lock = RLock()
        self.state = None
        self.reservations = {}
        self.lose_next_ack = False
        self.fail_next_commit = False

    def connect(self, *_args, **_kwargs):
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, database):
        self.database = database
        self.state = None
        self.reservations = None
        self.result = None
        self.has_reservation_insert = False

    def __enter__(self):
        self.database.lock.acquire()
        self.state = deepcopy(self.database.state)
        self.reservations = deepcopy(self.database.reservations)
        return self

    def __exit__(self, exc_type, _exc, _tb):
        lose_ack = False
        fail_commit = False
        if exc_type is None:
            if self.database.fail_next_commit and self.has_reservation_insert:
                self.database.fail_next_commit = False
                fail_commit = True
            else:
                self.database.state = self.state
                self.database.reservations = self.reservations
            if self.database.lose_next_ack and self.has_reservation_insert and not fail_commit:
                self.database.lose_next_ack = False
                lose_ack = True
        self.database.lock.release()
        if fail_commit:
            raise psycopg.OperationalError("synthetic definite commit failure")
        if lose_ack:
            raise psycopg.OperationalError("synthetic lost commit acknowledgement")
        return False

    @staticmethod
    def _state_row(state):
        if state is None:
            return None
        return (state["day"], state["calls"], state["paused"], state["reason"],
                state["last_attempt_at"], state["last_reservation_id"], state["migration_version"])

    def execute(self, query, params=()):
        normalized = " ".join(query.split())
        self.result = None
        if normalized.startswith("SELECT accounting_day, admitted_attempt_number FROM knowledge_engine.allowance_reservations"):
            row = self.reservations.get((params[0], params[1]))
            self.result = (row["day"], row["attempt_number"]) if row else None
        elif normalized.startswith("SELECT accounting_day, admitted_attempts, paused, pause_reason"):
            self.result = self._state_row(self.state)
        elif normalized.startswith("INSERT INTO knowledge_engine.allowance_state"):
            if self.state is None:
                (workspace, day, calls, paused, reason, last_attempt, last_reservation, version) = params
                self.state = {"workspace": workspace, "day": day, "calls": calls, "paused": paused,
                              "reason": reason, "last_attempt_at": last_attempt,
                              "last_reservation_id": last_reservation, "migration_version": version}
        elif normalized.startswith("UPDATE knowledge_engine.allowance_state SET accounting_day"):
            day, calls, last_attempt, reservation_id, workspace = params
            assert self.state and self.state["workspace"] == workspace
            self.state.update(day=day, calls=calls, last_attempt_at=last_attempt,
                              last_reservation_id=reservation_id)
        elif normalized.startswith("INSERT INTO knowledge_engine.allowance_reservations"):
            self.has_reservation_insert = True
            workspace, reservation_id, day, attempt_number, admitted_at = params
            key = (workspace, reservation_id)
            if key in self.reservations:
                raise psycopg.errors.UniqueViolation("duplicate reservation")
            self.reservations[key] = {"day": day, "attempt_number": attempt_number, "at": admitted_at}
        elif normalized.startswith("UPDATE knowledge_engine.allowance_state SET paused"):
            paused, reason, workspace, version = params
            if self.state and self.state["workspace"] == workspace and self.state["migration_version"] == version:
                self.state.update(paused=paused, reason=reason)
                self.result = self._state_row(self.state)
        else:
            raise AssertionError(f"Unexpected SQL in test fake: {normalized}")
        return self

    def fetchone(self):
        return self.result


@pytest.fixture
def ledger(monkeypatch):
    database = FakeDatabase()
    store = allowance.PostgresAllowanceStore("postgres://synthetic", "workspace-test")
    monkeypatch.setattr(store, "_connect", database.connect)
    return store, database


def reserve(store, reservation_id, day="2026-10-15", limit=450):
    return store.reserve_attempt(reservation_id=reservation_id, day=day, limit=limit,
                                 attempted_at=datetime(2026, 10, 15, 12, tzinfo=timezone.utc))


def test_migration_seeds_and_verifies_existing_snapshot_usage(ledger):
    store, database = ledger
    previous = {"day": "2026-10-15", "calls": 37, "paused": True,
                "reason": "provider quota", "last_attempt_at": "2026-10-15T11:00:00+00:00"}
    state = store.ensure_migrated(previous)
    assert state["day"] == "2026-10-15"
    assert state["calls"] == 37 and state["paused"] is True
    assert state["reason"] == "provider quota" and state["migration_version"] == 1
    assert state["last_attempt_at"] == "2026-10-15T11:00:00+00:00"
    assert store.ensure_migrated(previous) == state
    previous.update(day="2026-10-14", calls=0, paused=False, reason=None)
    unchanged = store.read(previous)
    assert unchanged["calls"] == 37 and unchanged["paused"] is True
    assert unchanged["reason"] == "provider quota"
    assert unchanged["last_attempt_at"] == "2026-10-15T11:00:00+00:00"
    assert database.state["migration_version"] == allowance.ALLOWANCE_MIGRATION_VERSION


def test_migration_does_not_seed_below_same_day_snapshot_count(ledger):
    store, _ = ledger
    state = store.ensure_migrated({"day": "2026-10-15", "calls": 449})
    assert state["day"] == "2026-10-15" and state["calls"] == 449
    assert reserve(store, "after-migration")["attempt_number"] == 450


def test_existing_ledger_is_not_reseeded_and_ahead_snapshot_fails_closed(ledger):
    store, database = ledger
    store.ensure_migrated({"day": "2026-10-15", "calls": 40})
    with pytest.raises(allowance.AllowanceMigrationError):
        store.ensure_migrated({"day": "2026-10-15", "calls": 41})
    assert database.state["calls"] == 40


def test_simultaneous_first_reads_create_one_idempotent_ledger(ledger):
    store, database = ledger
    legacy = {"day": "2026-10-15", "calls": 73, "paused": True,
              "reason": "preserve pause", "last_attempt_at": "2026-10-15T11:00:00+00:00"}
    gate = Barrier(8)

    def initialize(_):
        gate.wait()
        return store.ensure_migrated(legacy)

    with ThreadPoolExecutor(max_workers=8) as pool:
        states = list(pool.map(initialize, range(8)))

    assert all(state == states[0] for state in states)
    assert states[0]["calls"] == 73 and states[0]["paused"] is True
    assert states[0]["reason"] == "preserve pause"
    assert states[0]["last_attempt_at"] == "2026-10-15T11:00:00+00:00"
    assert database.state["calls"] == 73


def test_fresh_day_and_same_day_attempts_are_counted_independently(ledger):
    store, _ = ledger
    store.ensure_migrated({"day": "2026-10-14", "calls": 450})
    first = reserve(store, "attempt-1")
    second = reserve(store, "attempt-2")
    assert first["attempt_number"] == 1 and second["attempt_number"] == 2
    assert store.read({})["calls"] == 2


def test_pacific_midnight_rollover_starts_a_new_count(ledger):
    store, _ = ledger
    before = datetime(2026, 10, 16, 6, 59, tzinfo=timezone.utc)
    after = datetime(2026, 10, 16, 7, 1, tzinfo=timezone.utc)
    old_day, new_day = ai_gateway._quota_day(before), ai_gateway._quota_day(after)
    assert (old_day, new_day) == ("2026-10-15", "2026-10-16")
    store.ensure_migrated({"day": old_day, "calls": 449})
    assert store.reserve_attempt(reservation_id="last-old", day=old_day, limit=450,
                                 attempted_at=before)["attempt_number"] == 450
    assert store.reserve_attempt(reservation_id="first-new", day=new_day, limit=450,
                                 attempted_at=after)["attempt_number"] == 1
    assert store.read({})["calls"] == 1


def test_duplicate_reservation_is_idempotent_and_not_dispatchable(ledger):
    store, _ = ledger
    store.ensure_migrated({})
    first = reserve(store, "same-id")
    duplicate = reserve(store, "same-id")
    assert first["dispatch_allowed"] is True
    assert duplicate["duplicate"] is True and duplicate["dispatch_allowed"] is False
    assert store.read({})["calls"] == 1


def test_lost_commit_ack_is_confirmed_once_without_reincrement(ledger):
    store, database = ledger
    store.ensure_migrated({})
    database.lose_next_ack = True
    recovered = reserve(store, "lost-ack")
    assert recovered["acknowledgement_recovered"] is True
    assert recovered["dispatch_allowed"] is True
    assert reserve(store, "lost-ack")["dispatch_allowed"] is False
    assert store.read({})["calls"] == 1


def test_lost_commit_ack_confirmation_allows_exactly_one_provider_dispatch(ledger, monkeypatch):
    store, database = ledger
    store.ensure_migrated({})
    install_hosted_gateway(monkeypatch, store)
    database.lose_next_ack = True
    calls = install_fake_provider(monkeypatch, [SimpleNamespace(output_text='{"ok":true}')])

    result = ai_gateway.generate("synthetic-model", {"text": "fixture"}, {"type": "object"})

    assert result.output_text == '{"ok":true}'
    assert len(calls) == 1 and store.read({})["calls"] == 1


def test_restart_after_reservation_counts_it_but_does_not_replay_it(ledger, monkeypatch):
    store, database = ledger
    store.ensure_migrated({})
    reserved = reserve(store, "before-dispatch")
    restarted = allowance.PostgresAllowanceStore("postgres://synthetic", "workspace-test")
    monkeypatch.setattr(restarted, "_connect", database.connect)
    assert restarted.read({})["calls"] == 1
    assert reserve(restarted, "before-dispatch")["dispatch_allowed"] is False
    assert reserve(restarted, "after-restart")["attempt_number"] == 2
    assert reserved["dispatch_allowed"] is True


def test_restart_after_provider_dispatch_keeps_reservation_and_does_not_replay(ledger, monkeypatch):
    store, database = ledger
    store.ensure_migrated({})
    install_hosted_gateway(monkeypatch, store)
    calls = install_fake_provider(monkeypatch, [SimpleNamespace(output_text='{"ok":true}')])
    result = ai_gateway.generate("synthetic-model", {"text": "fixture"}, {"type": "object"})
    assert result.output_text == '{"ok":true}' and len(calls) == 1

    restarted = allowance.PostgresAllowanceStore("postgres://synthetic", "workspace-test")
    monkeypatch.setattr(restarted, "_connect", database.connect)
    state = restarted.read({})
    reservation_id = state["last_reservation_id"]
    assert state["calls"] == 1
    assert restarted.reserve_attempt(reservation_id=reservation_id, day=state["day"], limit=450,
                                     attempted_at=datetime.now(timezone.utc))["dispatch_allowed"] is False
    assert len(calls) == 1 and restarted.read({})["calls"] == 1


def test_concurrent_reservation_writers_never_exceed_cap(ledger):
    store, _ = ledger
    store.ensure_migrated({})
    def attempt(index):
        return reserve(store, f"parallel-{index}", limit=7)["admitted"]
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(attempt, range(24)))
    assert sum(results) == 7
    assert store.read({})["calls"] == 7


class Provider503(Exception):
    code = status_code = 503
    body = {"error": {"code": "UNAVAILABLE", "status": "UNAVAILABLE"}}


class Provider429(Exception):
    code = status_code = 429
    body = {"error": {"code": "RESOURCE_EXHAUSTED", "status": "RESOURCE_EXHAUSTED"}}


def install_fake_provider(monkeypatch, outcomes):
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
            result = remaining.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
    monkeypatch.setattr(ai_gateway.genai, "Client", FakeClient)
    return calls


def install_hosted_gateway(monkeypatch, store):
    monkeypatch.setattr(ai_gateway, "PERSISTENCE_MODE", "hosted")
    monkeypatch.setattr(ai_gateway, "get_allowance_store", lambda: store)
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "true")
    monkeypatch.setenv("GEMINI_DAILY_CALL_LIMIT", "450")


def test_definite_reservation_commit_failure_never_dispatches(ledger, monkeypatch):
    store, database = ledger
    store.ensure_migrated({})
    install_hosted_gateway(monkeypatch, store)
    database.fail_next_commit = True
    calls = install_fake_provider(monkeypatch, [SimpleNamespace(output_text="must not run")])

    with pytest.raises(HTTPException) as failure:
        ai_gateway.generate("synthetic-model", {"text": "fixture"}, {"type": "object"})

    assert failure.value.status_code == 503
    assert calls == [] and store.read({})["calls"] == 0


def test_ambiguous_reservation_ack_without_confirmable_lookup_never_dispatches(
    ledger, monkeypatch
):
    store, database = ledger
    store.ensure_migrated({})
    install_hosted_gateway(monkeypatch, store)
    database.lose_next_ack = True
    monkeypatch.setattr(store, "_lookup_reservation",
                        lambda _reservation_id: (_ for _ in ()).throw(RuntimeError("lookup unavailable")))
    calls = install_fake_provider(monkeypatch, [SimpleNamespace(output_text="must not run")])

    with pytest.raises(HTTPException) as failure:
        ai_gateway.generate("synthetic-model", {"text": "fixture"}, {"type": "object"})

    # The transaction may have committed, so the ledger conservatively counts
    # the attempt. With no confirmation, no provider request is dispatched.
    assert failure.value.status_code == 503
    assert calls == [] and store.read({})["calls"] == 1


def test_503_retry_success_uses_two_reservations_and_two_provider_calls(ledger, monkeypatch):
    store, _ = ledger
    store.ensure_migrated({})
    install_hosted_gateway(monkeypatch, store)
    monkeypatch.setattr(ai_gateway.time, "sleep", lambda _delay: None)
    calls = install_fake_provider(monkeypatch, [Provider503("busy"), SimpleNamespace(output_text='{"ok":true}')])
    from app.services import knowledge_extraction
    whole_snapshot_saves = []
    monkeypatch.setattr(knowledge_extraction, "persist_state", lambda: whole_snapshot_saves.append(True))

    result = ai_gateway.generate("synthetic-model", {"source_id": "source-test", "chunk_id": "chunk-test"}, {"type": "object"})

    state = store.read({})
    assert result.output_text == '{"ok":true}'
    assert len(calls) == 2 and state["calls"] == 2
    assert calls[0] == calls[1]
    assert len(set((row[1] for row in _.reservations))) == 2
    assert whole_snapshot_saves == []


def test_two_503_failures_count_both_attempts_and_do_not_replay(ledger, monkeypatch):
    store, _database = ledger
    store.ensure_migrated({})
    install_hosted_gateway(monkeypatch, store)
    monkeypatch.setattr(ai_gateway.time, "sleep", lambda _delay: None)
    calls = install_fake_provider(monkeypatch, [Provider503("busy"), Provider503("still busy")])
    with pytest.raises(HTTPException) as failure:
        ai_gateway.generate("synthetic-model", {"text": "private"}, {"type": "object"})
    assert failure.value.status_code == 502
    assert len(calls) == 2 and store.read({})["calls"] == 2


def test_provider_429_pauses_ledger_after_counting_attempt(ledger, monkeypatch):
    store, _ = ledger
    store.ensure_migrated({})
    install_hosted_gateway(monkeypatch, store)
    calls = install_fake_provider(monkeypatch, [Provider429("quota")])
    with pytest.raises(HTTPException) as failure:
        ai_gateway.generate("synthetic-model", {"text": "fixture"}, {"type": "object"})
    state = store.read({})
    assert failure.value.status_code == 429
    assert len(calls) == 1 and state["calls"] == 1
    assert state["paused"] is True and "quota exhausted" in state["reason"]


def test_exhausted_local_cap_denies_without_provider_work(ledger, monkeypatch):
    store, _ = ledger
    store.ensure_migrated({"day": ai_gateway._quota_day(), "calls": 450})
    install_hosted_gateway(monkeypatch, store)
    calls = install_fake_provider(monkeypatch, [SimpleNamespace(output_text="unused")])
    with pytest.raises(HTTPException) as failure:
        ai_gateway.generate("synthetic-model", {"text": "fixture"}, {"type": "object"})
    assert failure.value.status_code == 429
    assert calls == [] and store.read({})["calls"] == 450


def test_duplicate_reservation_id_never_reaches_provider(ledger, monkeypatch):
    store, _ = ledger
    store.ensure_migrated({})
    install_hosted_gateway(monkeypatch, store)
    monkeypatch.setattr(ai_gateway, "uuid4", lambda: SimpleNamespace(hex="duplicate"))
    # First reservation already exists; the provider must not be dispatched again.
    store.reserve_attempt(reservation_id="duplicate", day=ai_gateway._quota_day(), limit=450,
                          attempted_at=datetime.now(timezone.utc))
    calls = install_fake_provider(monkeypatch, [SimpleNamespace(output_text="must not run")])
    with pytest.raises(HTTPException) as failure:
        ai_gateway.generate("synthetic-model", {"text": "fixture"}, {"type": "object"})
    assert failure.value.status_code == 503 and calls == []


def test_rollback_copyback_preserves_authoritative_ledger_state(ledger, monkeypatch):
    store, _ = ledger
    state = store.ensure_migrated({"day": "2026-10-15", "calls": 8, "paused": True,
                                   "reason": "provider quota",
                                   "last_attempt_at": "2026-10-15T11:00:00+00:00"})
    monkeypatch.setattr(ai_gateway, "PERSISTENCE_MODE", "hosted")
    monkeypatch.setattr(ai_gateway, "get_allowance_store", lambda: store)
    copied_snapshots = []
    monkeypatch.setattr("app.services.knowledge_extraction.persist_state",
                        lambda: copied_snapshots.append(deepcopy(ai_gateway.usage)))
    copied = ai_gateway.copy_allowance_to_legacy_snapshot()
    assert copied["calls"] == state["calls"] == 8
    assert copied["day"] == "2026-10-15" and copied["paused"] is True
    assert copied["reason"] == "provider quota" and len(copied_snapshots) == 1

