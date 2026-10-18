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
    return WorkshopGenerateRequest(situation=text, goal=text, output_type=mode,
                                   source_ids=['source_a'], save=False, **kwargs)


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


def test_repetition_is_deduplicated_within_fields_but_reweighted_across_fields():
    item = asset('asset_a', 'Storytelling psychology')
    base = payload()
    repeated = payload('Storytelling psychology storytelling psychology')
    assert workshop._workshop_relevance(item, base) == workshop._workshop_relevance(item, repeated)
    constrained = payload(constraints=['Storytelling psychology'])
    assert workshop.build_workshop_query(base) == workshop.build_workshop_query(constrained)
    assert workshop._workshop_relevance(item, constrained)[0] > workshop._workshop_relevance(item, base)[0]
    duplicated = payload(constraints=['Storytelling psychology', 'Storytelling psychology'])
    assert workshop._workshop_relevance(item, duplicated)[0] > workshop._workshop_relevance(item, constrained)[0]


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
    assert ('evidence_coverage' in result) == (mode == 'knowledge_answer')
    assert ('reasoning_sections' in calls[0][2].get('properties', {})) is False
    assert ('sections' in calls[0][2].get('properties', {})) == (mode == 'knowledge_answer')


def test_single_source_answer_fallback_differs_from_research_synthesis(monkeypatch):
    pool(monkeypatch, [asset('asset_a', 'Garden soil')])
    assert workshop._retrieve_raw_assets(payload()) == []
    result = workshop._retrieve_raw_assets(payload(mode='knowledge_answer'))
    assert result[0]['relevance_score'] == 1
    assert result[0]['matched_terms'] == []


def test_normal_group_shape_overcredits_sources_and_undercounts_used_ideas(monkeypatch):
    items = [asset('asset_a', 'Storytelling psychology'),
             asset('asset_b', 'Storytelling psychology', 'source_b')]
    snapshot = prepared(items)
    assert len(snapshot['knowledge_units']) == 1
    calls = fake_provider(monkeypatch, 'knowledge_answer', ref='asset_a')
    result = workshop_generation.generate_workshop_output(payload(mode='knowledge_answer'), prepared=snapshot)
    coverage = result['evidence_coverage']
    assert len(calls) == 1
    assert result['output']['reasoning_sections'][0]['supporting_asset_ids'] == ['asset_a']
    # Normal prepare_workshop groups have canonical_asset.id, not asset_id.
    assert 'asset_id' not in snapshot['knowledge_units'][0]
    assert coverage['used_idea_count'] == 0
    assert coverage['used_source_count'] == 2
    assert coverage['used_source_ids'] == ['source_a', 'source_b']
    assert len(result['output']['applied_knowledge']) == 1
