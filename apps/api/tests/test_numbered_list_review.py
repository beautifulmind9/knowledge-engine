from copy import deepcopy
import json

import pytest
from pydantic import TypeAdapter, ValidationError

from app.models.knowledge_asset import KnowledgeAsset
from app.services.numbered_list_review import review_asset, review_chunk_pair
from app.services.generated_content_integrity import check_generated_assets, GeneratedContentIntegrityError


def candidate(**changes):
    value = dict(asset_type='framework', title='Five primary motivations',
                 what_it_says='Five primary motivations for sharing.', components=['a','b','c','d'],
                 source_id='s', chunk_id='c', evidence='1. a 2. b 3. c 4. d', keywords=['sharing'])
    value.update(changes)
    return TypeAdapter(KnowledgeAsset).validate_python(value)


def chunk(text, index=1, source='s'):
    return dict(id=f'c{index}', source_id=source, chunk_index=index, text=text)


def test_mismatch_is_advisory_without_mutation():
    asset = candidate()
    before = asset.model_dump()
    check_generated_assets([asset], dict(id='j', source_id='s', chunk_id='c'))
    assert asset.model_dump() == before


def test_complete_list_passes():
    assert review_asset(candidate(components=list('abcde'), evidence='1. a 2. b 3. c 4. d 5. e')) == []


def test_partial_interpretation_is_diagnostic_only():
    asset = candidate(title='Partial excerpt of five motivations', what_it_says='Incomplete subset.')
    assert [s['reason'] for s in review_asset(asset)] == ['partial_numbered_evidence']
    check_generated_assets([asset], dict(id='j', source_id='s', chunk_id='c'))


@pytest.mark.parametrize('title', ['2026 marketing report', 'Five experiments', 'Chapter 5', 'Five primary motivations'])
def test_title_alone_does_not_invent_list(title):
    # Use the concept subtype, which deliberately has no component field.
    value = candidate().model_dump()
    value.pop('components'); value.pop('steps'); value.pop('adaptation_notes')
    value.update(asset_type='concept', title=title, what_it_says='A general observation.', evidence='Value 1.5 rose in 2026.')
    assert review_asset(TypeAdapter(KnowledgeAsset).validate_python(value)) == []


@pytest.mark.parametrize('overlap', [False, True])
def test_adjacent_continuation_keeps_both_identities(overlap):
    current = chunk('Five primary motivations: 1. a 2. b 3. c 4. d and ...')
    following = chunk(('1. a 2. b 3. c 4. d ' if overlap else '') + '5. e', 2)
    original = deepcopy([current, following])
    signals = review_chunk_pair(current, following)
    assert signals[0]['reason'] == 'possible_adjacent_list_continuation'
    assert (signals[0]['chunk_id'], signals[0]['next_chunk_id']) == ('c1','c2')
    assert [current, following] == original


@pytest.mark.parametrize('following', [None, chunk('5. e',3), chunk('5. e',2,'foreign'), chunk('1. unrelated 2. list',2)])
def test_no_unsupported_adjacent_attribution(following):
    signals = review_chunk_pair(chunk('Five parts: 1. a 2. b 3. c 4. d'), following)
    assert signals[0]['reason'] == 'unfinished_numbered_list'
    assert 'next_chunk_id' not in signals[0]


@pytest.mark.parametrize('text', ['Five parts: 1. a 2. b 3. c 4. d 5. e',
                                    'Price 1.5 in 2026. Chapter 5.', '1. a 2. b',
                                    'Five parts. 1. a 2. b ' + 'prose ' * 81])
def test_boundary_false_positives(text):
    assert review_chunk_pair(chunk(text)) == []


def test_reviewed_proposal_preserves_strict_schema_and_provenance():
    # Entirely synthetic proposal: no private acceptance evidence is required.
    original = candidate(
        id='synthetic-asset', source_id='synthetic-source', chunk_id='synthetic-chunk',
        title='Five principles of a practice cycle', what_it_says='Five principles.',
        components=['observe', 'plan', 'practice', 'reflect'],
        chapter_or_section='Synthetic chapter',
        evidence='Unrelated example: 42 percent preferred blue.',
    ).model_dump()
    original.update(active=True, schema_version=1,
                    extraction_job_id='synthetic-job', extraction_version=1)
    proposed_field_changes = dict(
        title='Partial excerpt of five practice principles',
        what_it_says='This partial excerpt supplies four practice principles.',
        chapter_or_section='Synthetic chapter — practice cycle',
        evidence='Five principles: 1. observe 2. plan 3. practice 4. reflect and . . .',
        when_not_to_use=['Do not treat this excerpt as a complete cycle.'],
    )
    before = deepcopy(original)
    corrected = {**original, **proposed_field_changes}
    # Persistence metadata stays in the envelope, never added to model fields.
    fields = TypeAdapter(KnowledgeAsset).validate_python
    metadata = {'active','schema_version','extraction_job_id','extraction_version'}
    validated = fields({k:v for k,v in corrected.items() if k not in metadata})
    assert validated.chunk_id == original['chunk_id']
    assert validated.components == original['components'] and len(validated.components) == 4
    assert validated.source_id == original['source_id']
    assert validated.id == original['id']
    assert validated.evidence == proposed_field_changes['evidence']
    assert '42 percent' not in validated.evidence
    assert validated.evidence.endswith('and . . .')
    assert validated.chapter_or_section == proposed_field_changes['chapter_or_section']
    assert review_asset(validated)[0]['reason'] == 'partial_numbered_evidence'
    assert original == before
    assert all(corrected[k] == original[k] for k in metadata)
    check_generated_assets([validated], dict(id='j', source_id=validated.source_id, chunk_id=validated.chunk_id))
    with pytest.raises(ValidationError):
        fields({**validated.model_dump(), 'review_signal': True})


def test_numbered_advisory_precedes_ids_and_allows_whole_settlement(source, monkeypatch):
    from app.db import mock_data as db
    from app.services import knowledge_extraction as extraction
    src, part = source
    job = extraction.create_extraction_job(src['id'], part['id'])
    asset = candidate(source_id=src['id'], chunk_id=part['id'])
    events = []
    from app.services import generated_content_integrity as integrity
    monkeypatch.setattr(integrity, 'emit', lambda *a, **kw: events.append(kw))
    original_create_id = extraction.create_id
    def checked_create_id(*args):
        assert events and events[0]['result'] == 'diagnostic_only'
        return original_create_id(*args)
    monkeypatch.setattr(extraction, 'create_id', checked_create_id)
    valid = candidate(source_id=src['id'], chunk_id=part['id'],
                      components=list('abcde'), evidence='1. a 2. b 3. c 4. d 5. e')
    result = extraction.complete_extraction_job(job['id'], [asset, valid], generated_content=True)
    assert result['job']['status'] == 'completed'
    assert len(result['assets']) == 2
    assert len(db.knowledge_assets) == 2


def test_incidental_partial_word_does_not_bypass_complete_title():
    assert any(s['reason'] == 'declared_count_mismatch' for s in
               review_asset(candidate(what_it_says='Five motivations help explain incomplete data.')))


@pytest.mark.parametrize('word', ['partial', 'incomplete', 'excerpt', 'subset'])
def test_topic_words_do_not_exempt(word):
    asset = candidate(title=f'Five principles of {word} reinforcement', what_it_says='Five principles.')
    assert any(s['reason'] == 'declared_count_mismatch' for s in review_asset(asset))
    check_generated_assets([asset], dict(id='j', source_id='s', chunk_id='c'))


def test_steps_and_components_are_independent():
    assert review_asset(candidate(title='Five steps for success', what_it_says='Five steps.', steps=list('abcde'), components=list('ab'), evidence='Supporting prose.')) == []
    assert review_asset(candidate(title='Five steps with three components', what_it_says='A method.', steps=list('abc'), components=list('abc'), evidence='Prose.')) == [dict(reason='declared_count_mismatch', field='steps', declared_counts=[5], observed_count=3)]


def test_local_examples_do_not_inherit_reason_total():
    assert review_asset(candidate(title='Five reasons for success', what_it_says='Five reasons.', components=list('abcde'), evidence='Two examples: 1. a 2. b. These illustrate all five reasons.')) == []


def test_multiple_lists_keep_local_counts():
    signals = review_asset(candidate(components=list('abcde'), evidence='Two examples: 1. a 2. b. Five principles: 1. a 2. b 3. c 4. d'))
    assert signals == [dict(reason='incomplete_numbered_evidence', field='evidence', declared_counts=[5], observed_count=4)]


def test_ambiguous_run_is_advisory():
    asset = candidate(components=list('abcde'), evidence='Supporting observations: 1. a 2. b')
    assert review_asset(asset)[0]['reason'] == 'ambiguous_list_association'
    check_generated_assets([asset], dict(id='j', source_id='s', chunk_id='c'))


def test_chunk_local_declarations():
    assert review_chunk_pair(chunk('Five parts discussed. Two examples: 1. a 2. b')) == []
    signals = review_chunk_pair(chunk('Two examples: 1. a 2. b. Five parts: 1. a 2. b 3. c 4. d'), chunk('5. e',2))
    assert signals[0]['declared_counts'] == [5]
    assert signals[0]['reason'] == 'possible_adjacent_list_continuation'



def test_two_complete_lists_pass():
    assert review_asset(candidate(components=list('abcde'), evidence='Two examples: 1. a 2. b. Five principles: 1. a 2. b 3. c 4. d 5. e')) == []


def test_conflicting_same_field_claims_are_advisory(monkeypatch):
    from app.services import generated_content_integrity as integrity
    events = []
    monkeypatch.setattr(integrity, 'emit', lambda *a, **kw: events.append(kw))
    asset = candidate(title='Five principles with three reasons', what_it_says='Related lists.', evidence='Supporting prose.')
    check_generated_assets([asset], dict(id='j', source_id='s', chunk_id='c'))
    assert events[0]['result'] == 'diagnostic_only'
    assert events[0]['signals'][0]['reason'] == 'ambiguous_list_association'


@pytest.mark.parametrize('changes', [
    dict(title='Two reasons to use this framework', what_it_says='A framework.',
         components=list('abcde'), evidence='Private supporting quotation.'),
    dict(components=list('abcde'), evidence='Five motivations: 1. private a 2. private b'),
    dict(title='Partial list of five principles', what_it_says='These are all five principles.',
         evidence='Five principles: 1. private a 2. private b'),
    dict(title='Sharing motivations — partial interpretation from chunk 18',
         what_it_says='This partial excerpt supplies four motivations.',
         evidence='Five motivations: 1. private a 2. private b 3. private c 4. private d'),
])
def test_uncertain_completeness_never_rejects_or_logs_prose(changes, monkeypatch):
    from app.services import generated_content_integrity as integrity
    events = []
    monkeypatch.setattr(integrity, 'emit', lambda *a, **kw: events.append(kw))
    asset = candidate(**changes)
    before = asset.model_dump()
    check_generated_assets([asset], dict(id='j', source_id='s', chunk_id='c'))
    assert asset.model_dump() == before
    assert events and all(e['result'] == 'diagnostic_only' for e in events)
    for event in events:
        assert set(event) == {'result', 'detector', 'job_id', 'source_id', 'chunk_id', 'asset_index', 'signals'}
        for signal in event['signals']:
            assert set(signal) == {'reason', 'field', 'declared_counts', 'observed_count'}
    assert 'private' not in json.dumps(events).lower()


@pytest.mark.parametrize('changes', [
    dict(components=list('abcde'), evidence='Five motivations: 1. a 2. b. Separate examples: 3. x 4. y 5. z'),
    dict(components=list('abcde'), evidence='Five motivations: 1. a'),
])
def test_documented_lexical_blind_spots_are_not_completeness_proof(changes):
    # Current lexical limitations are explicit: no signal does not prove completeness.
    asset = candidate(**changes)
    assert review_asset(asset) == []
    check_generated_assets([asset], dict(id='j', source_id='s', chunk_id='c'))


def test_numbered_advisory_does_not_bypass_repetition_rejection(monkeypatch):
    from app.services import generated_content_integrity as integrity
    events = []
    monkeypatch.setattr(integrity, 'emit', lambda *a, **kw: events.append(kw))
    asset = candidate(why_it_matters='PRIVATE_LOOP ' * 256)
    with pytest.raises(GeneratedContentIntegrityError):
        check_generated_assets([asset], dict(id='j', source_id='s', chunk_id='c'))
    assert events[0]['result'] == 'diagnostic_only'
    assert events[-1]['detector'] == 'adjacent-word-periodicity-v1'
    assert events[-1]['result'] == 'review_required'
    assert 'PRIVATE_LOOP' not in json.dumps(events)


def test_empty_framework_components_are_rejected_by_strict_schema():
    with pytest.raises(ValidationError):
        candidate(components=[], evidence='Prose.')
