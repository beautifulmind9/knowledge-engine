from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from app.db import mock_data as db
from app.services import source_summary, source_interpretation, gemini_knowledge_extraction
from app.services.knowledge_extraction import recover_job, persist_state
from app.services.text_chunking import save_chunks


def summary(client, sid):
    r = client.get(f'/sources/{sid}/summary')
    assert r.status_code == 200, r.text
    return r.json()


def install_parts(source, count=3):
    s, _ = source
    record = db.sources[0]
    record['chunks_path'] = save_chunks(s['id'], [{'id': f'p{i}', 'text': 'Grounded practice.', 'source_id': s['id']} for i in range(count)])
    return record


def job(s, part, status, **extra):
    item = dict(id=f'j{len(db.extraction_jobs)}', source_id=s['id'], chunk_id=part, status=status, created_at=datetime.now(timezone.utc).isoformat(), **extra)
    db.extraction_jobs.append(item)
    return item


def test_added_unattached_and_uploaded(client):
    lib = client.post('/libraries', json={'name':'Research'}).json()
    s = client.post('/sources', json={'library_id':lib['id'], 'title':'Notes'}).json()
    facts = summary(client, s['id'])
    assert (facts['readiness'], facts['file_state'], facts['next_action']) == ('added','unattached','attach_file')
    assert facts['total_parts']==0 and facts['completed_parts']==0 and facts['attention_category']=='missing_file'
    client.post(f"/sources/{s['id']}/upload", files={'file':('notes.txt',b'Practice')})
    facts = summary(client, s['id'])
    assert facts['readiness']=='added' and facts['next_action']=='read_source'
    assert facts['operation']=='idle' and facts['attention_category'] is None


def test_readiness_counts_are_independent_from_ideas_and_old_status(client, source):
    s=install_parts(source)
    s['processing_status']='knowledge_interpreted'  # stale field is not authoritative
    assert summary(client,s['id'])['readiness']=='ready_to_build'
    job(s,'p0','completed')
    facts=summary(client,s['id'])
    assert facts['readiness']=='partly_ready' and facts['completed_parts']==1
    assert not facts['has_usable_knowledge'] and facts['coverage_text']=='1 of 3 parts ready'
    job(s,'p1','completed');job(s,'p2','completed');job(s,'obsolete','completed')
    facts=summary(client,s['id'])
    assert facts['readiness']=='ready' and facts['completed_parts']==3 and facts['total_parts']==3
    assert not facts['has_usable_knowledge']


def test_partial_failure_preserves_grounded_knowledge_and_retrieval(client, source, knowledge, monkeypatch):
    s= db.sources[0]
    original=client.get(f"/sources/{s['id']}/chunks").json()['items'][0]
    s['chunks_path']=save_chunks(s['id'],[original,{'id':'later','source_id':s['id'],'text':'More practice.'}])
    before=[dict(a) for a in db.knowledge_assets]
    def fail(jid):
        next(j for j in db.extraction_jobs if j['id']==jid)['status']='failed'
        raise RuntimeError('private parser/provider prose')
    monkeypatch.setattr(source_interpretation,'run_gemini_knowledge_extraction',fail)
    source_interpretation.interpret_source(s['id'],max_chunks=1)
    facts=summary(client,s['id'])
    assert facts['readiness']=='partly_ready' and facts['has_usable_knowledge']
    assert facts['attention_category']=='build_stopped' and 'private' not in str(facts)
    assert db.knowledge_assets==before
    assert client.get(f"/sources/{s['id']}/knowledge-units").json()['items']
    assert client.get('/knowledge-assets/search',params={'q':'practice','source_id':s['id'],'consolidated':True}).json()['items']
    prepared=client.post('/workshops/prepare',json={'source_ids':[s['id']], 'situation':'Write an essay about practice', 'goal':'Explain practice', 'audience':'Learners', 'constraints':[], 'tone_or_style':'Clear', 'output_type':'writing'})
    assert prepared.status_code==200, prepared.text
    assert prepared.json()['knowledge_unit_count']>0


def test_attention_resolves_latest_success_and_reset_not_old_prose(client,source,monkeypatch):
    s=install_parts(source);job(s,'p0','completed');j=job(s,'p1','failed');s['stopped_reason']='old failure'
    assert summary(client,s['id'])['attention_category']=='build_stopped'
    monkeypatch.setattr(gemini_knowledge_extraction,'generate_structured_interaction',lambda *a,**k:pytest.fail('reset must not invoke provider'))
    assert client.post(f"/knowledge-extractions/{j['id']}/recover").json()['status']=='pending_ai'
    assert j['status']=='pending_ai' and s['stopped_reason'] is None
    s['stopped_reason']='stale restored text'
    assert summary(client,s['id'])['attention_category'] is None
    j['status']='completed';job(s,'p2','completed')
    facts=summary(client,s['id'])
    assert facts['readiness']=='ready' and facts['attention_category'] is None


@pytest.mark.parametrize('seconds,allowed',[(599,False),(600,True),(601,True)])
def test_recovery_rule_shared_by_summary_and_reset(source,monkeypatch,seconds,allowed):
    s=install_parts(source);now=datetime(2026,10,11,tzinfo=timezone.utc)
    j=job(s,'p0','running',started_at=(now-timedelta(seconds=seconds)).isoformat())
    monkeypatch.setattr('app.services.knowledge_extraction.utc_now',lambda:now)
    facts=source_summary.source_summaries(source_id=s['id'],now=now)[0]
    assert facts.operation=='build_unconfirmed'
    assert facts.attention_category==('build_unconfirmed' if allowed else None) and facts.recovery[0].allowed==allowed
    assert facts.recovery[0].eligible_at==now+timedelta(seconds=600-seconds)
    if allowed:
        recover_job(j['id']);assert j['status']=='pending_ai'
    else:
        with pytest.raises(ValueError,match='ten minutes'):recover_job(j['id'])


def test_summary_is_compact_and_audit_independent(client,source,monkeypatch):
    def forbidden(*a,**k):pytest.fail('summary must not audit, consolidate or retrieve units')
    monkeypatch.setattr('app.services.knowledge_extraction.audit_source',forbidden)
    monkeypatch.setattr('app.services.knowledge_extraction.consolidate_knowledge_assets',forbidden)
    facts=summary(client,source[0]['id'])
    assert facts['total_parts']==1
    response=client.get('/sources/summaries',params={'library_id':source[0]['library_id']})
    assert response.status_code==200 and len(response.json())==1
    assert client.get('/sources/summaries',params={'library_id':'other'}).json()==[]
    assert not any(k in facts for k in ['text','jobs','knowledge_units','confidence_distribution','overlap_rate'])


def test_missing_chunks_retains_useful_knowledge_and_unknown_counts(client,source,knowledge):
    db.sources[0]['chunks_path']='/definitely/missing/chunks.json'
    facts=summary(client,source[0]['id'])
    assert facts['total_parts'] is None and facts['completed_parts'] is None
    assert facts['readiness']=='unknown'
    assert facts['attention_category']=='artifact_unavailable' and facts['has_usable_knowledge']


@pytest.mark.parametrize('category',['ocr_required','unsupported_extraction','read_failed'])
def test_safe_durable_read_errors_and_success_clears_them(client,source,monkeypatch,category):
    from app.routers import sources as router
    from app.services.text_extraction import OCRRequiredError, UnsupportedExtractionTypeError
    s=db.sources[0];s.update(chunks_path=None,extracted_text_path=None,processing_status='uploaded')
    error={'ocr_required':OCRRequiredError,'unsupported_extraction':UnsupportedExtractionTypeError,'read_failed':RuntimeError}[category]
    original=router.extract_text_from_file
    monkeypatch.setattr(router,'extract_text_from_file',lambda **k:(_ for _ in ()).throw(error('PRIVATE raw parser input')))
    response=client.post(f"/sources/{s['id']}/process")
    assert response.status_code==400 and 'PRIVATE' not in response.text
    assert s['reading_failure']==category and summary(client,s['id'])['read_state']==category
    monkeypatch.setattr(router,'extract_text_from_file',original)
    assert client.post(f"/sources/{s['id']}/process").status_code==200
    assert s['reading_failure'] is None and summary(client,s['id'])['read_state']=='read'


def test_legacy_read_failure_does_not_guess_ocr(client,source):
    s=db.sources[0];s.update(chunks_path=None,processing_status='extraction_not_supported')
    assert summary(client,s['id'])['read_state']=='read_failed'


@pytest.mark.parametrize('flag',['true','TRUE','1','false',''])
def test_no_config_can_enable_automatic_repair(monkeypatch,flag):
    monkeypatch.setenv('GEMINI_ALLOW_REPAIR',flag)
    monkeypatch.setattr(gemini_knowledge_extraction,'generate_structured_interaction',lambda *a,**k:pytest.fail('automatic repair invoked provider'))
    with pytest.raises(RuntimeError,match='Automatic repair is disabled'):
        gemini_knowledge_extraction.validate_extraction_result(None,'model',{},SimpleNamespace(output_text='{"assets":[{"asset_type":"decision_rule"}]}'))


def test_scanned_pdf_category_comes_from_actual_reader(client,source,monkeypatch):
    from app.services import text_extraction
    s=db.sources[0];s.update(chunks_path=None,extracted_text_path=None,file_type='.pdf',processing_status='uploaded')
    monkeypatch.setattr(text_extraction,'PdfReader',lambda path:SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda:'')]))
    response=client.post(f"/sources/{s['id']}/process")
    assert response.status_code==400 and 'OCR is not supported' in response.json()['detail']
    assert summary(client,s['id'])['read_state']=='ocr_required'


def test_latest_success_removes_historical_failure_attention(client,source):
    s=install_parts(source);job(s,'p0','failed');job(s,'p0','completed');s['stopped_reason']='historical failure'
    assert summary(client,s['id'])['attention_category'] is None


def test_failed_replacement_keeps_ready_knowledge(client,source,knowledge):
    s=db.sources[0];part=source[1]['id'];job(s,part,'failed');s['stopped_reason']='replacement failed'
    facts=summary(client,s['id'])
    assert facts['readiness']=='ready' and facts['has_usable_knowledge']
    assert facts['attention_category']=='build_stopped' and facts['recovery'][0]['allowed']


def test_invalid_provider_output_uses_one_attempt_even_with_flag(client,source,knowledge,monkeypatch):
    from app.services.knowledge_extraction import create_extraction_job
    from app.services.gemini_knowledge_extraction import run_gemini_knowledge_extraction
    s,part=source;before=[dict(a) for a in db.knowledge_assets];calls=[]
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-not-a-key');monkeypatch.setenv('GEMINI_ALLOW_REPAIR','true')
    def generate(**kwargs):
        calls.append(kwargs);return SimpleNamespace(output_text='invalid JSON')
    monkeypatch.setattr(gemini_knowledge_extraction,'generate_structured_interaction',generate)
    attempt=create_extraction_job(s['id'],part['id'],reprocess=True)
    with pytest.raises(RuntimeError,match='Automatic repair is disabled'):
        run_gemini_knowledge_extraction(attempt['id'])
    assert len(calls)==1 and attempt['status']=='failed'
    assert db.knowledge_assets==before and summary(client,s['id'])['has_usable_knowledge']


def test_corrupt_parts_are_unknown_not_complete(client,source,monkeypatch):
    monkeypatch.setattr(source_summary,'load_chunks',lambda path:[{'id':'p0'},{'id':'p0'}])
    facts=summary(client,source[0]['id'])
    assert facts['total_parts'] is None and facts['completed_parts'] is None
    assert facts['readiness']=='unknown'
    assert facts['attention_category']=='artifact_unavailable'


def test_known_empty_parts_are_added(client,source):
    s=install_parts(source,count=0)
    facts=summary(client,s['id'])
    assert facts['readiness']=='added' and facts['completed_parts']==facts['total_parts']==0
    assert facts['attention_category']=='read_failed'


def test_missing_part_reference_with_known_knowledge_is_unknown(client,source,knowledge):
    s=db.sources[0];s['chunks_path']=None
    facts=summary(client,s['id'])
    assert facts['readiness']=='unknown' and facts['has_usable_knowledge']
    assert facts['completed_parts'] is None and facts['total_parts'] is None
    assert facts['attention_category']=='artifact_unavailable'


def test_invalid_running_timestamp_is_unconfirmed_but_not_actionable(client,source):
    s=install_parts(source);j=job(s,'p0','running',started_at='not-a-timestamp')
    facts=summary(client,s['id'])
    assert facts['operation']=='build_unconfirmed' and facts['attention_category'] is None
    assert facts['recovery'][0]['allowed'] is False and facts['recovery'][0]['eligible_at'] is None
    with pytest.raises(ValueError):recover_job(j['id'])
    assert j['status']=='running'


def test_other_failure_creates_attention_while_running_is_not_resettable(client,source):
    s=install_parts(source);job(s,'p0','running',started_at=datetime.now(timezone.utc).isoformat());job(s,'p1','failed')
    facts=summary(client,s['id'])
    assert facts['operation']=='build_unconfirmed' and facts['attention_category']=='build_stopped'
    assert [r['allowed'] for r in facts['recovery']]==[False,True]
