"""Labeled synthetic acceptance for lexical retrieval, never semantic sufficiency."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from app.db import mock_data as db
from app.models.knowledge_asset import KnowledgeAsset
from app.models.workshop import WorkshopPrepareRequest
from app.services import knowledge_extraction as retrieval, workshop
from app.services.retrieval_diagnostics import RetrievalDiagnostics


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/relevance/research_cases.json').read_text())
LEXICAL_CASES = [case for case in FIXTURE['cases'] if case.get('expectation') != 'unresolved_semantic_vocabulary']
CREATOR_CASES = [case for case in LEXICAL_CASES if case['id'].startswith('creator_')]


def asset(aid, title, text, sid='source_a', evidence=None, keywords=('synthetic',)):
    return TypeAdapter(KnowledgeAsset).validate_python({
        'id': aid, 'asset_type': 'principle', 'source_id': sid, 'chunk_id': 'chunk_' + aid,
        'title': title, 'what_it_says': text, 'evidence': evidence or text,
        'keywords': list(keywords), 'confidence_score': 4,
    }).model_dump(mode='json')


def install(assets, sources=None):
    db.knowledge_assets[:] = deepcopy(assets)
    db.sources[:] = deepcopy(sources or [{'id': sid, 'title': sid, 'library_id': 'selected'}
                                       for sid in sorted({item['source_id'] for item in assets})])
    db.libraries[:] = [{'id': lid, 'name': lid} for lid in {s['library_id'] for s in db.sources} | {'excluded_empty'}]


def install_labeled():
    install([TypeAdapter(KnowledgeAsset).validate_python(row['asset']).model_dump(mode='json')
             for row in FIXTURE['assets']], FIXTURE['sources'])


def find(case):
    scopes = ([{'source_id': sid} for sid in case['source_ids']] if 'source_ids' in case else
              [{'library_id': lid} for lid in case['library_ids']])
    groups = [group for scope in scopes for group in retrieval.search_consolidated_knowledge_assets(
        case['query'], limit=case['limit'], **scope)]
    return sorted(groups, key=lambda group: group['relevance_score'], reverse=True)[:case['limit']]


def request(case, mode='research_synthesis'):
    selected = case.get('source_ids', [source['id'] for source in FIXTURE['sources'] if source['library_id'] in case['library_ids']])
    return WorkshopPrepareRequest(situation=case['query'], goal=case['query'], output_type=mode,
                                  source_ids=selected, limit=case['limit'],
                                  library_id=case['library_ids'][0] if not selected else None)


@pytest.mark.parametrize('case', LEXICAL_CASES, ids=lambda case: case['id'])
def test_labeled_find_retains_direct_evidence_before_incidental_overlap(case):
    install_labeled()
    groups = find(case)
    members = {aid for group in groups for aid in group['asset_ids']}
    assert set(case['direct_ids']) <= members
    allowed = set(request(case).source_ids)
    assert {sid for group in groups for sid in group['source_ids']} <= allowed
    direct_positions = [index for index, group in enumerate(groups) if set(group['asset_ids']) & set(case['direct_ids'])]
    incidental_positions = [index for index, group in enumerate(groups) if set(group['asset_ids']) & set(case['incidental_ids'])]
    if incidental_positions and direct_positions:
        assert max(direct_positions) < min(incidental_positions)


@pytest.mark.parametrize('case', CREATOR_CASES, ids=lambda case: case['id'])
@pytest.mark.parametrize('mode', ['knowledge_answer', 'research_synthesis'])
def test_ask_and_create_retain_labeled_direct_evidence_in_exact_scope(case, mode):
    install_labeled()
    payload = request(case, mode)
    result = workshop.prepare_workshop(payload)
    groups = result['knowledge_units']
    assert set(case['direct_ids']) <= {aid for group in groups for aid in group['asset_ids']}
    assert {sid for group in groups for sid in group['source_ids']} <= set(payload.source_ids)
    assert set(case['direct_ids']) <= {aid for group in groups[:2] for aid in group['asset_ids']}
    assert 'outside_scope' not in {aid for group in groups for aid in group['asset_ids']}


def test_equivalent_lexical_questions_keep_strongest_two_and_independent_material_identity():
    install_labeled()
    strongest = []
    for case in CREATOR_CASES:
        groups = find(case)
        strongest.append([group['canonical_asset']['id'] for group in groups[:2]])
        measurement = next(group for group in groups if 'narrative_measure' in group['asset_ids'])
        assert set(measurement['asset_ids']) == {'narrative_measure', 'narrative_measure_independent'}
        assert {row['source_id'] for row in measurement['evidence_trail']} == {'psychology', 'psychology_b'}
    assert all(value == strongest[0] for value in strongest)


def test_vocabulary_paraphrase_gets_only_bounded_inflection_help():
    # Plural inflections are a lexical normalization, not semantic interpretation.
    install_labeled()
    case = next(case for case in FIXTURE['cases'] if case.get('expectation') == 'unresolved_semantic_vocabulary')
    assert case['direct_ids']
    trace = RetrievalDiagnostics()
    result = workshop.prepare_workshop(request(case), diagnostics=trace)
    assert set(case['direct_ids']) <= {aid for group in result['knowledge_units'] for aid in group['asset_ids']}
    candidates = {row['id']: row for row in trace.as_dict()['candidates']}
    assert candidates['creator_study']['matched_terms'] == ['narratives', 'personalities']
    assert {row['matched_variant'] for row in candidates['creator_study']['contributions']} == {
        'narrative', 'personality',
    }
    assert trace.as_dict()['requests'][0]['pipeline'] == 'workshop'


def test_semantic_only_paraphrase_remains_outside_lexical_claims():
    install_labeled()
    query = 'How do stories and suspense help public figures form enduring bonds with their communities?'
    groups = [group for library_id in ('marketing', 'psychology', 'creators')
              for group in retrieval.search_consolidated_knowledge_assets(query, library_id=library_id, limit=5)]
    members = {aid for group in groups for aid in group['asset_ids']}
    assert not (members & {'creator_study', 'narrative_measure'})


def test_find_diagnostics_record_resolved_scope_and_inflection_contribution():
    install_labeled()
    trace = RetrievalDiagnostics()
    groups = retrieval.search_consolidated_knowledge_assets(
        'narratives personalities', library_id='marketing', limit=5, diagnostics=trace)
    assert 'creator_study' in {aid for group in groups for aid in group['asset_ids']}
    capture = trace.as_dict()
    assert capture['requests'][0]['scope']['source_ids'] == ['business', 'creator_a', 'empty', 'preparing']
    candidate = next(row for row in capture['candidates'] if row['id'] == 'creator_study')
    assert candidate['matched_terms'] == ['narratives', 'personalities']
    assert {row['matched_variant'] for row in candidate['contributions']} == {'narrative', 'personality'}
    assert capture['final_selection'][0]['canonical_asset_id'] == 'creator_study'


def test_indexed_acquisition_receives_bounded_inflection_variants(monkeypatch):
    install_labeled()
    creator = next(item for item in db.knowledge_assets if item['id'] == 'creator_study')
    calls = []

    class Adapter:
        version = 3

        def search_candidates(self, tokens, normalized_query, **scope):
            calls.append((tokens, normalized_query, scope))
            return [creator] if {'narrative', 'personality'} <= set(tokens) else []

    monkeypatch.setattr(retrieval.authority, 'coordinator', lambda: Adapter())
    groups = retrieval.search_consolidated_knowledge_assets(
        'narratives personalities', library_id='marketing', limit=5)
    assert [group['canonical_asset']['id'] for group in groups] == ['creator_study']
    assert calls[0][0] == ['narrative', 'narratives', 'personalities', 'personality']
    assert calls[0][2]['source_ids'] == ['business', 'creator_a', 'empty', 'preparing']


def test_repeating_constraints_or_duplicate_request_words_cannot_manufacture_relevance():
    item = asset('one', 'Audience positioning', 'Customer choice depends on audience positioning.')
    def payload(constraints):
        return WorkshopPrepareRequest(situation='Audience positioning', goal='Customer choice', constraints=constraints)
    single = workshop._workshop_relevance(item, payload(['Audience positioning']))
    repeated = workshop._workshop_relevance(item, payload(['Audience positioning'] * 4))
    assert single == repeated
    assert workshop.build_workshop_query(payload(['Audience positioning'])) == workshop.build_workshop_query(payload(['Audience positioning'] * 4))
    install([item])
    assert retrieval.search_knowledge_assets('audience audience positioning')[0]['matched_terms'] == ['audience', 'positioning']


def test_duplicate_flood_keeps_distinct_findings_and_all_member_evidence_before_limit():
    copies = [asset('copy_' + str(index), 'Audience positioning customer choice',
                    'Audience positioning informs customer choice.') for index in range(45)]
    independent = asset('independent', 'Audience positioning customer choice',
                        'Audience positioning informs customer choice.', 'source_b')
    distinct = asset('distinct', 'Customer choice context',
                     'Availability and eligibility conditions limit a customer choice.', evidence='A separate contextual qualification.')
    install(copies + [independent, distinct])
    trace = RetrievalDiagnostics()
    groups = retrieval.search_consolidated_knowledge_assets('audience positioning customer choice', limit=2, diagnostics=trace)
    assert len(groups) == 2
    duplicate = next(group for group in groups if 'independent' in group['asset_ids'])
    assert len(duplicate['asset_ids']) == len(duplicate['evidence_trail']) == 46
    assert set(duplicate['source_ids']) == {'source_a', 'source_b'}
    assert any(group['asset_ids'] == ['distinct'] for group in groups)
    payload = WorkshopPrepareRequest(situation='Audience positioning customer choice', goal='Compare customer choice',
                                      source_ids=['source_a', 'source_b'], output_type='knowledge_answer', limit=2)
    prepared = workshop.prepare_workshop(payload)
    assert {aid for group in prepared['knowledge_units'] for aid in group['asset_ids']} == {item['id'] for item in copies + [independent, distinct]}
    assert all(row['retained_within_limit'] for row in trace.as_dict()['candidates'])


def test_lexically_uncertain_near_duplicates_remain_visible_with_provenance():
    # A method/methodology synonym is an unresolved grouping case, not a
    # validated reason to suppress a finding or lower the similarity threshold.
    first = asset('method_a', 'Caption and interview analysis method', 'Combine caption observations and interview testimony to examine creator motives.')
    near = asset('method_b', 'Caption and interview analysis methodology', 'Combine interview testimony and caption observations to examine creator motives.', 'source_b')
    distinct = asset('method_c', 'Interview consent limitations', 'Interview participation requires consent and withdrawal procedures.', 'source_b')
    groups = retrieval.consolidate_knowledge_assets([first, near, distinct])
    assert len(groups) == 3
    assert {aid for group in groups for aid in group['asset_ids']} == {'method_a', 'method_b', 'method_c'}
    assert any(group['asset_ids'] == ['method_c'] for group in groups)
    trail = [row for group in groups for row in group['evidence_trail']]
    assert {row['asset_id']: row['source_id'] for row in trail} == {
        'method_a': 'source_a', 'method_b': 'source_b', 'method_c': 'source_b'}


def test_conservative_near_duplicate_group_keeps_distinct_member_evidence():
    first = asset('method_a', 'Caption and interview analysis method',
                  'Combine caption observations and interview testimony to examine creator motives.')
    near = asset('method_b', 'Interview and caption analysis method',
                 'Combine interview testimony and caption observations to examine creator motives.', 'source_b')
    distinct = asset('method_c', 'Interview consent limitations',
                     'Interview participation requires consent and withdrawal procedures.', 'source_b')
    groups = retrieval.consolidate_knowledge_assets([first, near, distinct])
    assert len(groups) == 2
    combined = next(group for group in groups if set(group['asset_ids']) == {'method_a', 'method_b'})
    assert any(group['asset_ids'] == ['method_c'] for group in groups)
    assert {row['asset_id']: (row['source_id'], row['evidence']) for row in combined['evidence_trail']} == {
        item['id']: (item['source_id'], item['evidence']) for item in (first, near)}


def test_many_repeated_generic_words_cannot_displace_broader_source_evidence():
    install_labeled()
    direct = next(item for item in db.knowledge_assets if item['id'] == 'renal_direct')
    generic = next(item for item in db.knowledge_assets if item['id'] == 'renal_generic')
    install([direct] + [{**generic, 'id': 'generic_' + str(index)} for index in range(80)])
    query = next(case['query'] for case in FIXTURE['cases'] if case['id'] == 'medical_transfer')
    assert retrieval.search_consolidated_knowledge_assets(query, limit=1)[0]['asset_ids'] == ['renal_direct']
    prepared = workshop.prepare_workshop(WorkshopPrepareRequest(situation=query, goal=query,
                                         source_ids=['medicine', 'wellness'], output_type='knowledge_answer', limit=1))
    assert prepared['knowledge_units'][0]['asset_ids'] == ['renal_direct']


def test_local_listing_and_selected_assets_never_import_other_materials():
    chosen = asset('chosen', 'Audience positioning', 'Audience positioning matters.', 'chosen_source')
    outside = asset('outside', 'Audience positioning', 'Audience positioning matters.', 'outside_source')
    inactive = {**chosen, 'id': 'inactive', 'active': False}
    install([chosen, outside, inactive], [{'id':'chosen_source','title':'Chosen','library_id':'selected'},
                                        {'id':'outside_source','title':'Outside','library_id':'outside'}])
    assert [item['id'] for item in retrieval.list_knowledge_assets(source_ids=['chosen_source'])] == ['chosen']
    assert retrieval.list_knowledge_assets(source_ids=[]) == []
    payload = WorkshopPrepareRequest(situation='Audience positioning', goal='Audience positioning',
                                      source_ids=['chosen_source'], asset_ids=['chosen'], limit=1)
    result = workshop.prepare_workshop(payload)
    assert result['knowledge_units'][0]['asset_ids'] == ['chosen']
    assert result['knowledge_units'][0]['source_ids'] == ['chosen_source']
    with pytest.raises(ValueError, match='current source scope'):
        workshop.prepare_workshop(payload.model_copy(update={'asset_ids':['outside']}))
    with pytest.raises(ValueError, match='do not belong'):
        workshop.prepare_workshop(payload.model_copy(update={'library_id':'outside'}))


def test_empty_library_diagnostics_records_scope_without_importing_global_candidates():
    install([asset('outside', 'Audience positioning', 'Audience positioning matters.')])
    trace = RetrievalDiagnostics()
    result = workshop.prepare_workshop(WorkshopPrepareRequest(situation='Audience positioning', goal='Compare evidence',
                                        library_id='excluded_empty'), diagnostics=trace)
    assert result['knowledge_units'] == result['source_coverage'] == []
    assert result['evidence_base']['selected_count'] == 0
    capture = trace.as_dict()
    assert capture['result_limit'] == 8
    assert capture['requests'][0]['scope'] == {'source_ids': [], 'library_id': 'excluded_empty'}
    assert capture['candidates'] == []


def test_partial_preparation_and_prepared_zero_matches_remain_distinguishable(client, knowledge):
    from app.services.text_chunking import load_chunks, save_chunks
    from app.services.chunk_manifest import manifest_from_chunks
    source = next(source for source in db.sources if source['id'] == knowledge['source_id'])
    chunks = load_chunks(source['chunks_path'])
    chunks.append({**chunks[0], 'id':f"chunk_{source['id']}_002",'chunk_index':2})
    source['chunks_path'] = save_chunks(source['id'], chunks)
    source['chunk_manifest'] = manifest_from_chunks(source['id'], chunks)
    second = client.post('/sources', json={'library_id':source['library_id'],'title':'Prepared unrelated material'}).json()
    content = '# Gardens\nWater soil after planting.'
    assert client.post(f"/sources/{second['id']}/upload", files={'file':('garden.md',content,'text/markdown')}).status_code == 200
    assert client.post(f"/sources/{second['id']}/process").status_code == 200
    chunk = client.get(f"/sources/{second['id']}/chunks").json()['items'][0]
    job = client.post('/knowledge-extractions',json={'source_id':second['id'],'chunk_id':chunk['id']}).json()['job']
    assert client.post(f"/knowledge-extractions/{job['id']}/results",json={'assets':[]}).status_code == 200
    payload = WorkshopPrepareRequest(situation='Practice breaks learning',goal='Practice breaks learning',
                                      source_ids=[source['id'],second['id']], output_type='research_synthesis')
    trace = RetrievalDiagnostics()
    result = workshop.prepare_workshop(payload, diagnostics=trace)
    rows = {row['source_id']:row for row in result['source_coverage']}
    assert rows[source['id']]['prepared_sections'] == 1 and rows[source['id']]['total_sections'] == 2
    assert rows[second['id']]['prepared_sections'] == rows[second['id']]['total_sections'] == 1
    assert rows[second['id']]['relevant_idea_count'] == 0
    prep = {row['source_id']:row for row in trace.as_dict()['preparation']}
    assert prep[source['id']]['readiness'] == 'partly_ready'
    assert prep[second['id']]['readiness'] == 'ready'
    assert prep[second['id']]['positive_match_count'] == prep[second['id']]['retained_group_count'] == 0
