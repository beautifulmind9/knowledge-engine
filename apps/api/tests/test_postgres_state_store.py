"""Offline transaction fake: every psycopg connection is intercepted."""
from copy import deepcopy
import json
import traceback
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest

from app.persistence.postgres import (
    HostedStateIntegrityError, HostedStateStoreError, PostgresStateStore, StaleStateWriteError, STALE_WRITE_MESSAGE,
)


@pytest.fixture
def database(monkeypatch):
    db = SimpleNamespace(rows={}, queries=[], rollbacks=0, fail_execute=False, fail_commit=False)

    class Connection:
        def __enter__(self):
            self.rows = deepcopy(db.rows)
            return self

        def execute(self, sql, parameters):
            db.queries.append((sql, parameters))
            if db.fail_execute:
                raise psycopg.OperationalError(db.secret)
            if sql.startswith('SELECT'):
                row = self.rows.get(parameters[0])
                result = (deepcopy(row[0]), row[1]) if row else None
            elif sql.startswith('INSERT'):
                key, payload = parameters
                if key in self.rows:
                    result = None
                else:
                    self.rows[key] = (json.loads(json.dumps(payload.obj)), 1)
                    result = (1,)
            else:
                payload, key, revision = parameters
                row = self.rows.get(key)
                if row is None or row[1] != revision:
                    result = None
                else:
                    self.rows[key] = (json.loads(json.dumps(payload.obj)), revision + 1)
                    result = (revision + 1,)
            return SimpleNamespace(fetchone=lambda: result)

        def __exit__(self, kind, error, tb):
            if kind is not None or db.fail_commit:
                db.rollbacks += 1
                if kind is None:
                    raise psycopg.OperationalError(db.secret)
            else:
                db.rows = self.rows

    db.secret = uuid4().hex
    db.key = uuid4().hex
    db.connect_calls = []

    def connect(url, **kwargs):
        db.connect_calls.append((url, kwargs))
        return Connection()

    monkeypatch.setattr('app.persistence.postgres.psycopg.connect', connect)
    db.store = lambda: PostgresStateStore(db.secret, db.key)
    return db


@pytest.fixture
def snapshot():
    return {'schema_version': 2, 'libraries': [{'id': 'b'}, {'id': 'a'}],
            'sources': [], 'extraction_jobs': [],
            'json_values': [None, True, False, 0, -7, 2.75, 'é — 漢字 🚀'],
            'knowledge_assets': [
                {'id': 'old', 'active': False, 'revision': 2, 'superseded_by': 'new',
                 'provenance': {'nested': [{'pages': [9, 2]}, {'unicode': 'é'}]}},
                {'id': 'new', 'active': True, 'revision': 3}],
            'outputs': [{'content': 'saved', 'asset_ids': ['new', 'old']}],
            'usage': {'calls': 7, 'tokens': {'input': 123, 'output': 45}}}


def test_empty_load_does_not_insert(database):
    assert database.store().load() is None
    assert database.rows == {}
    assert len(database.queries) == 1
    sql, parameters = database.queries[0]
    assert 'WHERE workspace_key = %s' in sql
    assert parameters == (database.key,)


def test_load_exact_snapshot_and_workspace_isolation(database, snapshot):
    database.rows[database.key] = (snapshot, 8)
    database.rows[uuid4().hex] = ({'other': True}, 99)
    store = database.store()
    assert store.load() == snapshot
    assert store._revision == 8


def test_insert_then_increment_and_roundtrip(database, snapshot):
    store = database.store()
    assert store.load() is None
    store.save(snapshot)
    assert database.rows[database.key] == (snapshot, 1)
    store.save(snapshot)
    assert database.rows[database.key] == (snapshot, 2)
    assert store._revision == 2
    assert database.store().load() == snapshot
    assert len(database.connect_calls) == 4
    assert 'ON CONFLICT (workspace_key) DO NOTHING RETURNING revision' in database.queries[1][0]
    assert 'revision = revision + 1' in database.queries[2][0]
    assert 'WHERE workspace_key = %s AND revision = %s' in database.queries[2][0]


@pytest.mark.parametrize('existing', [False, True])
def test_independent_writers_conflict_without_overwrite(database, existing):
    if existing:
        database.rows[database.key] = ({'before': True}, 0)
    first, second = database.store(), database.store()
    first.load()
    second.load()
    first.save({'winner': True})
    durable = deepcopy(database.rows)
    with pytest.raises(StaleStateWriteError, match='stale revision') as error:
        second.save({'loser': True})
    assert str(error.value) == STALE_WRITE_MESSAGE
    assert database.rows == durable
    assert database.rollbacks == 1
    assert second._revision == (0 if existing else None)
    second.load()
    second.save({'reloaded': True})
    assert database.rows[database.key] == ({'reloaded': True}, 2)


@pytest.mark.parametrize('operation', ['load', 'save'])
def test_database_errors_surface_and_are_sanitized(database, operation, caplog):
    store = database.store()
    store.load()
    database.fail_execute = True
    with pytest.raises(HostedStateStoreError) as error:
        store.load() if operation == 'load' else store.save({'value': 1})
    assert str(error.value) == f'Hosted state {operation} failed: database operation failed.'
    assert database.secret not in ''.join(traceback.format_exception(error.value))
    assert database.secret not in caplog.text
    assert database.rows == {}


def test_connection_error_is_not_missing(monkeypatch):
    secret = uuid4().hex
    def fail(*args, **kwargs):
        raise psycopg.OperationalError(secret)
    monkeypatch.setattr('app.persistence.postgres.psycopg.connect', fail)
    with pytest.raises(HostedStateStoreError):
        PostgresStateStore(secret, uuid4().hex).load()


@pytest.mark.parametrize('existing', [False, True])
def test_failed_commit_preserves_snapshot_and_expected_revision(database, snapshot, existing):
    if existing:
        database.rows[database.key] = (snapshot, 5)
    store = database.store()
    store.load()
    before = deepcopy(database.rows)
    revision = store._revision
    database.fail_commit = True
    with pytest.raises(HostedStateStoreError):
        store.save({'replacement': True})
    assert database.rows == before
    assert store._revision == revision
    assert database.rollbacks == 1
    database.fail_commit = False
    store.save({'retry': True})
    assert store._revision == (6 if existing else 1)


def test_save_requires_load(database):
    with pytest.raises(RuntimeError, match=r'requires load\(\) before save'):
        database.store().save({})
    assert database.connect_calls == []


@pytest.mark.parametrize('missing', ['KNOWLEDGE_ENGINE_DATABASE_URL', 'KNOWLEDGE_ENGINE_WORKSPACE_KEY'])
@pytest.mark.parametrize('value', ['', '   '])
def test_missing_configuration(missing, value):
    values = [uuid4().hex, uuid4().hex]
    values[0 if missing.endswith('DATABASE_URL') else 1] = value
    with pytest.raises(RuntimeError) as error:
        PostgresStateStore(*values)
    assert str(error.value) == f'Hosted StateStore requires {missing}.'


@pytest.mark.parametrize('payload', [None, [], [1], 'scalar', 42, 2.75, True, False])
def test_non_dictionary_payload_rejected(database, payload):
    database.rows[database.key] = (payload, 4)
    store = database.store()
    with pytest.raises(HostedStateIntegrityError) as error:
        store.load()
    assert str(error.value) == (
        'Hosted state load failed: stored payload must be a dictionary JSON snapshot.'
    )
    assert not store._loaded
    assert store._revision is None
    assert database.rows[database.key] == (payload, 4)
    assert database.rollbacks == 1
    with pytest.raises(RuntimeError, match=r'requires load\(\) before save'):
        store.save({})


def test_invalid_reload_blocks_save_until_valid_load(database):
    database.rows[database.key] = ({'valid': True}, 4)
    store = database.store()
    store.load()
    database.rows[database.key] = (None, 5)
    with pytest.raises(HostedStateIntegrityError):
        store.load()
    with pytest.raises(RuntimeError, match=r'requires load\(\) before save'):
        store.save({})
    database.rows[database.key] = ({'repaired': True}, 6)
    assert store.load() == {'repaired': True}
    store.save({'saved': True})
    assert database.rows[database.key] == ({'saved': True}, 7)
