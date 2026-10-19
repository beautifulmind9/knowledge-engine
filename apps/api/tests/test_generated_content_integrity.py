"""Synthetic offline enforcement tests; SDK replacement never accesses Gemini."""
import copy
import json
from types import SimpleNamespace

import pytest

from app.db import mock_data as db
from app.models.knowledge_extraction import KnowledgeExtractionResultSubmission
from app.services.generated_content_integrity import (
    check_generated_assets, GeneratedContentIntegrityError, measure_periodicity,
)
from app.services.gemini_knowledge_extraction import run_gemini_knowledge_extraction
from app.services.knowledge_extraction import create_extraction_job, complete_extraction_job
from test_ai_gateway_503_retry import install_provider
from test_extraction_integrity_characterization import FIXTURES, case_text


@pytest.mark.parametrize('case', FIXTURES, ids=lambda c:c['id'])
def test_generated_prose_fixture_policy(case, asset):
    parsed = KnowledgeExtractionResultSubmission(assets=[{**asset, 'why_it_matters':case_text(case)}])
    job = {'id':'job_synthetic', 'source_id':asset['source_id'], 'chunk_id':asset['chunk_id']}
    if case['severe_signal']:
        with pytest.raises(GeneratedContentIntegrityError):
            check_generated_assets(parsed.assets, job)
    else:
        check_generated_assets(parsed.assets, job)
    assert parsed.assets[0].why_it_matters == case_text(case)


def test_exact_fifteen_word_loop_and_thresholds():
    phrase = ' '.join(f'token{i}' for i in range(15))
    measured = measure_periodicity(' '.join([phrase]*144))
    assert measured['period_words'] == 15
    assert measured['complete_cycles'] == 144
    assert measured['adjacent_periodic_words'] == 2160
    assert measured['severe_repetition_signal']
    assert not measure_periodicity('pending '*159)['severe_repetition_signal']
    assert measure_periodicity('pending '*160)['severe_repetition_signal']
    assert not measure_periodicity(' '.join(f't{i}' for i in range(32))*1)['severe_repetition_signal']
    assert not measure_periodicity(' '.join([phrase]*8))['severe_repetition_signal']
    assert not measure_periodicity('pending '*160 + ' '.join(f'x{i}' for i in range(200)))['severe_repetition_signal']


@pytest.mark.parametrize('field', ['evidence', 'chapter_or_section'])
def test_source_text_fields_are_exempt(field, asset):
    text = 'source quotation '*200
    parsed = KnowledgeExtractionResultSubmission(assets=[{**asset, field:text}])
    check_generated_assets(parsed.assets, {'id':'job', 'source_id':'source', 'chunk_id':'chunk'})
    assert getattr(parsed.assets[0],field) == text


@pytest.mark.parametrize('field', ['what_it_says','why_it_matters','how_to_apply'])
def test_prose_and_list_fields_have_no_quotation_bypass(field, asset):
    text = '"' + 'synthetic phrase '*200 + '"'
    parsed = KnowledgeExtractionResultSubmission(assets=[{**asset,field:[text] if field=='how_to_apply' else text}])
    with pytest.raises(GeneratedContentIntegrityError):
        check_generated_assets(parsed.assets, {'id':'job','source_id':'source','chunk_id':'chunk'})


@pytest.mark.parametrize('mode', ['single','coalesced','batch'])
def test_generated_rejection_atomic_safe_counted_no_retry(mode, client, knowledge, source, asset, monkeypatch, caplog):
    from app.services.batch_knowledge_extraction import run_gemini_knowledge_extraction_batch
    from app.services.ai_gateway import status
    from app.services.knowledge_extraction import persist_state
    from app.db.persistence import load_state
    src, chunk = source
    job = create_extraction_job(src['id'],chunk['id'],reprocess=True)
    old = copy.deepcopy(db.knowledge_assets)
    secret_text = 'PRIVATE_REJECTED_CONTENT '*256
    candidates = [asset,{**asset,'why_it_matters':secret_text}]
    response = {'assets':candidates}
    if mode=='batch': response={'results':[{'chunk_id':chunk['id'],'assets':candidates}]}
    calls = install_provider(monkeypatch,[SimpleNamespace(output_text=json.dumps(response),id='synthetic-response')])
    caplog.set_level('INFO',logger='uvicorn.error')
    # Gate must run before even allocating an ID or entering authority settlement.
    monkeypatch.setattr('app.services.knowledge_extraction.create_id',lambda *a:pytest.fail('allocated candidate ID'))
    if mode=='batch':
        result=run_gemini_knowledge_extraction_batch([job['id']])
        assert not result['results'] and len(result['failures'])==1
    else:
        with pytest.raises(GeneratedContentIntegrityError):
            run_gemini_knowledge_extraction(job['id'],coalesce_interpretation=mode=='coalesced')
    assert job['status']=='failed'
    assert db.knowledge_assets==old
    assert len(calls)==status()['calls_today']==1
    assert 'review required' in job['error']
    assert 'PRIVATE_REJECTED_CONTENT' not in job['error']+caplog.text
    diagnostic=json.loads(job['error'].split('Diagnostics: ',1)[1])
    assert diagnostic['field_path']=='assets[1].why_it_matters'
    assert diagnostic['job_id']==job['id']
    assert diagnostic['source_id']==src['id'] and diagnostic['chunk_id']==chunk['id']
    assert diagnostic['detector']=='adjacent-word-periodicity-v1'
    # Explicit checkpoint simulates coalesced caller persistence; historical
    # accepted records remain byte-for-byte readable without revalidation.
    persist_state()
    restored=load_state()
    assert restored['knowledge_assets']==old


def test_valid_empty_generated_settlement(source):
    src,chunk=source
    job=create_extraction_job(src['id'],chunk['id'])
    result=complete_extraction_job(job['id'],[],generated_content=True)
    assert result['job']['status']=='completed' and result['assets']==[]


def test_source_dispatch_stops_after_integrity_failure(client, source, asset, monkeypatch):
    from app.services.text_chunking import save_chunks
    src, chunk=source
    chunks=[chunk,{**chunk,'id':'chunk_synthetic_sibling'}]
    db.sources[0]['chunks_path']=save_chunks(src['id'],chunks)
    db.sources[0].pop('chunk_manifest',None)
    calls=install_provider(monkeypatch,[SimpleNamespace(output_text=json.dumps({
        'assets':[{**asset,'why_it_matters':'loop '*256}]}),id='synthetic')])
    response=client.post(f"/sources/{src['id']}/interpret?max_chunks=2")
    assert response.status_code==200,response.text
    assert response.json()['interruption_category']=='validation_failed'
    assert len(calls)==1
    assert not db.knowledge_assets
    assert not any(j['chunk_id']=='chunk_synthetic_sibling' and j['status']=='completed' for j in db.extraction_jobs)


def test_legitimate_quotation_is_not_a_rejection_reason(asset):
    text='The coordinator wrote, "Check the record before proceeding." This quotation explains the procedure.'
    parsed=KnowledgeExtractionResultSubmission(assets=[{**asset,'why_it_matters':text}])
    check_generated_assets(parsed.assets,{'id':'job','source_id':'source','chunk_id':'chunk'})
    assert parsed.assets[0].why_it_matters==text


def test_all_repetition_conditions_and_period_range():
    # Each failing case meets the other three policy conditions.
    assert not measure_periodicity('loop '*100+' '.join(f'u{i}' for i in range(60)))['severe_repetition_signal']
    unit=' '.join(f'u{i}' for i in range(31))
    assert not measure_periodicity(' '.join([unit]*7))['severe_repetition_signal']
    assert measure_periodicity('loop '*180+' '.join(f'u{i}' for i in range(120)))['severe_repetition_signal']
    unit=' '.join(f'u{i}' for i in range(32))
    assert measure_periodicity(' '.join([unit]*8))['severe_repetition_signal']


def test_gate_precedes_coordinator_settlement(source,asset,monkeypatch):
    from app.services import partition_authority as authority
    src,chunk=source
    job=create_extraction_job(src['id'],chunk['id'])
    parsed=KnowledgeExtractionResultSubmission(assets=[{**asset,'why_it_matters':'loop '*256}])
    monkeypatch.setattr('app.services.knowledge_extraction.get_extraction_job',lambda _:job)
    monkeypatch.setattr('app.services.knowledge_extraction.get_extraction_chunk',lambda *a,**k:chunk)
    monkeypatch.setattr(authority,'coordinator',lambda:object())
    monkeypatch.setattr(authority,'complete',lambda *a:pytest.fail('entered settlement transaction'))
    with pytest.raises(GeneratedContentIntegrityError):
        complete_extraction_job(job['id'],parsed.assets,generated_content=True)
    assert not db.knowledge_assets


def test_historical_corrupted_manual_snapshot_remains_readable(source,asset):
    from app.db.persistence import load_state
    src,chunk=source
    historical_text='historical repetition '*256
    parsed=KnowledgeExtractionResultSubmission(assets=[{**asset,'why_it_matters':historical_text}])
    job=create_extraction_job(src['id'],chunk['id'])
    complete_extraction_job(job['id'],parsed.assets)  # Manual import remains unchanged.
    historical=copy.deepcopy(db.knowledge_assets)
    assert load_state()['knowledge_assets']==historical
    replacement=create_extraction_job(src['id'],chunk['id'],reprocess=True)
    with pytest.raises(GeneratedContentIntegrityError):
        complete_extraction_job(replacement['id'],parsed.assets,generated_content=True)
    assert db.knowledge_assets==historical
    assert load_state()['knowledge_assets'][0]['why_it_matters']==historical_text
