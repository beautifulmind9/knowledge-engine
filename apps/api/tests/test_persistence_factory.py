"""Exercise startup configuration in fresh processes, without reloading live modules."""
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from app.persistence import factory

API_ROOT = Path(__file__).resolve().parents[1]
MODE_ENV = 'KNOWLEDGE_ENGINE_PERSISTENCE_MODE'


def run_configuration(code, root, mode=None):
    env = os.environ.copy()
    env.pop(MODE_ENV, None)
    env.pop('KNOWLEDGE_ENGINE_DATABASE_URL', None)
    env.pop('KNOWLEDGE_ENGINE_WORKSPACE_KEY', None)
    env.pop('KNOWLEDGE_ENGINE_PUBLIC_HOST', None)
    for name in ('SUPABASE_URL', 'SUPABASE_SECRET_KEY', 'KNOWLEDGE_ENGINE_STORAGE_BUCKET'):
        env.pop(name, None)
    for name in ('KNOWLEDGE_ENGINE_BETA_PASSWORD', 'KNOWLEDGE_ENGINE_SESSION_SECRET'):
        env.pop(name, None)
    if mode == 'hosted':
        env.update(SUPABASE_URL='https://offline.supabase.co', SUPABASE_SECRET_KEY='sb_secret_offline',
                   KNOWLEDGE_ENGINE_STORAGE_BUCKET='knowledge-engine-artifacts',
                   KNOWLEDGE_ENGINE_BETA_PASSWORD='offline-beta-password',
                   KNOWLEDGE_ENGINE_PUBLIC_HOST='offline.onrender.com',
                   KNOWLEDGE_ENGINE_SESSION_SECRET=__import__('secrets').token_urlsafe(32))
    env.pop('GEMINI_API_KEY', None)
    env.pop('GEMINI_FREE_TIER_CONFIRMED', None)
    if mode is not None:
        env[MODE_ENV] = mode
    if root is None:
        env.pop('KNOWLEDGE_ENGINE_STORAGE', None)
    else:
        env['KNOWLEDGE_ENGINE_STORAGE'] = str(root)
    guard = (
        "import sys\n"
        f"sys.path.insert(0, {str(API_ROOT / 'tests')!r})\n"
        "from postgres_test_guard import install_postgres_guard\n"
        "install_postgres_guard()\n"
        "from storage_test_guard import install_storage_guard\n"
        "install_storage_guard()\n"
    )
    result = subprocess.run([sys.executable, '-c', guard + textwrap.dedent(code)], cwd=API_ROOT,
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


@pytest.mark.parametrize('mode', [None, 'local'])
def test_local_configuration_paths_instances_and_no_eager_io(tmp_path, mode):
    root = tmp_path / 'storage'
    run_configuration('''
        import os
        from pathlib import Path
        from app.persistence import factory
        from app.db import persistence
        from app.persistence.sqlite import SQLiteStateStore
        from app.persistence.local_artifacts import LocalArtifactStore
        assert factory.PERSISTENCE_MODE == 'local'
        root = Path(os.environ['KNOWLEDGE_ENGINE_STORAGE']).resolve()
        assert factory.API_ROOT == Path.cwd()
        assert persistence.API_ROOT == factory.API_ROOT
        assert persistence.STORAGE_ROOT == factory.STORAGE_ROOT == root
        assert persistence.STATE_PATH == factory.STATE_PATH == root / 'state.json'
        assert persistence.DB_PATH == factory.DB_PATH == root / 'knowledge.sqlite3'
        state = factory.get_state_store()
        assert isinstance(state, SQLiteStateStore)
        assert (state.storage_root, state.state_path, state.db_path, state.api_root) == (
            root, root / 'state.json', root / 'knowledge.sqlite3', Path.cwd())
        assert isinstance(factory.get_artifact_store(), LocalArtifactStore)
        assert factory.get_local_artifact_store() is factory.get_artifact_store()
        assert factory.get_state_store() is state is persistence.get_state_store()
        assert not root.exists()
        # A running process retains one configuration; changing env requires restart.
        os.environ['KNOWLEDGE_ENGINE_PERSISTENCE_MODE'] = 'hosted'
        os.environ['KNOWLEDGE_ENGINE_STORAGE'] = str(root / 'different')
        assert factory.get_state_store() is state
        assert factory.STORAGE_ROOT == root
    ''', root, mode)
    assert not root.exists()


def test_default_storage_path_is_unchanged():
    run_configuration('''
        from pathlib import Path
        from app.persistence import factory
        assert factory.STORAGE_ROOT == Path.cwd() / 'storage'
        assert factory.STATE_PATH == factory.STORAGE_ROOT / 'state.json'
        assert factory.DB_PATH == factory.STORAGE_ROOT / 'knowledge.sqlite3'
    ''', None)


@pytest.mark.parametrize('mode', ['hosted', 'unknown', '', 'LOCAL', ' local '])
@pytest.mark.parametrize('entrypoint', ['app.persistence.factory', 'app.main'])
def test_unsupported_modes_fail_before_local_construction_or_io(tmp_path, mode, entrypoint):
    root = tmp_path / 'must-not-exist'
    expected = ('Hosted StateStore requires KNOWLEDGE_ENGINE_DATABASE_URL.' if mode == 'hosted'
                else f"Invalid {MODE_ENV} value {mode!r}. Expected 'local' or 'hosted'.")
    code = '''
        import importlib
        from unittest.mock import patch
        from app.persistence.sqlite import SQLiteStateStore
        from app.persistence.local_artifacts import LocalArtifactStore
        with patch.object(SQLiteStateStore, '__init__', side_effect=AssertionError('local state constructed')) as state, \
             patch.object(LocalArtifactStore, '__init__', side_effect=AssertionError('local artifacts constructed')) as artifacts:
            try:
                importlib.import_module(ENTRYPOINT)
            except RuntimeError as error:
                assert str(error) == EXPECTED, str(error)
            else:
                raise AssertionError('startup unexpectedly succeeded')
            state.assert_not_called()
            artifacts.assert_not_called()
    '''.replace('ENTRYPOINT', repr(entrypoint)).replace('EXPECTED', repr(expected))
    run_configuration(code, root, mode)
    assert not root.exists()


def test_consumers_share_centralized_instances():
    from app.db import persistence
    from app.routers import control, sources, structure
    from app.services import text_chunking, text_extraction
    state = factory.get_state_store()
    artifact = factory.get_artifact_store()
    assert persistence.get_state_store() is state
    assert factory.get_local_artifact_store() is artifact
    for module in (control, sources, structure, text_chunking, text_extraction):
        assert module._artifact_store is artifact


def test_import_loads_and_migrates_once_without_rebinding(tmp_path):
    root = tmp_path / 'storage'
    root.mkdir()
    legacy = {'libraries': [], 'sources': [{'id': 'source_one', 'file_path': 'storage/uploads/one.txt'}],
              'extraction_jobs': [], 'knowledge_assets': [], 'outputs': [], 'usage': {}}
    original = json.dumps(legacy, indent=2).encode()
    (root / 'state.json').write_bytes(original)
    run_configuration('''
        import importlib
        import os
        import sqlite3
        from pathlib import Path
        from unittest.mock import patch
        from app.persistence.sqlite import SQLiteStateStore
        from app.persistence.local_artifacts import LocalArtifactStore
        root = Path(os.environ['KNOWLEDGE_ENGINE_STORAGE'])
        original_load = SQLiteStateStore.load
        original_read = Path.read_text
        original_state_init = SQLiteStateStore.__init__
        original_artifact_init = LocalArtifactStore.__init__
        calls = dict(load=0, legacy_read=0, state_init=0, artifact_init=0)
        def load(store):
            calls['load'] += 1
            return original_load(store)
        def read(path, *args, **kwargs):
            if path == root / 'state.json':
                calls['legacy_read'] += 1
            return original_read(path, *args, **kwargs)
        def state_init(store, *args, **kwargs):
            calls['state_init'] += 1
            original_state_init(store, *args, **kwargs)
        def artifact_init(store):
            calls['artifact_init'] += 1
            original_artifact_init(store)
        with patch.object(SQLiteStateStore, 'load', load), patch.object(Path, 'read_text', read), \
             patch.object(SQLiteStateStore, '__init__', state_init), patch.object(LocalArtifactStore, '__init__', artifact_init):
            from app.persistence import factory
            assert calls == dict(load=0, legacy_read=0, state_init=1, artifact_init=1)
            assert not factory.DB_PATH.exists()
            from app.db import mock_data as db
            assert calls == dict(load=1, legacy_read=1, state_init=1, artifact_init=1)
            assert db.sources[0]['file_path'] == str(root / 'uploads/one.txt')
            names = ('libraries', 'sources', 'extraction_jobs', 'knowledge_assets', 'outputs', 'usage')
            collections = [getattr(db, name) for name in names]
            from app.main import app
            for name in ('app.main', 'app.db.mock_data', 'app.persistence.factory'):
                importlib.import_module(name)
            assert calls == dict(load=1, legacy_read=1, state_init=1, artifact_init=1)
            from app.db import persistence
            persistence.save_state(db.libraries, db.sources, db.extraction_jobs, db.knowledge_assets)
            assert all(getattr(db, name) is value for name, value in zip(names, collections))
            assert persistence.load_state()['sources'] == db.sources
            assert calls == dict(load=2, legacy_read=1, state_init=1, artifact_init=1)
            with sqlite3.connect(factory.DB_PATH) as connection:
                assert connection.execute('SELECT count(*) FROM state').fetchone() == (1,)
    ''', root)
    assert (root / 'state.json').read_bytes() == original


def test_subprocess_configuration_does_not_contaminate_current_process(tmp_path):
    before = (factory.PERSISTENCE_MODE, factory.STORAGE_ROOT,
              factory.get_state_store(), factory.get_artifact_store())
    environment = os.environ.get(MODE_ENV)
    run_configuration('''
        try:
            import app.persistence.factory
        except RuntimeError as error:
            assert str(error) == 'Hosted StateStore requires KNOWLEDGE_ENGINE_DATABASE_URL.'
        else:
            raise AssertionError('hosted startup succeeded')
    ''', tmp_path / 'hosted', 'hosted')
    assert before == (factory.PERSISTENCE_MODE, factory.STORAGE_ROOT,
                      factory.get_state_store(), factory.get_artifact_store())
    assert os.environ.get(MODE_ENV) == environment


def test_hosted_configuration_and_startup_fail_closed(tmp_path):
    root = tmp_path / 'no-local-storage'
    run_configuration('''
        import os
        from uuid import uuid4
        from unittest.mock import patch
        from app.persistence.sqlite import SQLiteStateStore
        from app.persistence.local_artifacts import LocalArtifactStore
        from app.persistence.postgres import PostgresStateStore
        os.environ['KNOWLEDGE_ENGINE_DATABASE_URL'] = uuid4().hex
        # Missing workspace key fails before any connection or local construction.
        with patch('psycopg.connect') as connect, \
             patch.object(SQLiteStateStore, '__init__', side_effect=AssertionError('local state')), \
             patch.object(LocalArtifactStore, '__init__', side_effect=AssertionError('local artifacts')):
            try:
                import app.persistence.factory
            except RuntimeError as error:
                assert str(error) == 'Hosted StateStore requires KNOWLEDGE_ENGINE_WORKSPACE_KEY.'
            else:
                raise AssertionError('missing workspace accepted')
            os.environ['KNOWLEDGE_ENGINE_WORKSPACE_KEY'] = uuid4().hex
            from app.persistence import factory
            store = factory.get_state_store()
            assert isinstance(store, PostgresStateStore)
            assert store is factory.get_state_store()
            connect.assert_not_called()
            with patch.object(PostgresStateStore, 'load', return_value=None) as load:
                from app.db.persistence import load_state
                assert load_state() is None
                from app.persistence.supabase_artifacts import SupabaseArtifactStore
                assert isinstance(factory.get_artifact_store(), SupabaseArtifactStore)
                try:
                    factory.get_local_artifact_store()
                except RuntimeError as error:
                    assert str(error) == 'Local artifact capabilities are unavailable in hosted mode.'
                else:
                    raise AssertionError('local capabilities accepted')
                import app.main
            connect.assert_not_called()
    ''', root, 'hosted')
    assert not root.exists()
