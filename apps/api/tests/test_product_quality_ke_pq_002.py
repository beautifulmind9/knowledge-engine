"""KE-PQ-002 current-behavior characterization, not proposed quality guarantees.

All material is synthetic. No private export or provider connection is used.
"""
import json
from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter

from app.db import mock_data
from app.models.knowledge_asset import KnowledgeAsset
from app.models.workshop_generation import WorkshopGenerateRequest
from app.services import ai_gateway, workshop, workshop_generation


def asset(name, text, source='source_a'):
    value = TypeAdapter(KnowledgeAsset).validate_python({
        'asset_type': 'principle', 'id': name, 'source_id': source,
        'chunk_id': 'chunk_' + name, 'title': text, 'what_it_says': text,
        'evidence': text, 'keywords': text.lower().split(), 'confidence_score': 4,
    })
    return value.model_dump(mode='json')


def payload(text='Storytelling psychology', mode='research_synthesis', **kwargs):
    selected = kwargs.pop('source_ids', ['source_a'])
    return WorkshopGenerateRequest(situation=text, goal=text, output_type=mode,
                                   source_ids=selected, save=False, **kwargs)


def pool(monkeypatch, assets):
    monkeypatch.setattr(mock_data, 'sources', [
        {'id': sid, 'library_id': 'library_synthetic', 'title': sid}
        for sid in sorted({a['source_id'] for a in assets})
    ])
    monkeypatch.setattr(workshop, 'list_knowledge_assets', lambda **_: assets)


def prepared(assets):
    groups = workshop.consolidate_knowledge_assets(assets)
    return {'brief': {'situation': 'Storytelling psychology', 'goal': 'Storytelling psychology',
                      'constraints': []}, 'knowledge_units': groups,
            'knowledge_unit_count': len(groups), 'synthesis_context': {}}


def fake_provider(monkeypatch, mode, ref='asset_a'):
    calls = []
    output = {'title': 'Synthetic finding',
              'applied_knowledge': [{'asset_id': ref, 'usage_note': 'Synthetic reference.'}],
              'design_choices': []}
    if mode == 'knowledge_answer':
        output.update(introduction='', sections=[{
            'kind': 'source_principle', 'heading': 'A finding',
            'content': 'Storytelling can be considered using the supplied evidence.',
            'evidence_refs': [ref],
        }])
    else:
        output.update(output_type=mode, content='Synthesis: A synthetic discussion. Supporting ideas: supplied evidence. Gaps: unknown.')
    def generate(*args):
        calls.append(args)
        return SimpleNamespace(output_text=json.dumps(output), id='synthetic-response')
    monkeypatch.setattr(ai_gateway, 'generate', generate)
    monkeypatch.setattr(workshop, 'evidence_base_state', lambda *_: {
        'selected_count': 2, 'selected_source_ids': ['source_a', 'source_b'],
        'ready_count': 2, 'preparing_count': 0, 'attention_count': 0, 'unavailable_count': 0,
    })
    return calls


def test_long_request_can_reverse_direct_and_marketing_ranking(monkeypatch):
    direct = asset('asset_direct', 'Storytelling psychology')
    marketing = asset('asset_marketing', 'Marketing branding customers sales pricing promotion')
    pool(monkeypatch, [direct, marketing])
    short = workshop._retrieve_raw_assets(payload())
    long = workshop._retrieve_raw_assets(payload('Storytelling psychology marketing branding customers sales pricing promotion'))
    assert short[0]['id'] == 'asset_direct'
    assert long[0]['id'] == 'asset_marketing'
    assert {a['id'] for a in long} == {'asset_direct', 'asset_marketing'}


def test_repeated_constraints_do_not_reweight_the_same_request_terms():
    item = asset('asset_a', 'Storytelling psychology')
    base = payload()
    repeated = payload('Storytelling psychology storytelling psychology')
    assert workshop._workshop_relevance(item, base) == workshop._workshop_relevance(item, repeated)
    constrained = payload(constraints=['Storytelling psychology'])
    assert workshop.build_workshop_query(base) == workshop.build_workshop_query(constrained)
    assert workshop._workshop_relevance(item, constrained)[0] > workshop._workshop_relevance(item, base)[0]
    duplicated = payload(constraints=['Storytelling psychology', 'Storytelling psychology'])
    assert workshop._workshop_relevance(item, duplicated) == workshop._workshop_relevance(item, constrained)


def test_weak_incidental_match_is_admitted(monkeypatch):
    pool(monkeypatch, [asset('asset_a', 'Marketing customers')])
    result = workshop._retrieve_raw_assets(payload('Storytelling psychology marketing'))
    assert len(result) == 1
    assert result[0]['matched_terms'] == ['marketing']


@pytest.mark.parametrize('mode', ['knowledge_answer', 'research_synthesis'])
def test_empty_evidence_rejects_before_provider(monkeypatch, mode):
    calls = fake_provider(monkeypatch, mode)
    with pytest.raises(RuntimeError, match='No relevant knowledge'):
        workshop_generation.generate_workshop_output(payload(mode=mode), prepared=prepared([]))
    assert calls == []


@pytest.mark.parametrize('mode', ['knowledge_answer', 'research_synthesis'])
def test_weak_only_evidence_does_not_gate_generation(monkeypatch, mode):
    items = [asset('asset_a', 'Marketing customers')]
    pool(monkeypatch, items)
    calls = fake_provider(monkeypatch, mode)
    request = payload('Storytelling psychology marketing', mode=mode)
    snapshot = workshop.prepare_workshop(request)
    result = workshop_generation.generate_workshop_output(request, prepared=snapshot)
    assert len(calls) == 1
    assert result['knowledge_unit_count'] == 1
    assert 'evidence_coverage' in result
    assert ('reasoning_sections' in calls[0][2].get('properties', {})) is False
    assert ('sections' in calls[0][2].get('properties', {})) == (mode == 'knowledge_answer')


def test_single_source_answer_fallback_differs_from_research_synthesis(monkeypatch):
    pool(monkeypatch, [asset('asset_a', 'Garden soil')])
    assert workshop._retrieve_raw_assets(payload()) == []
    result = workshop._retrieve_raw_assets(payload(mode='knowledge_answer'))
    assert result[0]['relevance_score'] == 1
    assert result[0]['matched_terms'] == []


def test_normal_group_shape_counts_one_used_idea_and_only_cited_member_source(monkeypatch):
    items = [asset('asset_a', 'Storytelling psychology'),
             asset('asset_b', 'Storytelling psychology', 'source_b')]
    snapshot = prepared(items)
    assert len(snapshot['knowledge_units']) == 1
    calls = fake_provider(monkeypatch, 'knowledge_answer', ref='asset_a')
    result = workshop_generation.generate_workshop_output(payload(mode='knowledge_answer', source_ids=['source_a', 'source_b']), prepared=snapshot)
    coverage = result['evidence_coverage']
    assert len(calls) == 1
    assert result['output']['reasoning_sections'][0]['supporting_asset_ids'] == ['asset_a']
    # Normal prepare_workshop groups have canonical_asset.id, not asset_id.
    assert 'asset_id' not in snapshot['knowledge_units'][0]
    assert coverage['used_idea_count'] == 1
    assert coverage['used_source_count'] == 1
    assert coverage['used_source_ids'] == ['source_a']
    assert len(result['output']['applied_knowledge']) == 1


@pytest.mark.parametrize('compact', [False, True])
def test_member_and_canonical_references_count_once_without_counting_unused_units(monkeypatch, compact):
    items = [asset('asset_a', 'Storytelling psychology'),
             asset('asset_b', 'Storytelling psychology', 'source_b'),
             asset('asset_unused', 'Garden soil')]
    snapshot = prepared(items)
    if compact:
        for group in snapshot['knowledge_units']:
            group['asset_id'] = group['canonical_asset']['id']
    fake_provider(monkeypatch, 'knowledge_answer', ref='asset_b')
    # Applied IDs remain canonical under the existing provider contract.
    response = {'title': 'Synthetic finding', 'introduction': '', 'sections': [
        {'kind': 'source_principle', 'heading': 'Finding', 'content': 'Synthetic supported finding.',
         'evidence_refs': ['asset_a', 'asset_b', 'asset_b']}],
        'applied_knowledge': [{'asset_id': 'asset_a', 'usage_note': 'Synthetic use.'}], 'design_choices': []}
    monkeypatch.setattr(ai_gateway, 'generate', lambda *_: SimpleNamespace(output_text=json.dumps(response), id='synthetic'))
    result = workshop_generation.generate_workshop_output(payload(mode='knowledge_answer', source_ids=['source_a', 'source_b']), prepared=snapshot)
    assert result['knowledge_unit_count'] == 2
    assert result['evidence_coverage']['used_idea_count'] == 1
    assert result['evidence_coverage']['used_source_ids'] == ['source_a', 'source_b']


@pytest.mark.parametrize('kind', ['agreement', 'source_principle'])
def test_one_member_cannot_establish_cross_source_agreement_or_broad_coverage(monkeypatch, kind):
    from app.services.workshop_generation import GroundedAnswerValidationError
    snapshot = prepared([asset('asset_a', 'Storytelling psychology'),
                         asset('asset_b', 'Storytelling psychology', 'source_b')])
    fake_provider(monkeypatch, 'knowledge_answer')
    response = {'title': 'Synthetic finding', 'introduction': 'Across the selected sources, the corpus supports this finding.' if kind == 'source_principle' else '', 'sections': [
        {'kind': kind, 'heading': 'Agreement', 'content': 'The materials agree.',
         'evidence_refs': ['asset_a']}],
        'applied_knowledge': [{'asset_id': 'asset_a', 'usage_note': 'Synthetic use.'}], 'design_choices': []}
    monkeypatch.setattr(ai_gateway, 'generate', lambda *_: SimpleNamespace(output_text=json.dumps(response), id='synthetic'))
    with pytest.raises(GroundedAnswerValidationError, match='distinct materials|broader source coverage'):
        workshop_generation.generate_workshop_output(payload(mode='knowledge_answer', source_ids=['source_a', 'source_b']), prepared=snapshot)


def test_legacy_provenance_does_not_expand_ambiguous_group():
    from app.services.evidence_accounting import reference_maps
    unit = {'asset_id': 'asset_a', 'asset_ids': ['asset_a', 'asset_b'],
            'source_id': 'source_a', 'source_ids': ['source_a', 'source_b']}
    canonical, sources = reference_maps([unit])
    assert canonical == {'asset_a': 'asset_a', 'asset_b': 'asset_a'}
    assert sources['asset_a'] == {'source_a'}
    assert sources['asset_b'] == set()
    unit['source_ids'] = ['source_a']
    assert reference_maps([unit])[1]['asset_b'] == {'source_a'}


def test_saved_output_and_export_preserve_context_without_crediting_uncited_sources(monkeypatch):
    from app.services.outputs import save_output, export_markdown
    snapshot = prepared([asset('asset_a', 'Storytelling psychology'),
                         asset('asset_b', 'Storytelling psychology', 'source_b')])
    calls = fake_provider(monkeypatch, 'research_synthesis')
    result = workshop_generation.generate_workshop_output(payload(source_ids=['source_a', 'source_b']), prepared=snapshot)
    saved = save_output(result)
    assert len(calls) == 1
    assert saved['source_ids'] == ['source_a']
    assert saved['knowledge_snapshot'] == snapshot['knowledge_units']
    # Older saved records may contain the former inflated list; export derives
    # attribution from their immutable snapshot without mutating the record.
    saved['source_ids'] = ['source_a', 'source_b']
    markdown = export_markdown(saved)
    assert 'Sources: source_a\n' in markdown
    assert 'Consolidated evidence context (separate from citation attribution)' in markdown
    assert 'asset asset_b' in markdown
    assert saved['source_ids'] == ['source_a', 'source_b']


def test_answer_api_save_export_and_manual_revision_keep_snapshot_provenance(client, monkeypatch):
    snapshot = prepared([asset('asset_a', 'Storytelling psychology'),
                         asset('asset_b', 'Storytelling psychology', 'source_b')])
    fake_provider(monkeypatch, 'knowledge_answer')
    response = {'title': 'Synthetic finding', 'introduction': '', 'sections': [
        {'kind': 'source_principle', 'heading': 'Finding', 'content': 'Synthetic supported finding.',
         'evidence_refs': ['asset_b']}],
        'applied_knowledge': [{'asset_id': 'asset_a', 'usage_note': 'Canonical idea used.'}], 'design_choices': []}
    monkeypatch.setattr(ai_gateway, 'generate', lambda *_: SimpleNamespace(output_text=json.dumps(response), id='synthetic'))
    monkeypatch.setattr(workshop_generation, 'prepare_workshop', lambda *_: snapshot)
    request = payload(mode='knowledge_answer', source_ids=['source_a', 'source_b']).model_dump()
    request['save'] = True
    generated = client.post('/workshops/generate', json=request)
    assert generated.status_code == 200
    result = generated.json()
    assert result['evidence_coverage']['used_idea_count'] == 1
    assert result['evidence_coverage']['used_source_ids'] == ['source_b']
    saved = result['saved_output']
    assert saved['source_ids'] == ['source_b']
    assert client.get('/outputs/' + saved['id']).json()['knowledge_snapshot'] == snapshot['knowledge_units']
    exported = client.get('/outputs/' + saved['id'] + '/export')
    assert exported.status_code == 200
    assert 'Sources: source_b\n' in exported.text
    assert '## Cited evidence\n- Asset asset_b' in exported.text
    revised_answer = client.post('/outputs/' + saved['id'] + '/revise', json={
        'instruction': 'Clarify wording', 'content': 'A revised synthetic answer; attribution requires review.'})
    assert revised_answer.status_code == 200
    assert revised_answer.json()['source_ids'] == ['source_b']
    assert revised_answer.json()['generation_metadata']['citation_asset_ids'] == ['asset_b']
    assert revised_answer.json()['knowledge_snapshot'] == saved['knowledge_snapshot']
    # A separate ordinary artifact retains its immutable evidence across revisions.
    from app.services.outputs import save_output
    ordinary = {'title': 'Synthetic artifact', 'output_type': 'research_synthesis',
                'content': 'A synthetic research synthesis with limited evidence.',
                'applied_knowledge': [{'asset_id': 'asset_a', 'usage_note': 'Canonical idea used.'}],
                'design_choices': []}
    parent = save_output({'brief': snapshot['brief'], 'knowledge_snapshot': snapshot['knowledge_units'],
                          'output': ordinary, 'provider': 'manual'})
    revised = client.post('/outputs/' + parent['id'] + '/revise', json={
        'instruction': 'Clarify the wording', 'content': 'A revised synthetic research synthesis with limited evidence.'})
    assert revised.status_code == 200
    assert revised.json()['source_ids'] == ['source_a']
    assert revised.json()['knowledge_snapshot'] == parent['knowledge_snapshot']


def test_applied_idea_is_counted_even_when_sections_only_describe_open_questions(monkeypatch):
    snapshot = prepared([asset('asset_a', 'Storytelling psychology'), asset('asset_unused', 'Garden soil')])
    fake_provider(monkeypatch, 'knowledge_answer')
    response = {'title': 'Research remains incomplete', 'introduction': '', 'sections': [
        {'kind': 'open_question', 'heading': 'Research gap', 'content': 'Further research is needed.', 'evidence_refs': []}],
        'applied_knowledge': [{'asset_id': 'asset_a', 'usage_note': 'Used to identify the remaining research gap.'}],
        'design_choices': []}
    monkeypatch.setattr(ai_gateway, 'generate', lambda *_: SimpleNamespace(output_text=json.dumps(response), id='synthetic'))
    result = workshop_generation.generate_workshop_output(payload(mode='knowledge_answer'), prepared=snapshot)
    assert result['knowledge_unit_count'] == 2
    assert result['evidence_coverage']['used_idea_count'] == 1
    assert result['evidence_coverage']['used_source_count'] == 0
