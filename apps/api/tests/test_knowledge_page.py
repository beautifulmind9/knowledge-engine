from pathlib import Path
import subprocess
from app.db import mock_data as db


def test_browser_state_regressions():
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(['node', '--test', 'apps/web/tests/knowledge-browser.test.mjs'], cwd=root, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_specific_search_excludes_generic_prioritization_match(client, knowledge):
    db.knowledge_assets.extend([
        {**knowledge, 'id': 'facilitation', 'title': 'One-on-one facilitation approach',
         'what_it_says': 'Facilitation in individual conversations.', 'keywords': ['facilitation'], 'evidence': 'Individual facilitation.'},
        {**knowledge, 'id': 'economics', 'title': 'One economic prioritization approach',
         'what_it_says': 'Choose one task with the highest economic return.', 'keywords': ['economic'], 'evidence': 'Choose one task.'},
    ])
    result = client.get('/knowledge-assets/search', params={'q': 'One-on-one facilitation approach', 'consolidated': 'true', 'source_id': knowledge['source_id']}).json()
    assert [g['canonical_asset']['id'] for g in result['items']] == ['facilitation']


def test_search_library_and_source_scope(client, knowledge):
    library = client.post('/libraries', json={'name': 'Other library'}).json()
    source = client.post('/sources', json={'library_id': library['id'], 'title': 'Other source'}).json()
    db.knowledge_assets.append({**knowledge, 'id': 'other', 'source_id': source['id']})
    result = client.get('/knowledge-assets/search', params={'q': 'practice', 'consolidated': 'true', 'library_id': library['id']}).json()
    assert [g['canonical_asset']['id'] for g in result['items']] == ['other']
    result = client.get('/knowledge-assets/search', params={'q': 'practice', 'consolidated': 'true', 'source_id': knowledge['source_id']}).json()
    assert all(g['source_ids'] == [knowledge['source_id']] for g in result['items'])
