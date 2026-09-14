import copy
import json
from types import SimpleNamespace

import pytest

from app.db import mock_data as db
from app.services import ai_gateway
from app.services.batch_knowledge_extraction import (
    BATCH_REQUIRED_ASSET_FIELDS,
    run_gemini_knowledge_extraction_batch as run_batch,
)
from app.services.knowledge_extraction import create_extraction_job, persist_state, complete_extraction_job
from app.models.knowledge_extraction import KnowledgeExtractionResultSubmission
from app.services.text_chunking import save_chunks


@pytest.fixture
def batch(source, asset):
    s, c = source
    chunks = [{**c, 'id': f'chunk_batch_{i}', 'text': f'Original chunk {i}: practice breaks.'} for i in range(10)]
    db.sources[0]['chunks_path'] = save_chunks(s['id'], chunks)
    jobs = [create_extraction_job(s['id'], c['id']) for c in chunks]
    groups = [{'chunk_id': c['id'], 'assets': [{**asset, 'title': f'Chunk {i}',
                'source_id': 'untrusted-source', 'chunk_id': 'untrusted-chunk'}]} for i, c in enumerate(chunks)]
    return s, jobs, groups


def provider(monkeypatch, response=None, error=None):
    """Exercise the real gateway/accounting, replacing only the SDK client."""
    monkeypatch.setenv('GEMINI_API_KEY', 'fixture-key')
    monkeypatch.setenv('GEMINI_FREE_TIER_CONFIRMED', 'true')
    monkeypatch.setenv('GEMINI_ALLOW_REPAIR', 'true')  # batch must ignore this opt-in
    calls = []
    class FakeClient:
        def __init__(self, **kwargs):
            self.interactions = self
            self.sdk_configuration = SimpleNamespace(retry_config=SimpleNamespace(strategy='retry'))
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def create(self, **kwargs):
            assert self.sdk_configuration.retry_config.strategy == 'none'
            calls.append(kwargs)
            if error: raise error
            return SimpleNamespace(output_text=json.dumps(response), id='batch-response')
    monkeypatch.setattr(ai_gateway.genai, 'Client', FakeClient)
    return calls


def test_ten_chunks_one_gateway_call_and_usage_increment(client, batch, monkeypatch):
    s, jobs, groups = batch
    calls = provider(monkeypatch, {'results': list(reversed(groups))})
    gateway_calls = []
    original = ai_gateway.generate
    def counted(*args):
        gateway_calls.append(args)
        return original(*args)
    monkeypatch.setattr(ai_gateway, 'generate', counted)
    before = client.get('/usage').json()['calls_today']
    response = client.post(f"/sources/{s['id']}/interpret?max_chunks=10")
    assert response.status_code == 200, response.text
    assert response.json()['processed_this_run'] == 10
    assert len(calls) == len(gateway_calls) == 1
    assert client.get('/usage').json()['calls_today'] == before + 1
    payload = json.loads(calls[0]['input'])
    assert [c['chunk_id'] for c in payload['chunks']] == [j['chunk_id'] for j in jobs]
    assert all(c['source_id'] == s['id'] and c['chunk_text'] for c in payload['chunks'])
    instructions = payload['instructions']
    for field in BATCH_REQUIRED_ASSET_FIELDS:
        assert field in instructions
    assert 'omit that candidate rather than returning an incomplete object' in instructions
    assert 'verify that all six required fields are present' in instructions
    for i, job in enumerate(jobs):
        saved = next(a for a in db.knowledge_assets if a['extraction_job_id'] == job['id'])
        assert (saved['source_id'], saved['chunk_id'], saved['title']) == (s['id'], job['chunk_id'], f'Chunk {i}')
        assert saved['extraction_version'] == 1 and job['status'] == 'completed'


@pytest.mark.parametrize('bad', ['missing', 'duplicate', 'unknown', 'envelope'])
def test_bad_routing_rejects_entire_batch(batch, monkeypatch, bad):
    _, jobs, groups = batch
    if bad == 'missing': groups.pop()
    if bad == 'duplicate': groups[-1]['chunk_id'] = groups[0]['chunk_id']
    if bad == 'unknown': groups[-1]['chunk_id'] = 'unknown'
    calls = provider(monkeypatch, {'results': groups} if bad != 'envelope' else {'wrong': groups})
    with pytest.raises(ValueError): run_batch([j['id'] for j in jobs])
    assert len(calls) == 1 and not db.knowledge_assets
    assert all(j['status'] == 'failed' for j in jobs)


def seed_replacements(jobs, groups):
    for job, group in zip(jobs, groups):
        data = [{**a, 'source_id': job['source_id'], 'chunk_id': job['chunk_id']} for a in group['assets']]
        complete_extraction_job(job['id'], KnowledgeExtractionResultSubmission(assets=data).assets)
    old = copy.deepcopy(db.knowledge_assets)
    replacements = [create_extraction_job(j['source_id'], j['chunk_id'], reprocess=True) for j in jobs]
    return old, replacements


def test_invalid_chunk_preserves_old_extraction_and_other_replacements(batch, monkeypatch):
    _, jobs, groups = batch
    old, replacements = seed_replacements(jobs, groups)
    # Even a valid first asset in this group must not be saved if another fails.
    groups[0]['assets'].append({**groups[0]['assets'][0], 'asset_type': 'process', 'steps': []})
    calls = provider(monkeypatch, {'results': groups})
    result = run_batch([j['id'] for j in replacements])
    assert len(calls) == 1 and len(result['results']) == 9 and len(result['failures']) == 1
    assert db.knowledge_assets[0] == old[0]
    assert replacements[0]['status'] == 'failed'
    assert len([a for a in db.knowledge_assets if a['chunk_id'] == jobs[0]['chunk_id']]) == 1
    for job in replacements[1:]:
        active = [a for a in db.knowledge_assets if a['chunk_id'] == job['chunk_id'] and a['active']]
        assert len(active) == 1 and active[0]['extraction_version'] == 2
        assert next(a for a in db.knowledge_assets if a['chunk_id'] == job['chunk_id'] and not a['active'])['superseded_by_job_id'] == job['id']


@pytest.mark.parametrize('failure', ['provider', 'quota', 'local_cap'])
def test_provider_and_quota_failure_preserve_previous_data(client, batch, monkeypatch, failure):
    _, jobs, groups = batch
    old, replacements = seed_replacements(jobs, groups)
    calls = provider(monkeypatch, error=RuntimeError('429 quota' if failure == 'quota' else 'provider unavailable'))
    if failure == 'local_cap': monkeypatch.setenv('GEMINI_DAILY_CALL_LIMIT', '0')
    with pytest.raises(Exception): run_batch([j['id'] for j in replacements])
    assert db.knowledge_assets == old
    assert all(j['status'] == 'failed' for j in replacements)
    assert len(calls) == (0 if failure == 'local_cap' else 1)
    assert client.get('/usage').json()['calls_today'] == len(calls)


@pytest.mark.parametrize('mode', ['batch', 'legacy'])
def test_single_chunk_remains_supported(source, asset, monkeypatch, mode):
    from app.services.gemini_knowledge_extraction import run_gemini_knowledge_extraction
    s, c = source
    job = create_extraction_job(s['id'], c['id'])
    response = {'assets': [asset]}
    if mode == 'batch': response = {'results': [{'chunk_id': c['id'], **response}]}
    calls = provider(monkeypatch, response)
    if mode == 'batch': run_batch([job['id']])
    else: run_gemini_knowledge_extraction(job['id'])
    assert job['status'] == 'completed' and len(calls) == 1
    assert db.knowledge_assets[0]['chunk_id'] == c['id']


def test_batch_bounds_fail_before_provider(batch, monkeypatch):
    _, jobs, _ = batch
    calls = provider(monkeypatch)
    for ids in ([], [jobs[0]['id']] * 2, [j['id'] for j in jobs] + ['extra']):
        with pytest.raises(ValueError): run_batch(ids)
    assert not calls and all(j['status'] == 'pending_ai' for j in jobs)


@pytest.mark.parametrize('invalid', ['missing_assets', 'extra_field', 'wrong_assets_type'])
def test_invalid_group_shape_is_isolated(batch, monkeypatch, invalid):
    _, jobs, groups = batch
    if invalid == 'missing_assets': del groups[0]['assets']
    elif invalid == 'extra_field': groups[0]['unknown'] = True
    else: groups[0]['assets'] = 'not an array'
    calls = provider(monkeypatch, {'results': groups})
    result = run_batch([j['id'] for j in jobs])
    assert len(calls) == 1 and len(result['results']) == 9
    assert jobs[0]['status'] == 'failed'
    assert not any(a['chunk_id'] == jobs[0]['chunk_id'] for a in db.knowledge_assets)


def test_empty_assets_are_valid_chunk_completions(batch, monkeypatch):
    _, jobs, groups = batch
    for group in groups: group['assets'] = []
    calls = provider(monkeypatch, {'results': groups})
    result = run_batch([j['id'] for j in jobs])
    assert len(result['results']) == 10 and not result['failures']
    assert len(calls) == 1 and not db.knowledge_assets
    assert all(j['status'] == 'completed' for j in jobs)


def test_interpret_limit_and_single_chunk_batch(client, batch, monkeypatch):
    s, jobs, groups = batch
    calls = provider(monkeypatch, {'results': groups[:1]})
    assert client.post(f"/sources/{s['id']}/interpret?max_chunks=11").status_code == 422
    assert not calls
    response = client.post(f"/sources/{s['id']}/interpret?max_chunks=1")
    assert response.status_code == 200 and response.json()['processed_this_run'] == 1
    assert len(calls) == 1 and jobs[0]['status'] == 'completed'
    assert all(j['status'] == 'pending_ai' for j in jobs[1:])
