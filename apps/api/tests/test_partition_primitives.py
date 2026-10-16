"""Offline boundaries for dormant partition primitives; no real DB/provider IO."""
from types import SimpleNamespace
import traceback
from unittest.mock import Mock
from uuid import uuid4

import psycopg
import pytest

from app.persistence import factory
from app.persistence.partitions import (
    PostgresPartitionStore, PartitionTransaction, PartitionVersionError,
    snapshot_authority,
)
from app.persistence.postgres import HostedStateStoreError
from postgres_test_guard import PostgreSQLConnectionDenied
from test_persistence_factory import run_configuration


@pytest.mark.parametrize("snapshot,expected", [
    ({}, "legacy"),
    ({"schema_version": 2, "extraction_jobs": [{"status": "completed"}]}, "legacy"),
    ({"partition": {"version": 1, "state": "preparing"}}, "legacy"),
    ({"partition": {"version": 1, "state": "active"}}, "partitioned"),
])
def test_snapshot_authority_compatibility_without_io(snapshot, expected):
    assert snapshot_authority(snapshot) == expected


@pytest.mark.parametrize("marker", [None, False, [], "active", {}, {"version": True, "state": "active"},
                                    {"version": 2, "state": "preparing"},
                                    {"version": 1, "state": "verified"}])
def test_unknown_or_malformed_markers_fail_closed(marker):
    with pytest.raises(PartitionVersionError):
        snapshot_authority({"partition": marker})


def test_factory_is_lazy_hosted_only_and_preserves_existing_snapshot_loader(tmp_path):
    with pytest.raises(RuntimeError, match="hosted mode"):
        factory.get_partition_store()
    run_configuration('''
        import os
        os.environ['KNOWLEDGE_ENGINE_DATABASE_URL'] = 'offline-database'
        os.environ['KNOWLEDGE_ENGINE_WORKSPACE_KEY'] = 'offline-workspace'
        from unittest.mock import patch
        from app.persistence import factory
        with patch('app.persistence.partitions.psycopg.connect', side_effect=AssertionError('unexpected IO')):
            first = factory.get_partition_store()
            assert first is factory.get_partition_store()
            assert first._workspace_key == 'offline-workspace'
            assert first._database_url == 'offline-database'
            # A core load is still delegated to StateStore, never composed with partitions.
            from app.db import persistence
            with patch.object(factory.get_state_store(), 'load', return_value={'legacy': True}):
                assert persistence.load_state() == {'legacy': True}
    ''', tmp_path / 'unused', 'hosted')


def test_adapter_keeps_existing_offline_guard():
    with pytest.raises(PostgreSQLConnectionDenied):
        PostgresPartitionStore('synthetic', 'workspace').read_source('source')


@pytest.mark.parametrize("database,workspace", [("", "workspace"), ("synthetic", ""), (" ", "workspace")])
def test_missing_configuration_is_not_a_silent_fallback(database, workspace):
    with pytest.raises(RuntimeError, match="Hosted partition storage requires"):
        PostgresPartitionStore(database, workspace)


def test_batch_id_reads_use_one_scoped_query_and_empty_batch_no_io():
    tx = PartitionTransaction(None, 'workspace')
    tx._all = Mock(return_value=[{'record': {'asset_id': 'a'}}])
    assert tx.assets_by_ids(['a', 'b', 'c']) == [{'asset_id': 'a'}]
    sql, parameters = tx._all.call_args.args
    assert 'workspace_key = %s' in sql and 'asset_id = ANY(%s)' in sql
    assert parameters == ('workspace', ['a', 'b', 'c'])
    tx._all.assert_called_once()
    store = PostgresPartitionStore('synthetic', 'workspace')
    assert store.assets_by_ids([]) == []


def test_queries_are_scoped_and_active_reads_require_live_generation():
    tx = PartitionTransaction(None, 'workspace')
    tx._all = Mock(return_value=[])
    tx.query_assets('s', 7, chunk_id='c', active=True)
    sql, params = tx._all.call_args.args
    assert 'NOT s.deleted' in sql and 's.generation = a.generation' in sql
    assert params == ('workspace', 's', 7, 'c', True)
    tx.query_jobs('s', 7, chunk_id='c')
    sql, params = tx._all.call_args.args
    assert 'chunk_id = %s' in sql and params == ('workspace', 's', 7, 'c')


@pytest.mark.parametrize('kind', ['connect', 'execute', 'commit'])
def test_driver_errors_sanitized_including_uncertain_commit(monkeypatch, kind):
    secret = uuid4().hex
    class Connection:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            if kind == 'commit':
                raise psycopg.OperationalError(secret)
    def connect(*args, **kwargs):
        if kind == 'connect':
            raise psycopg.OperationalError(secret)
        return Connection()
    monkeypatch.setattr('app.persistence.partitions.psycopg.connect', connect)
    store = PostgresPartitionStore(secret, 'workspace')
    with pytest.raises(HostedStateStoreError) as error:
        with store.transaction():
            if kind == 'execute':
                raise psycopg.OperationalError(secret)
    assert secret not in ''.join(traceback.format_exception(error.value))
    assert 'uncertain' in str(error.value)


def test_borrowed_connection_requires_outer_transaction():
    connection = SimpleNamespace(info=SimpleNamespace(transaction_status=psycopg.pq.TransactionStatus.IDLE))
    with pytest.raises(ValueError, match='outer transaction'):
        with PostgresPartitionStore('synthetic', 'workspace').transaction(connection):
            pytest.fail('accepted implicit independent commit')


def test_job_metadata_cannot_duplicate_authoritative_state():
    for metadata in ({'status': 'completed'}, {'generation': 3}, {'claim_token': 'untrusted'}):
        with pytest.raises(ValueError):
            PartitionTransaction._metadata(metadata)


def test_unsupported_staging_version_blocks_read_and_write():
    tx = PartitionTransaction(None, 'workspace')
    tx._one = Mock(return_value={'record': {'partition_version': 9}})
    with pytest.raises(PartitionVersionError):
        tx.checkpoint_migration('m', 1, 2, {})
    tx._one.assert_called_once()


def test_large_asset_batch_uses_one_set_based_insert():
    tx = PartitionTransaction(None, 'workspace')
    tx._running = Mock(return_value={'source_id': 's', 'chunk_id': 'c', 'extraction_version': 1})
    tx._all = Mock(return_value=[{'asset_id': str(i)} for i in range(100)])
    assets = [{'id': str(i), 'source_id': 's', 'chunk_id': 'c', 'asset_type': 'principle',
               'title': 'Synthetic', 'what_it_says': 'Use fixtures', 'evidence': 'Use fixtures',
               'keywords': ['fixtures']} for i in range(100)]
    assert tx.insert_assets('j', 1, 2, 'claim', assets) == {'inserted': 100}
    tx._all.assert_called_once()
    sql, params = tx._all.call_args.args
    assert 'jsonb_to_recordset' in sql and len(params[-1].obj) == 100
