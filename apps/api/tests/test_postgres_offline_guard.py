"""Prove the DB guard runs before collection/startup, even under hosted env."""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import textwrap
from uuid import uuid4

import psycopg
import pytest

from app.persistence import factory
from app.persistence.postgres import PostgresStateStore
from postgres_test_guard import PostgreSQLConnectionDenied
from test_persistence_factory import run_configuration

API_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('entrypoint', [psycopg.connect, psycopg.Connection.connect])
def test_unmocked_connections_denied(entrypoint, caplog):
    private_value = uuid4().hex
    with pytest.raises(PostgreSQLConnectionDenied) as error:
        entrypoint(private_value)
    assert str(error.value) == 'Real PostgreSQL connections are forbidden in backend tests.'
    assert private_value not in str(error.value) + caplog.text


def test_async_connection_denied():
    with pytest.raises(PostgreSQLConnectionDenied):
        asyncio.run(psycopg.AsyncConnection.connect(uuid4().hex))


def test_adapter_cannot_open_unmocked_connection():
    with pytest.raises(PostgreSQLConnectionDenied):
        PostgresStateStore(uuid4().hex, uuid4().hex).load()
    assert factory.PERSISTENCE_MODE == 'local'


def test_hosted_subprocess_startup_denies_unmocked_connection(tmp_path):
    root = tmp_path / 'no-storage'
    run_configuration('''
        import os
        from uuid import uuid4
        from postgres_test_guard import PostgreSQLConnectionDenied
        os.environ['KNOWLEDGE_ENGINE_DATABASE_URL'] = uuid4().hex
        os.environ['KNOWLEDGE_ENGINE_WORKSPACE_KEY'] = uuid4().hex
        from app.persistence import factory
        from app.persistence.postgres import PostgresStateStore
        assert isinstance(factory.get_state_store(), PostgresStateStore)
        try:
            import app.main
        except PostgreSQLConnectionDenied as error:
            assert str(error) == 'Real PostgreSQL connections are forbidden in backend tests.'
        else:
            raise AssertionError('unmocked hosted startup was not denied')
    ''', root, 'hosted')
    assert not root.exists()


def test_collection_with_inherited_hosted_environment_is_offline():
    env = os.environ.copy()
    env['KNOWLEDGE_ENGINE_PERSISTENCE_MODE'] = 'hosted'
    env['KNOWLEDGE_ENGINE_DATABASE_URL'] = uuid4().hex
    env['KNOWLEDGE_ENGINE_WORKSPACE_KEY'] = uuid4().hex
    code = '''
        import asyncio
        import os
        import pytest
        # conftest must run its guard before app.main imports during collection.
        assert os.environ['KNOWLEDGE_ENGINE_PERSISTENCE_MODE'] == 'hosted'
        result = pytest.main(['--collect-only', 'tests/test_postgres_state_store.py', '-q'])
        assert result == 0
        from app.persistence import factory
        from app.persistence.sqlite import SQLiteStateStore
        from postgres_test_guard import PostgreSQLConnectionDenied
        import psycopg
        assert factory.PERSISTENCE_MODE == 'local'
        assert isinstance(factory.get_state_store(), SQLiteStateStore)
        assert 'KNOWLEDGE_ENGINE_DATABASE_URL' not in os.environ
        assert 'KNOWLEDGE_ENGINE_WORKSPACE_KEY' not in os.environ
        for connect in (psycopg.connect, psycopg.Connection.connect):
            try:
                connect()
            except PostgreSQLConnectionDenied:
                pass
            else:
                raise AssertionError('unguarded connection after collection')
        try:
            asyncio.run(psycopg.AsyncConnection.connect())
        except PostgreSQLConnectionDenied:
            pass
        else:
            raise AssertionError('unguarded async connection after collection')
    '''
    result = subprocess.run([sys.executable, '-c', textwrap.dedent(code)], cwd=API_ROOT,
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
