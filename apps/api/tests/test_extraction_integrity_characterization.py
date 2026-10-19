"""Current validation behavior plus OFFLINE candidate-signal experiments.

These structural/manual baselines are separate from generated-only enforcement. All fixtures
are synthetic. No frozen/private asset is loaded and no provider is contacted.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from extraction_integrity_probe import measure_periodicity
from app.models.knowledge_extraction import KnowledgeExtractionResultSubmission
from app.services.gemini_knowledge_extraction import validate_extraction_result

FIXTURES = json.loads((Path(__file__).parent / 'fixtures/extraction_integrity_cases.json').read_text())['cases']


def case_text(case):
    if case['kind'] == 'phrase_loop':
        return ' '.join([case['unit']] * case['repeats'])
    if case['kind'] == 'literal_repeat':
        return case['unit'] * case['repeats']
    if case['kind'] == 'literal':
        return case['text']
    if case['kind'] == 'long_explanation':
        # Coherent long case commentary with meaningful repeated terminology,
        # distinct scenario details, headings, numbers and recurring structure.
        topics = ['arrival recording', 'tool inventory', 'handoff ownership',
                  'public status', 'private notes', 'capacity review']
        return '\n\n'.join(
            f'Case {i}: {topics[i % len(topics)]}. '
            f'The coordinator compared record {i} with a separate record {i+1}. '
            f'The distinction matters because the records name different actions, '
            f'and the person assigned to case {i} has confirmed only that case. '
            f'A later review must verify the remaining action independently; '
            f'repeating the same label does not transfer responsibility. '
            f'This example documents the comparison, preserves the uncertainty, '
            f'and leaves the unconfirmed task visible for its own review.'
            for i in range(case['paragraphs']))
    return '\n\n'.join(
        f'Review note. Entry {i} records an observation about item {i+1000}. '
        f'Status note. Task {i+2000} remains assigned to reviewer {i+3000}. '
        f'Next step. Compare the independent evidence for case {i+4000} '
        f'before making a conclusion about case {i+5000}.'
        for i in range(case['paragraphs']))


def synthetic_asset(text, **overrides):
    return {'asset_type':'warning', 'title':'Check the record before proceeding',
            'what_it_says':'Check the record before proceeding.',
            'source_id':'source_synthetic', 'chunk_id':'chunk_synthetic',
            'evidence':'Check the record before proceeding.', 'keywords':['record','check'],
            'confidence_score':4, 'why_it_matters':text, **overrides}


@pytest.mark.parametrize('case', FIXTURES, ids=lambda case:case['id'])
def test_current_structural_validation_accepts_these_strings(case):
    text = case_text(case)
    interaction = SimpleNamespace(output_text=json.dumps({'assets':[synthetic_asset(text)]}), id='synthetic')
    parsed, returned = validate_extraction_result(None,'synthetic-model',{},interaction)
    assert parsed.assets[0].why_it_matters == text
    assert returned is interaction


@pytest.mark.parametrize('case', FIXTURES, ids=lambda case:case['id'])
def test_candidate_periodicity_signal_is_not_production_enforcement(case):
    measured = measure_periodicity(case_text(case))
    assert measured['severe_repetition_signal'] is case['severe_signal']


def test_valid_long_explanation_exceeds_observed_failure_length_without_periodic_loop():
    case = next(c for c in FIXTURES if c['id']=='long_diverse_explanation')
    measured = measure_periodicity(case_text(case))
    assert measured['characters'] > 21365
    assert measured['exceptional_length_diagnostic']
    assert not measured['severe_repetition_signal']


def test_repetition_is_not_a_general_semantic_or_coherence_validator():
    fluent = next(c for c in FIXTURES if c['id']=='unsupported_but_fluent_claim')
    quote = next(c for c in FIXTURES if c['id']=='intentional_long_repeated_quote')
    symbols = next(c for c in FIXTURES if c['id']=='exceptional_symbol_blob')
    assert not measure_periodicity(case_text(fluent))['severe_repetition_signal']
    assert measure_periodicity(case_text(quote))['severe_repetition_signal']
    assert measure_periodicity(case_text(symbols))['exceptional_length_diagnostic']
    assert not measure_periodicity(case_text(symbols))['severe_repetition_signal']


def test_existing_subtype_validation_remains_strict():
    with pytest.raises(ValidationError):
        KnowledgeExtractionResultSubmission.model_validate({'assets':[
            synthetic_asset('A coherent explanation.', action='Not a warning field')
        ]})


def test_manual_import_remains_unchanged_and_supersedes_prior_assets(client, knowledge, source, asset):
    # Historical settlement baseline retained: manual imports are explicitly
    # outside the newly authorized generated-content gate.
    src, chunk = source
    case = next(c for c in FIXTURES if c['id']=='severe_phrase_loop')
    job = client.post('/knowledge-extractions', json={
        'source_id':src['id'],'chunk_id':chunk['id'],'reprocess':True}).json()['job']
    corrupt = {**asset,'title':'Synthetic degenerate explanation','why_it_matters':case_text(case)}
    response = client.post(f"/knowledge-extractions/{job['id']}/results",json={'assets':[asset,corrupt]})
    assert response.status_code == 200
    assert len(response.json()['assets']) == 2
    from app.db import mock_data
    previous = next(a for a in mock_data.knowledge_assets if a['id']==knowledge['id'])
    assert previous['active'] is False
    assert previous['superseded_by_job_id'] == job['id']
    assert all(a['active'] for a in response.json()['assets'])


def test_existing_schema_rejection_preserves_prior_active_set(client, knowledge, source, asset):
    src, chunk = source
    job = client.post('/knowledge-extractions', json={
        'source_id':src['id'],'chunk_id':chunk['id'],'reprocess':True}).json()['job']
    invalid = {**asset,'asset_type':'decision_rule'}  # no required action
    response = client.post(f"/knowledge-extractions/{job['id']}/results",json={'assets':[asset,invalid]})
    assert response.status_code == 422
    from app.db import mock_data
    assert [a['id'] for a in mock_data.knowledge_assets if a.get('active',True)] == [knowledge['id']]
    assert not any(a['extraction_job_id']==job['id'] for a in mock_data.knowledge_assets)
