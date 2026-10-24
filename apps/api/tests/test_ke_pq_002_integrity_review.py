"""Synthetic integrity regressions and explicitly labeled omission diagnostics.

These are not a reconstruction of the unavailable Measuring Narrative Engagement
capture, nor semantic completeness tests. All provider responses are fake.
"""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import TypeAdapter

from app.db import mock_data as db
from app.models.knowledge_asset import KnowledgeAsset
from app.models.workshop_generation import WorkshopGenerateRequest
from app.services import ai_gateway, knowledge_extraction as extraction, workshop, workshop_generation


def asset(aid='asset_a', sid='source_a', **changes):
    value = dict(id=aid, source_id=sid, chunk_id='chunk_' + aid,
                 asset_type='principle', title='Curiosity and narrative attention',
                 what_it_says='Curiosity invites further exploration.',
                 evidence='A synthetic passage about attention.', keywords=['curiosity'],
                 confidence_score=4)
    value.update(changes)
    return TypeAdapter(KnowledgeAsset).validate_python(value).model_dump(mode='json')


def install(items):
    db.libraries[:] = [{'id': 'library_a'}, {'id': 'library_b'}]
    db.sources[:] = [{'id': 'source_a', 'library_id': 'library_a',
                     'title': 'Measuring Narrative Engagement — synthetic test only'},
                    {'id': 'source_b', 'library_id': 'library_b', 'title': 'Unselected synthetic material'}]
    db.knowledge_assets[:] = deepcopy(items)


def request(**changes):
    return WorkshopGenerateRequest(situation='How do curiosity and trust help audiences?',
                                   goal='Understand curiosity and trust.', source_ids=['source_a'],
                                   output_type='knowledge_answer', save=False, **changes)


def prepared(items):
    groups = extraction.consolidate_knowledge_assets(items)
    return {'brief': request().model_dump(), 'knowledge_units': groups,
            'knowledge_unit_count': len(groups), 'synthesis_context': {}}


def fake_provider(monkeypatch):
    calls = []
    result = {'title': 'A narrower supported answer', 'introduction': '',
              'sections': [{'kind': 'source_principle', 'heading': 'Curiosity',
                            'content': 'Curiosity invites further exploration.', 'evidence_refs': ['asset_a']}],
              'applied_knowledge': [{'asset_id': 'asset_a', 'usage_note': 'Supports one dimension.'}],
              'design_choices': []}
    monkeypatch.setattr(ai_gateway, 'generate', lambda *args: (
        calls.append(args) or SimpleNamespace(output_text=json.dumps(result), id='fake')))
    return calls


def test_single_source_retrieval_rejects_a_backend_scope_violation(monkeypatch):
    items = [asset(), asset('asset_b', 'source_b')]
    install(items)
    monkeypatch.setattr(workshop, 'list_knowledge_assets', lambda **_: items)
    with pytest.raises(HTTPException) as error:
        workshop.prepare_workshop(request())
    assert error.value.status_code == 409


@pytest.mark.parametrize('location', ['canonical', 'trail', 'group', 'context', 'conflicting_member',
                                       'missing_member', 'foreign_member', 'conflicting_chunk'])
def test_prepared_source_contamination_fails_before_provider(monkeypatch, location):
    install([asset()])
    snapshot = prepared([asset()])
    group = snapshot['knowledge_units'][0]
    if location == 'canonical':
        group['canonical_asset']['source_id'] = 'source_b'
    elif location == 'trail':
        group['evidence_trail'][0]['source_id'] = 'source_b'
    elif location == 'group':
        group['source_ids'].append('source_b')
    elif location == 'context':
        snapshot['synthesis_context'] = {'agreements': [{'source_ids': ['source_b'], 'asset_ids': ['asset_a']}]}
    elif location == 'conflicting_member':
        group['evidence_trail'].append({**group['evidence_trail'][0], 'source_id': 'source_b'})
    elif location == 'missing_member':
        group['asset_ids'].append('unknown_member')
    elif location == 'foreign_member':
        group['evidence_trail'].append({**group['evidence_trail'][0], 'asset_id': 'unknown_member'})
    else:
        group['evidence_trail'][0]['chunk_id'] = 'unrelated_chunk'
    original = deepcopy(snapshot)
    calls = fake_provider(monkeypatch)
    with pytest.raises(HTTPException) as error:
        workshop_generation.generate_workshop_output(request(), prepared=snapshot)
    assert error.value.status_code == 409
    assert calls == [] and db.outputs == []
    assert snapshot == original


def test_explicit_selections_cannot_silently_fall_outside_preview_limit():
    items = [asset(), asset('asset_b', title='Trust in relationships',
                           what_it_says='Trust depends on consistency.', evidence='A separate synthetic trust finding.',
                           keywords=['trust'])]
    install(items)
    payload = request(asset_ids=['asset_a', 'asset_b'], limit=1)
    with pytest.raises(HTTPException) as error:
        workshop.prepare_workshop(payload)
    assert error.value.status_code == 409


def test_noncanonical_interpretation_reaches_context_without_relabeling_its_evidence():
    canonical = asset(confidence_score=5, what_it_says='A broad narrative observation.')
    member = asset('asset_b', what_it_says='Curiosity creates an information gap.',
                   when_not_to_use=['Do not generalize beyond this synthetic setting.'])
    groups = extraction.consolidate_knowledge_assets([canonical, member])
    assert len(groups) == 1
    unit = workshop_generation._compact_knowledge_unit(groups[0])
    trail = next(row for row in unit['evidence_trail'] if row['asset_id'] == 'asset_b')
    assert trail['interpretation']['what_it_says'] == member['what_it_says']
    assert trail['interpretation']['when_not_to_use'] == member['when_not_to_use']
    assert trail['evidence'] == member['evidence']


def test_available_dimension_can_be_omitted_after_its_evidence_reaches_provider(monkeypatch):
    """A remaining generation limitation, not an assertion of product acceptance."""
    items = [asset(), asset('asset_b', title='Trust in relationships',
                           what_it_says='Trust depends on consistency.', evidence='A separate synthetic trust finding.',
                           keywords=['trust'])]
    install(items)
    snapshot = prepared(items)
    calls = fake_provider(monkeypatch)
    result = workshop_generation.generate_workshop_output(request(), prepared=snapshot)
    supplied = {aid for unit in calls[0][1]['knowledge_units'] for aid in unit['asset_ids']}
    assert supplied == {'asset_a', 'asset_b'}
    assert result['evidence_coverage']['used_idea_count'] == 1
    assert 'Trust depends on consistency' not in result['output']['content']
    assert result['knowledge_snapshot'] == snapshot['knowledge_units']


@pytest.mark.parametrize('operation', ['list', 'search'])
def test_single_source_indexed_adapter_cannot_widen_scope(monkeypatch, operation):
    items = [asset(), asset('asset_b', 'source_b')]
    install(items)
    class WrongScopeAdapter:
        version = 3
        def active_assets(self, **kwargs):
            return items
        def search_candidates(self, *args, **kwargs):
            return items
    monkeypatch.setattr(extraction.authority, 'coordinator', lambda: WrongScopeAdapter())
    with pytest.raises(HTTPException) as error:
        if operation == 'list':
            extraction.list_knowledge_assets(source_id='source_a')
        else:
            extraction.search_knowledge_assets('curiosity', source_id='source_a')
    assert error.value.status_code == 409


def test_library_membership_change_invalidates_generation_without_refreshing_evidence(monkeypatch):
    from app.services.prepared_evidence import remember_preparation, resolve_preparation
    install([asset()])
    payload = request(library_id='library_a', interaction_revision=1)
    snapshot = prepared([asset()])
    preview = remember_preparation(payload, snapshot)
    db.sources[0]['library_id'] = 'library_b'
    with pytest.raises(HTTPException) as error:
        resolve_preparation(payload.model_copy(update={'prepared_snapshot_id': preview['prepared_snapshot_id']}))
    assert error.value.status_code == 409
    assert db.outputs == []


@pytest.mark.parametrize('boundary', ['retrieval', 'generation'])
def test_declared_source_cannot_borrow_another_sources_known_chunk(monkeypatch, boundary):
    item = asset(chunk_id='chunk_source_b_001')
    install([item])
    db.sources[0]['chunk_manifest'] = {'version': 1, 'total_parts': 1, 'chunk_ids': ['chunk_source_a_001']}
    calls = fake_provider(monkeypatch)
    with pytest.raises(HTTPException) as error:
        if boundary == 'retrieval':
            workshop.prepare_workshop(request())
        else:
            workshop_generation.generate_workshop_output(request(), prepared=prepared([item]))
    assert error.value.status_code == 409
    assert calls == []
