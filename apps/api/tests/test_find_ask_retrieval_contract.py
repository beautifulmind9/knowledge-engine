"""Synthetic Find/Ask regressions; preparation only, no provider or private data.

Known differences are explicitly characterized, not accepted as semantic recall.
The browser request assertions live in knowledge-browser.test.mjs.
"""
from copy import deepcopy

import pytest
from fastapi import HTTPException

from app.db import mock_data as db
from app.models.workshop import WorkshopPrepareRequest
from app.services import knowledge_extraction as retrieval, workshop
from app.services.retrieval_diagnostics import RetrievalDiagnostics
from test_relevance_evaluation import FIXTURE, asset, install, install_labeled


LIBRARIES = ['marketing', 'psychology', 'creators']
DIRECT = {'creator_study', 'narrative_measure'}
CREATOR_CASES = [case for case in FIXTURE['cases'] if case['id'].startswith('creator_')]
SEMANTIC_QUERY = 'How do stories and suspense help public figures form enduring bonds with their communities?'
LEGACY_UI_CONSTRAINTS = [
    'Use only the selected knowledge scope as the evidence base',
    'Distinguish source-grounded teaching from generator synthesis',
]


def ask_request(query, *, constraints=(), mode='knowledge_answer', source_ids=None):
    return WorkshopPrepareRequest(
        situation=query, goal=query, constraints=list(constraints), output_type=mode,
        source_ids=source_ids if source_ids is not None else [
            source['id'] for source in db.sources if source['library_id'] in LIBRARIES
        ], asset_ids=[], limit=8,
    )


def browser_find(query):
    # app.js: per-library limit 50, score/support ordering, canonical-ID dedup.
    batches = [retrieval.search_consolidated_knowledge_assets(
        query, library_id=library, limit=50) for library in LIBRARIES]
    ranked = [(group, scope, index) for scope, batch in enumerate(batches)
              for index, group in enumerate(batch)]
    ranked.sort(key=lambda row: (-row[0]['relevance_score'], -row[0]['support_count'], row[1], row[2]))
    result, seen = [], set()
    for group, _, _ in ranked:
        aid = group['canonical_asset']['id']
        if aid not in seen:
            seen.add(aid)
            result.append(group)
    return result[:50]


def members(groups):
    return {aid for group in groups for aid in group['asset_ids']}


def assert_citations(groups, original, allowed):
    for group in groups:
        assert set(group['source_ids']) <= allowed
        assert {row['asset_id'] for row in group['evidence_trail']} == set(group['asset_ids'])
        for row in group['evidence_trail']:
            before = original[row['asset_id']]
            assert (row['source_id'], row['chunk_id'], row['evidence']) == (
                before['source_id'], before['chunk_id'], before['evidence'])


@pytest.mark.parametrize('case', CREATOR_CASES, ids=lambda case: case['id'])
@pytest.mark.parametrize('constraints', [(), LEGACY_UI_CONSTRAINTS], ids=['question_only', 'legacy_browser'])
def test_browser_shapes_retain_direct_findings_and_exact_member_citations(case, constraints):
    install_labeled()
    before = deepcopy(db.knowledge_assets)
    original = {item['id']: item for item in before}
    payload = ask_request(case['query'], constraints=constraints)
    found = browser_find(case['query'])
    asked = workshop.prepare_workshop(payload)['knowledge_units']
    for groups in (found, asked):
        assert DIRECT <= members(groups[:2])
        assert 'narrative_measure_independent' in members(groups)
        assert 'outside_scope' not in members(groups)
        assert_citations(groups, original, set(payload.source_ids))
    assert db.knowledge_assets == before


def test_semantic_only_multi_source_question_remains_unresolved_in_both_paths():
    install_labeled()
    trace = RetrievalDiagnostics()
    asked = workshop.prepare_workshop(ask_request(SEMANTIC_QUERY), diagnostics=trace)
    assert browser_find(SEMANTIC_QUERY) == asked['knowledge_units'] == []
    direct = [row for row in trace.as_dict()['candidates'] if row['id'] in DIRECT]
    assert len(direct) == 2
    assert all(row['score'] == 0 and not row['matched_terms'] for row in direct)


@pytest.mark.parametrize('mode', ['knowledge_answer', 'research_synthesis', 'general'])
def test_generated_boilerplate_can_outrank_question_but_is_not_needed_for_retrieval(mode):
    install_labeled()
    # An explicitly synthetic adversarial control, not a reported production incident.
    distractor = asset('boilerplate_only', 'Knowledge scope evidence base grounded teaching generator synthesis',
                       'A documentation note about an unrelated generation interface.', sid='business')
    db.knowledge_assets.append(distractor)
    query = next(case['query'] for case in CREATOR_CASES if case['id'] == 'creator_vocabulary_boundary')
    legacy = workshop.prepare_workshop(ask_request(query, constraints=LEGACY_UI_CONSTRAINTS, mode=mode))
    clean = workshop.prepare_workshop(ask_request(query, mode=mode))
    assert legacy['knowledge_units'][0]['asset_ids'] == ['boilerplate_only']
    assert 'boilerplate_only' not in members(browser_find(query))
    assert 'boilerplate_only' not in members(clean['knowledge_units'])
    assert DIRECT <= members(clean['knowledge_units'][:2])


def test_user_authored_constraint_is_still_a_retrieval_signal():
    install_labeled()
    db.knowledge_assets.append(asset('consent', 'Consent safeguards',
                                    'Consent must be documented.', sid='business'))
    query = next(case['query'] for case in CREATOR_CASES if case['id'] == 'creator_vocabulary_boundary')
    prepared = workshop.prepare_workshop(ask_request(query, constraints=['Discuss consent safeguards.']))
    assert 'consent' in members(prepared['knowledge_units'])
    assert prepared['brief']['constraints'] == ['Discuss consent safeguards.']


def test_cross_library_duplicates_have_different_grouping_but_identical_evidence_members():
    install_labeled()
    next(source for source in db.sources if source['id'] == 'psychology_b')['library_id'] = 'marketing'
    query = next(case['query'] for case in CREATOR_CASES if case['id'] == 'creator_exact')
    expected = {'narrative_measure', 'narrative_measure_independent'}
    found = [group for group in browser_find(query) if expected & set(group['asset_ids'])]
    asked = [group for group in workshop.prepare_workshop(ask_request(query))['knowledge_units']
             if expected & set(group['asset_ids'])]
    assert len(found) == 2 and len(asked) == 1
    assert members(found) == members(asked) == expected
    original = {item['id']: item for item in db.knowledge_assets}
    for groups in (found, asked):
        assert_citations(groups, original, {'psychology', 'psychology_b'})


def test_single_source_ask_fallback_does_not_establish_semantic_recall():
    install_labeled()
    assert retrieval.search_consolidated_knowledge_assets(SEMANTIC_QUERY, source_id='creator_a') == []
    trace = RetrievalDiagnostics()
    prepared = workshop.prepare_workshop(ask_request(SEMANTIC_QUERY, source_ids=['creator_a']), diagnostics=trace)
    assert members(prepared['knowledge_units']) == {'creator_study'}
    assert prepared['retrieval_coverage']['lexically_matched_asset_count'] == 0
    assert prepared['retrieval_coverage']['candidate_without_word_matches_asset_count'] == 1
    row = next(row for row in trace.as_dict()['candidates'] if row['id'] == 'creator_study')
    assert any(part.get('bonus') == 'single_source_representative_fallback' for part in row['contributions'])


def test_large_snapshot_scope_find_matches_but_ask_rejects_instead_of_truncating():
    target = asset('target', 'Narrative evidence', 'Narrative measurement.', sid='creator_a')
    unrelated = asset('unrelated', 'Garden soil', 'Water the plants.', sid='creator_a')
    install([{**unrelated, 'id': f'other_{i}'} for i in range(1000)] + [target])
    assert members(retrieval.search_consolidated_knowledge_assets('narrative', source_id='creator_a')) == {'target'}
    with pytest.raises(HTTPException) as error:
        workshop.prepare_workshop(ask_request('narrative', source_ids=['creator_a']))
    assert error.value.status_code == 413
    assert 'No evidence was truncated' in error.value.detail


def test_empty_ui_constraints_keep_server_grounding_instructions_and_citation_allowlist(monkeypatch):
    from app.models.workshop_generation import WorkshopGenerateRequest
    from app.services import ai_gateway, workshop_generation

    install_labeled()
    payload = WorkshopGenerateRequest(**ask_request(CREATOR_CASES[0]['query']).model_dump(), save=False)
    before = deepcopy(db.knowledge_assets)
    captured = []

    class CapturedBeforeProvider(Exception):
        pass

    def capture(model, request, schema):
        captured.append((request, schema))
        raise CapturedBeforeProvider

    monkeypatch.setattr(ai_gateway, 'generate', capture)
    with pytest.raises(CapturedBeforeProvider):
        workshop_generation.generate_workshop_output(payload)
    assert len(captured) == 1
    request, schema = captured[0]
    assert 'Do not invent source claims' in request['instructions']
    assert 'Keep a strict distinction between source-grounded knowledge and your own design choices' in request['instructions']
    assert 'Keep each section\'s evidence_refs limited to supplied asset IDs' in request['instructions']
    assert 'outside_scope' not in str(schema)
    assert 'creator_study' in str(schema) and 'narrative_measure_independent' in str(schema)
    assert db.knowledge_assets == before
