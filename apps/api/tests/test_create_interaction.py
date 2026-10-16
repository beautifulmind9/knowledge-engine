from pathlib import Path


def test_natural_create_adapter_prepares_generates_and_saves_grounded_output(client, knowledge, monkeypatch):
    import json
    import subprocess
    from types import SimpleNamespace
    from app.services import ai_gateway

    source = client.get(f"/sources/{knowledge['source_id']}").json()
    catalog = {
        "sources": [source],
        "libraries": client.get('/libraries').json()['items'],
        "modes": client.get('/outputs/modes').json()['items'],
        "selectedAssetIds": [knowledge['id']],
    }
    request = "Write a LinkedIn post about practice breaks.\nPreserve my final pause. Avoid jargon."
    javascript = """
import {newInteractionDraft,interpretDraft,correctDraft,workshopRequest} from './apps/web/interaction-draft.js';
const [catalog,request,sourceId,assetId]=JSON.parse(process.argv[1]);
let draft=interpretDraft(newInteractionDraft(request),catalog);
draft=correctDraft(draft,'preserve','Keep my final reflection');
draft=correctDraft(draft,'scope',{libraryId:null,sourceIds:[sourceId],assetIds:[assetId]});
console.log(JSON.stringify(workshopRequest(draft,catalog)));
"""
    result = subprocess.run(
        ['node', '--input-type=module', '-e', javascript,
         json.dumps([catalog, request, source['id'], knowledge['id']])],
        cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True, check=True,
    )
    payload = json.loads(result.stdout)
    calls = []

    def generate(model, prompt, schema):
        calls.append(prompt)
        return SimpleNamespace(output_text=json.dumps({
            'title': 'Make space for practice', 'output_type': 'social_content',
            'content': 'Use practice breaks to help participants retain learning. Leave time for a final reflection.',
            'applied_knowledge': [{'asset_id': knowledge['id'], 'usage_note': 'Practice breaks ground this post.'}],
            'design_choices': ['The final reflection is a creator-directed drafting choice.'],
        }), id='mock-natural-create')

    monkeypatch.setattr(ai_gateway, 'generate', generate)
    prepared = client.post('/workshops/prepare', json=payload)
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()['knowledge_unit_count'] == 1
    assert not calls  # Preparation has no provider attempt.
    payload['prepared_snapshot_id'] = prepared.json()['prepared_snapshot_id']
    def unexpected_retrieval(*args, **kwargs):
        raise AssertionError('Generation must use the reviewed snapshot without retrieval')
    monkeypatch.setattr('app.services.workshop_generation.prepare_workshop', unexpected_retrieval)
    response = client.post('/workshops/generate', json=payload)
    assert response.status_code == 200, response.text
    assert len(calls) == 1
    saved = response.json()['saved_output']
    assert saved['brief']['situation'].startswith(request)
    assert saved['brief']['preserve'] == ['Keep my final reflection']
    assert saved['brief']['avoid'] == ['Avoid jargon.']
    assert saved['brief']['output_format'] == 'LinkedIn post'
    assert saved['source_ids'] == [source['id']]
    assert saved['applied_knowledge'][0]['asset_id'] == knowledge['id']
    assert saved['knowledge_snapshot'] == prepared.json()['knowledge_units']
    assert saved['knowledge_snapshot'][0]['canonical_asset']['chunk_id'] == knowledge['chunk_id']
    assert client.get(f"/outputs/{saved['id']}").json() == saved


def _preview_payload(knowledge):
    return {'situation': 'Write about practice breaks for learning.', 'goal': 'Help people learn.',
            'output_type': 'writing', 'source_ids': [knowledge['source_id']], 'interaction_revision': 7}


def test_create_reports_real_partial_section_coverage(client, knowledge, source):
    from app.services.text_chunking import load_chunks, save_chunks
    from app.db import mock_data as db
    s = next(s for s in db.sources if s['id'] == knowledge['source_id'])
    chunks = load_chunks(s['chunks_path'])
    # One completed extraction; a second section has not been interpreted.
    chunks = chunks + [{**chunks[0], 'id': f"chunk_{s['id']}_002", 'chunk_index': 2}]
    save_chunks(s['id'], chunks)
    from app.services.chunk_manifest import manifest_from_chunks
    s['chunk_manifest'] = manifest_from_chunks(s['id'], chunks)
    prepared = client.post('/workshops/prepare', json=_preview_payload(knowledge))
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()['source_coverage'] == [{
        'source_id': s['id'], 'title': s['title'], 'prepared_sections': 1,
        'total_sections': 2, 'relevant_idea_count': 1,
    }]
    # Preview generation performs no additional extraction/preparation of sections.
    assert len(db.extraction_jobs) == 1


def test_snapshot_rejects_changed_brief_revision_missing_forged_and_expired_references_before_provider(client, knowledge, monkeypatch):
    from app.services import prepared_evidence
    from app.services import ai_gateway
    calls = []
    monkeypatch.setattr(ai_gateway, 'generate', lambda *a, **kw: calls.append(a))
    payload = _preview_payload(knowledge)
    preview = client.post('/workshops/prepare', json=payload).json()
    token = preview['prepared_snapshot_id']
    for changes in [
        {'interaction_revision': 8}, {'goal': 'Another goal'}, {'constraints': ['Under 100 words']},
        {'source_ids': []}, {'asset_ids': ['forged']}, {'prepared_snapshot_id': 'not-a-real-snapshot-reference'},
        {'prepared_snapshot_id': None},
    ]:
        r = client.post('/workshops/generate', json={**payload, 'prepared_snapshot_id': token, **changes})
        assert r.status_code == 409, r.text
    expiry, brief, evidence = prepared_evidence._snapshots[token]
    prepared_evidence._snapshots[token] = (0, brief, evidence)
    assert client.post('/workshops/generate', json={**payload, 'prepared_snapshot_id': token}).status_code == 409
    assert calls == []


def test_snapshot_is_server_owned_independent_of_returned_preview_and_current_ranking(client, knowledge, monkeypatch):
    from app.services.prepared_evidence import resolve_preparation
    from app.models.workshop_generation import WorkshopGenerateRequest
    from app.db import mock_data as db
    payload = _preview_payload(knowledge)
    preview = client.post('/workshops/prepare', json=payload).json()
    expected = preview['knowledge_units'][0]['canonical_asset']['title']
    preview['knowledge_units'][0]['canonical_asset']['title'] = 'Client tampering'
    db.knowledge_assets[0]['title'] = 'Later knowledge change'
    resolved = resolve_preparation(WorkshopGenerateRequest(**payload, prepared_snapshot_id=preview['prepared_snapshot_id']))
    assert resolved['knowledge_units'][0]['canonical_asset']['title'] == expected
    resolved['knowledge_units'].clear()
    assert len(resolve_preparation(WorkshopGenerateRequest(**payload, prepared_snapshot_id=preview['prepared_snapshot_id']))['knowledge_units']) == 1
    db.sources.clear()
    assert client.post('/workshops/generate', json={**payload, 'prepared_snapshot_id': preview['prepared_snapshot_id']}).status_code == 409


def test_snapshot_eviction_fails_closed_and_unknown_coverage_is_not_complete(client, knowledge, monkeypatch):
    from app.services import prepared_evidence
    from app.db import mock_data as db
    monkeypatch.setattr(prepared_evidence, 'MAX_SNAPSHOTS', 1)
    payload = _preview_payload(knowledge)
    first = client.post('/workshops/prepare', json=payload).json()
    db.sources[0].pop('chunks_path', None)
    second = client.post('/workshops/prepare', json=payload).json()
    assert second['source_coverage'][0]['prepared_sections'] is None
    assert second['source_coverage'][0]['total_sections'] is None
    assert client.post('/workshops/generate', json={**payload, 'prepared_snapshot_id': first['prepared_snapshot_id']}).status_code == 409
