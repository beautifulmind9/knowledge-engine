"""Explicit disposable-local PostgreSQL tests, outside the offline tests tree.

Run with: .venv/bin/python -m pytest apps/api/integration_tests -q
Launches and removes ONLY its own postgres:16-alpine container on the local
Docker socket. No configurable DSN or production credentials are accepted.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import subprocess
import sys
import time
from uuid import uuid4

import psycopg
import pytest

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))
from app.persistence.partitions import (
    PostgresPartitionStore, PartitionConflict, snapshot_authority,
)


@pytest.fixture(scope="session")
def database():
    env = os.environ.copy()
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        env.pop(key, None)
    def docker(*args):
        return subprocess.check_output(
            ["docker", "--host=unix:///var/run/docker.sock", *args], env=env,
            text=True, stderr=subprocess.STDOUT, timeout=60).strip()
    container = docker("run", "--rm", "-d", "--name", "ke-partitions-test-" + uuid4().hex[:12],
                       "--tmpfs", "/var/lib/postgresql/data", "-p", "127.0.0.1::5432",
                       "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "-e", "POSTGRES_USER=ke_test",
                       "-e", "POSTGRES_DB=ke_partitions", "postgres:16-alpine")
    try:
        port = docker("port", container, "5432/tcp")
        assert port.startswith("127.0.0.1:") and port.count(":") == 1
        dsn = f"host=127.0.0.1 port={int(port.split(':')[1])} user=ke_test dbname=ke_partitions"
        deadline = time.monotonic() + 30
        while True:
            try:
                with psycopg.connect(dsn, connect_timeout=1) as connection:
                    connection.execute("SELECT 1")
                break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    raise AssertionError("Disposable local PostgreSQL did not start.") from None
                time.sleep(0.1)
        with psycopg.connect(dsn) as connection:
            connection.execute((API_ROOT / "schema/create_knowledge_engine_partitions.sql").read_text())
        yield dsn
    finally:
        docker("rm", "-f", container)


@pytest.fixture
def store(database):
    return PostgresPartitionStore(database, "fixture-" + uuid4().hex)


def apply(store, fn, *, operation=None, request=None):
    return store.apply(operation or uuid4().hex, request or {"test": uuid4().hex}, fn)


def source(store):
    return apply(store, lambda tx: tx.create_source("s")).value


def job(store, jid="j", chunk="c", version=1, generation=1):
    return apply(store, lambda tx: tx.create_job(jid, "s", chunk, generation, version)).value


def claim(store, jid="j", token="claim", revision=1, generation=1):
    return apply(store, lambda tx: tx.claim_job(jid, generation, revision, token,
                                               provider="synthetic", model="fixture")).value


def finish(store, jid="j", revision=2, token="claim", status="completed", generation=1):
    return apply(store, lambda tx: tx.finish_job(jid, generation, revision, token, status=status)).value


def asset(aid="a", **overrides):
    return {"id": aid, "asset_type": "principle", "title": "Synthetic é", "what_it_says": "Use a fixture",
            "source_id": "s", "chunk_id": "c", "evidence": "Use a fixture", "keywords": ["fixture"],
            "created_at": "2026-10-16T00:00:00Z", **overrides}


def seeded(store):
    source(store)
    job(store)
    claim(store)


def test_source_generation_revision_and_deleted_fence(store):
    original = source(store)
    assert original["generation"] == original["revision"] == 1
    changed = apply(store, lambda tx: tx.advance_generation("s", 1, 1)).value
    assert changed["generation"] == changed["revision"] == 2
    for generation, revision in ((1, 2), (2, 1)):
        with pytest.raises(PartitionConflict):
            apply(store, lambda tx: tx.advance_generation("s", generation, revision))
    deleted = apply(store, lambda tx: tx.advance_generation("s", 2, 2, deleted=True)).value
    assert deleted["deleted"] and deleted["generation"] == 3
    with pytest.raises(PartitionConflict):
        apply(store, lambda tx: tx.advance_generation("s", 3, 3))
    with pytest.raises(PartitionConflict):
        job(store, generation=3)


def test_source_progress_is_not_a_chunk_counter(store):
    source(store)
    updated = apply(store, lambda tx: tx.update_source("s", 1, 1, status="running", stopped_reason="fixture")).value
    assert updated["revision"] == 2 and updated["stopped_reason"] == "fixture"
    assert "completed_chunks" not in updated
    with pytest.raises(PartitionConflict):
        apply(store, lambda tx: tx.update_source("s", 1, 1, status="completed"))


def test_create_claim_and_guarded_terminal_transition(store):
    seeded(store)
    assert store.read_job("j")["metadata"]["model"] == "fixture"
    for revision, token in ((1, "claim"), (2, "wrong")):
        with pytest.raises(PartitionConflict):
            finish(store, revision=revision, token=token)
    complete = finish(store)
    assert complete["status"] == "completed" and complete["claim_token"] is None
    assert complete["completed_at"] is not None
    with pytest.raises(PartitionConflict):
        claim(store, revision=3)


def test_live_uniqueness_and_extraction_versions(store):
    seeded(store)
    with pytest.raises(PartitionConflict):
        job(store, "second", version=2)
    finish(store)
    with pytest.raises(PartitionConflict):
        job(store, "skipped-version", version=3)
    second = job(store, "second", version=2)
    assert second["extraction_version"] == 2
    assert len(store.query_jobs("s", 1, chunk_id="c")) == 2
    assert store.query_jobs("other", 1) == []


def test_stale_generation_and_deleted_source_reject_inflight_mutations(store):
    seeded(store)
    apply(store, lambda tx: tx.advance_generation("s", 1, 1))
    with pytest.raises(PartitionConflict):
        finish(store)
    with pytest.raises(PartitionConflict):
        apply(store, lambda tx: tx.insert_assets("j", 1, 2, "claim", [asset()]))
    # Old rows remain historical, never implicit permission to resume.
    assert store.read_job("j")["generation"] == 1
    job(store, "new", generation=2)


def test_explicit_failed_and_stale_running_recovery(store):
    seeded(store)
    with pytest.raises(PartitionConflict):
        apply(store, lambda tx: tx.recover_job("j", 1, 2))
    finish(store, status="failed")
    recovered = apply(store, lambda tx: tx.recover_job("j", 1, 3)).value
    assert recovered["status"] == "pending_ai" and recovered["recovered_at"] is not None
    claim(store, revision=4, token="new-claim")
    with pytest.raises(PartitionConflict):
        finish(store, revision=5)  # Old token cannot finish recovered work.
    with store.transaction() as tx:
        # Simulate elapsed time in the disposable database without waiting ten minutes.
        tx.connection.execute("SET LOCAL session_replication_role = replica")
        tx.connection.execute("UPDATE knowledge_engine.partition_jobs SET started_at = now() - interval '11 minutes' "
                              "WHERE workspace_key = %s AND job_id = 'j'", (tx.workspace,))
    assert apply(store, lambda tx: tx.recover_job("j", 1, 5)).value["status"] == "pending_ai"


def test_batch_assets_provenance_and_replacement(store):
    seeded(store)
    result = apply(store, lambda tx: tx.insert_assets("j", 1, 2, "claim", [asset("a"), asset("b")]))
    assert result.value == {"inserted": 2}
    rows = store.query_assets("s", 1, chunk_id="c", active=True)
    assert [r["asset_id"] for r in rows] == ["a", "b"]
    assert rows[0]["payload"]["evidence"] == "Use a fixture"
    assert rows[0]["payload"]["title"] == "Synthetic é"
    assert rows[0]["job_id"] == "j" and rows[0]["extraction_version"] == 1
    finish(store)
    job(store, "j2", version=2)
    claim(store, "j2", "claim2")
    def replace(tx):
        tx.supersede_assets("j2", 1, 2, "claim2", expected_active_version=1)
        tx.insert_assets("j2", 1, 2, "claim2", [asset("new")])
        return tx.finish_job("j2", 1, 2, "claim2", status="completed")
    apply(store, replace)
    assert [r["asset_id"] for r in store.query_assets("s", 1, active=True)] == ["new"]
    old = store.query_assets("s", 1, active=False)
    assert len(old) == 2 and all(r["superseded_by_job_id"] == "j2" for r in old)
    assert len(store.assets_by_ids(["a", "b", "new", "missing"])) == 3
    apply(store, lambda tx: tx.advance_generation("s", 1, 1))
    assert store.query_assets("s", 1, active=True) == []
    assert len(store.assets_by_ids(["a", "new"])) == 2  # Historical resolution remains available.


@pytest.mark.parametrize("bad", [asset("wrong-source", source_id="other"), asset("wrong-chunk", chunk_id="other"),
                                  asset("invalid", evidence=""), asset(None)])
def test_invalid_batch_never_partially_persists(store, bad):
    seeded(store)
    with pytest.raises((ValueError, PartitionConflict)):
        apply(store, lambda tx: tx.insert_assets("j", 1, 2, "claim", [asset(), bad]))
    assert store.query_assets("s", 1) == []


def test_failed_replacement_rolls_back_supersession_and_receipt(store):
    seeded(store)
    apply(store, lambda tx: tx.insert_assets("j", 1, 2, "claim", [asset()]))
    finish(store)
    job(store, "j2", version=2)
    claim(store, "j2", "token2")
    operation = uuid4().hex
    def bad(tx):
        tx.supersede_assets("j2", 1, 2, "token2", expected_active_version=1)
        tx.insert_assets("j2", 1, 2, "token2", [asset("new", chunk_id="other")])
        return {}
    with pytest.raises(ValueError):
        apply(store, bad, operation=operation)
    assert store.read_operation(operation) is None
    assert [r["asset_id"] for r in store.query_assets("s", 1, active=True)] == ["a"]


def test_empty_replacement_retains_version_in_completed_job(store):
    seeded(store)
    finish(store)  # Valid empty result.
    job(store, "j2", version=2)
    claim(store, "j2", "claim2")
    with pytest.raises(PartitionConflict):
        apply(store, lambda tx: tx.supersede_assets("j2", 1, 2, "claim2", expected_active_version=None))
    assert apply(store, lambda tx: tx.supersede_assets("j2", 1, 2, "claim2", expected_active_version=1)).value == {"superseded": 0}


def test_idempotent_command_replay_and_input_conflict(store):
    source(store)
    operation, request = "op", {"kind": "create-job", "id": "j"}
    first = apply(store, lambda tx: tx.create_job("j", "s", "c", 1, 1), operation=operation, request=request)
    replay = apply(store, lambda tx: pytest.fail("replayed mutation executed"), operation=operation, request=request)
    assert not first.replayed and replay.replayed and replay.value == first.value
    assert store.read_operation(operation)["result"] == first.value
    with pytest.raises(PartitionConflict):
        apply(store, lambda tx: {}, operation=operation, request={"changed": True})


def test_workspace_isolation(store, database):
    seeded(store)
    apply(store, lambda tx: tx.insert_assets("j", 1, 2, "claim", [asset()]))
    other = PostgresPartitionStore(database, uuid4().hex)
    assert other.read_source("s") is None and other.read_job("j") is None
    assert other.assets_by_ids(["a"]) == []
    assert other.query_jobs("s", 1) == []


def test_concurrent_same_chunk_creation_and_claim(store):
    source(store)
    def create(jid):
        try:
            return job(store, jid)
        except PartitionConflict:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, ["one", "two"]))
    winner = next(r for r in results if r is not None)
    assert sum(r is not None for r in results) == 1
    def claiming(token):
        try:
            return claim(store, winner["job_id"], token)
        except PartitionConflict:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claiming, ["token1", "token2"]))
    assert sum(r is not None for r in claims) == 1


def test_concurrent_independent_chunks_and_operation_replay(store):
    source(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda c: job(store, c, chunk=c), ["c1", "c2"]))
    assert len(results) == 2
    operation, request = "concurrent-op", {"kind": "claim", "job": "c1", "token": "same"}
    def same(_):
        return apply(store, lambda tx: tx.claim_job("c1", 1, 1, "same", provider="fake", model="fake"),
                     operation=operation, request=request)
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(same, range(2)))
    assert sorted(r.replayed for r in receipts) == [False, True]


def test_migration_checkpoints_cas_and_no_authority_activation(store):
    assert store.read_migration() is None
    stage = apply(store, lambda tx: tx.prepare_migration("migration", 7)).value
    assert stage["stage"] == "preparing" and stage["partition_version"] == 1
    saved = apply(store, lambda tx: tx.checkpoint_migration("migration", 1, 7, {"jobs_cursor": "j5"})).value
    assert saved["revision"] == 2
    for revision, snapshot in ((1, 7), (2, 8)):
        with pytest.raises(PartitionConflict):
            apply(store, lambda tx: tx.checkpoint_migration("migration", revision, snapshot, {}))
    verified = apply(store, lambda tx: tx.checkpoint_migration("migration", 2, 7, {"verified": "fixture"}, verified=True)).value
    assert verified["stage"] == "verified"
    with pytest.raises(PartitionConflict):
        apply(store, lambda tx: tx.checkpoint_migration("migration", 3, 7, {}))
    assert snapshot_authority({"sources": []}) == "legacy"
    assert snapshot_authority({"partition": {"version": 1, "state": "preparing"}}) == "legacy"
    # Staging does not create or read a state_snapshots table.
    with store.transaction() as tx:
        assert tx._one("SELECT to_regclass('knowledge_engine.state_snapshots') AS name")["name"] is None


def test_borrowed_connection_joins_outer_transaction(store, database):
    with pytest.raises(RuntimeError, match="outer rollback"):
        with psycopg.connect(database) as connection:
            connection.execute("SELECT 1")
            store.apply("shared", {"kind": "source"}, lambda tx: tx.create_source("s"), connection=connection)
            raise RuntimeError("outer rollback")
    assert store.read_source("s") is None and store.read_operation("shared") is None
    with psycopg.connect(database) as connection:
        with pytest.raises(ValueError, match="outer transaction"):
            with store.transaction(connection):
                pass


def test_database_guards_cannot_be_bypassed_by_direct_sql(store):
    seeded(store)
    statements = [
        ("UPDATE knowledge_engine.partition_sources SET generation = 0, revision = revision + 1 WHERE workspace_key = %s",),
        ("UPDATE knowledge_engine.partition_jobs SET status = 'pending_ai', claim_token = NULL, revision = revision + 1 WHERE workspace_key = %s",),
        ("UPDATE knowledge_engine.partition_jobs SET generation = 99, revision = revision + 1 WHERE workspace_key = %s",),
    ]
    for (sql,) in statements:
        with pytest.raises(PartitionConflict):
            with store.transaction() as tx:
                tx.connection.execute(sql, (tx.workspace,))


@pytest.mark.parametrize('committed', [False, True])
def test_uncertain_commit_resolved_by_receipt_without_repeat_mutation(store, monkeypatch, committed):
    from app.persistence.postgres import HostedStateStoreError
    original = psycopg.connect
    class AcknowledgementFailure:
        def __enter__(self):
            self.connection = original(store._database_url)
            return self.connection.__enter__()
        def __exit__(self, kind, error, tb):
            if committed:
                self.connection.__exit__(kind, error, tb)
            else:
                failure = RuntimeError('synthetic abort')
                self.connection.__exit__(RuntimeError, failure, None)
            raise psycopg.OperationalError('synthetic lost acknowledgement')
    with monkeypatch.context() as patch:
        patch.setattr('app.persistence.partitions.psycopg.connect', lambda *a, **k: AcknowledgementFailure())
        with pytest.raises(HostedStateStoreError):
            store.apply('uncertain', {'source_id': 's'}, lambda tx: tx.create_source('s'))
    assert (store.read_operation('uncertain') is not None) is committed
    if committed:
        result = store.apply('uncertain', {'source_id': 's'}, lambda tx: pytest.fail('duplicate mutation'))
        assert result.replayed
    else:
        assert store.read_source('s') is None


def test_direct_asset_forgery_and_competing_active_versions_rejected(store):
    seeded(store)
    apply(store, lambda tx: tx.insert_assets('j', 1, 2, 'claim', [asset()]))
    with pytest.raises(PartitionConflict):
        with store.transaction() as tx:
            tx.connection.execute(
                "UPDATE knowledge_engine.partition_assets SET source_id = 'other', revision = revision + 1 "
                "WHERE workspace_key = %s", (tx.workspace,))
    finish(store)
    job(store, 'j2', version=2)
    claim(store, 'j2', 'next')
    with pytest.raises(PartitionConflict):
        apply(store, lambda tx: tx.insert_assets('j2', 1, 2, 'next', [asset('competing')]))
    assert len(store.query_assets('s', 1, active=True)) == 1


def test_migration_database_guards_and_table_security(store):
    apply(store, lambda tx: tx.prepare_migration('m', 1))
    with pytest.raises(PartitionConflict):
        with store.transaction() as tx:
            tx.connection.execute("UPDATE knowledge_engine.partition_migrations SET stage = 'active', "
                                  "revision = revision + 1 WHERE workspace_key = %s", (tx.workspace,))
    with store.transaction() as tx:
        tables = tx._all("SELECT relname, relrowsecurity FROM pg_class c JOIN pg_namespace n ON c.relnamespace = n.oid "
                         "WHERE n.nspname = 'knowledge_engine' AND c.relkind = 'r'")
        assert len(tables) == 5 and all(r['relrowsecurity'] for r in tables)
        public = tx._all("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON c.relnamespace = n.oid, "
                         "LATERAL aclexplode(c.relacl) acl WHERE n.nspname = 'knowledge_engine' AND acl.grantee = 0")
        assert public == []


def test_delete_wins_race_against_inflight_completion(store):
    from threading import Event
    seeded(store)
    entered, release = Event(), Event()
    def holding_fence():
        def hold(tx):
            changed = tx.advance_generation('s', 1, 1, deleted=True)
            entered.set()
            assert release.wait(5)
            return changed
        return apply(store, hold)
    with ThreadPoolExecutor(max_workers=2) as pool:
        deletion = pool.submit(holding_fence)
        assert entered.wait(5)
        completion = pool.submit(finish, store)
        release.set()
        assert deletion.result().value['deleted']
        with pytest.raises(PartitionConflict):
            completion.result()
    assert store.read_job('j')['status'] == 'running'


@pytest.mark.parametrize('deleted', [False, True])
def test_completion_before_lifecycle_change_is_preserved_as_history(store, deleted):
    seeded(store)
    apply(store, lambda tx: tx.insert_assets('j', 1, 2, 'claim', [asset()]))
    finish(store)
    apply(store, lambda tx: tx.advance_generation('s', 1, 1, deleted=deleted))
    assert store.read_job('j')['status'] == 'completed'
    assert store.query_assets('s', 1, active=True) == []
    assert store.assets_by_ids(['a'])[0]['payload']['source_id'] == 's'


def test_set_based_insert_database_error_rolls_back_entire_batch(store):
    seeded(store)
    with pytest.raises(PartitionConflict):
        apply(store, lambda tx: tx.insert_assets('j', 1, 2, 'claim', [asset('duplicate'), asset('duplicate')]))
    assert store.query_assets('s', 1) == []


def test_superseded_assets_cannot_be_reactivated_after_empty_replacement(store):
    seeded(store)
    apply(store, lambda tx: tx.insert_assets('j', 1, 2, 'claim', [asset()]))
    finish(store)
    job(store, 'j2', version=2)
    claim(store, 'j2', 'second')
    def empty(tx):
        tx.supersede_assets('j2', 1, 2, 'second', expected_active_version=1)
        return tx.finish_job('j2', 1, 2, 'second', status='completed')
    apply(store, empty)
    with pytest.raises(PartitionConflict):
        with store.transaction() as tx:
            tx.connection.execute("UPDATE knowledge_engine.partition_assets SET active = true, "
                                  "superseded_by_job_id = NULL, revision = revision + 1 WHERE workspace_key = %s",
                                  (tx.workspace,))
    assert store.query_assets('s', 1, active=True) == []
