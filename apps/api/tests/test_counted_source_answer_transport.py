"""All token counts here are synthetic mock data. No provider requests."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from fastapi import HTTPException
from app.services import source_answer_transport as transport,source_answer as adapter,ai_gateway
from app.services.source_context import build_source_context
from app.db import mock_data as db
from test_source_search import ROOT,upload
from test_source_answer import request,good_answer


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    def deny(*a,**k):raise AssertionError('No live HTTP/provider requests')
    monkeypatch.setattr('httpx.HTTPTransport.handle_request',deny)
    monkeypatch.setattr(ai_gateway.genai,'Client',deny)
    folder=adapter.STORAGE_ROOT/'source_answer_counts'
    answers=adapter.STORAGE_ROOT/'source_answers'
    assert adapter.STORAGE_ROOT.name.startswith('ke-tests-')
    for path in (folder,answers):
        if path.exists():shutil.rmtree(path)
    yield
    for path in (folder,answers):
        if path.exists():shutil.rmtree(path)


@pytest.fixture
def prepared(client):
    source,_=upload(client,(ROOT/'acceptance/extraction_quality_2026-10-17/source.md').read_text())
    q='consent inspect replace parts';package=build_source_context(q,[source['id']])
    data={'instructions':adapter.INSTRUCTIONS,'question':q,'source_context':package}
    schema=adapter.SourceAnswerDocument.model_json_schema()
    schema['$defs']['SourceCitation']['properties']['evidence_ref']['enum']=sorted(e['evidence_ref'] for e in package['evidence'])
    frozen=transport.freeze(transport.MODEL,data,schema)
    return source,data,schema,frozen


def receipt(frozen,n=100):return transport.receipt_from_response(frozen,{'totalTokens':n})


def ready(monkeypatch,prepared,n=100,authorize=True):
    source,data,schema,frozen=prepared
    r=receipt(frozen,n);transport.save_receipt(frozen,r,{'totalTokens':n})
    if authorize:monkeypatch.setattr(transport,'generation_authorized',lambda *args:True)
    monkeypatch.setattr(transport,'claim_generation',lambda *_:None)
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-key');monkeypatch.setenv('GEMINI_FREE_TIER_CONFIRMED','true')
    monkeypatch.setenv('GEMINI_DAILY_CALL_LIMIT','450')
    monkeypatch.setattr(ai_gateway.time,'sleep',lambda _:None)
    return r


def result(source,prompt=101,answer=None):
    return {'responseId':'mock-counted-response','modelVersion':'mock-version',
        'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(answer or good_answer(source['id']))}]}}],
        'usageMetadata':{'promptTokenCount':prompt,'candidatesTokenCount':80,'thoughtsTokenCount':20,'totalTokenCount':prompt+100}}


@pytest.mark.parametrize('n,accepted',[(1,True),(24576,True),(24577,False),(32768,False)])
def test_headroom_policy_boundaries(prepared,n,accepted):
    frozen=prepared[3];r=receipt(frozen,n)
    if accepted:assert transport.verify_receipt(frozen,r) is r
    else:
        with pytest.raises(transport.BudgetExceeded):transport.verify_receipt(frozen,r)


@pytest.mark.parametrize('change',['missing','request','count_body','model','policy','api','operation','status','time','future','boolean'])
def test_receipt_rejections(prepared,change):
    frozen=prepared[3];r=receipt(frozen)
    fields={'request':('request_sha256','wrong'),'count_body':('count_body_sha256','wrong'),
        'model':('model','other'),'policy':('policy','wrong'),'api':('api_version','v0'),
        'operation':('operation','generateContent'),'status':('http_status',503),
        'time':('counted_at',(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()),
        'future':('counted_at',(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()),'boolean':('total_tokens',True)}
    r=None if change=='missing' else replace(r,**{fields[change][0]:fields[change][1]})
    with pytest.raises(transport.BudgetUnavailable):transport.verify_receipt(frozen,r)


@pytest.mark.parametrize('change',['model','tools','cap','schema','parts','invalid_json'])
def test_unsupported_request_rejection(prepared,change):
    wire=prepared[3].value
    if change=='model':wire['model']='models/other'
    if change=='tools':wire['tools']=[{}]
    if change=='cap':wire['generationConfig']['maxOutputTokens']=4097
    if change=='schema':wire['generationConfig']['responseJsonSchema']='bad'
    if change=='parts':wire['contents'][0]['parts']=[{'fileData':{}}]
    with pytest.raises(transport.BudgetUnavailable):
        transport.FrozenRequest('not-json' if change=='invalid_json' else transport.canonical(wire)).validate()


def test_receipt_roundtrip_private_immutable_and_generation_stays_closed(client,prepared,monkeypatch):
    r=ready(monkeypatch,prepared,authorize=False);frozen=prepared[3]
    assert transport.load_receipt(frozen)==r
    file=adapter.STORAGE_ROOT/'source_answer_counts'/(frozen.fingerprint+'.json')
    assert file.stat().st_mode&0o777==0o600 and file.parent.stat().st_mode&0o777==0o700
    with pytest.raises(RuntimeError):transport.save_receipt(frozen,r,{'totalTokens':100})
    answer=client.post('/experimental/source-answers',json=request(prepared[0]['id'])).json()
    assert answer['status']=='generation_not_authorized' and ai_gateway.status()['calls_today']==0
    assert not transport.generation_authorized()


def test_contradictory_or_public_receipt_not_trusted(prepared):
    frozen=prepared[3];r=receipt(frozen)
    transport.save_receipt(frozen,r,{'totalTokens':100})
    file=adapter.STORAGE_ROOT/'source_answer_counts'/(frozen.fingerprint+'.json');raw=file.read_text()
    file.chmod(0o644)
    with pytest.raises(transport.BudgetUnavailable):transport.load_receipt(frozen)
    file.chmod(0o600);record=json.loads(raw);record['response']['totalTokens']=101;file.write_text(json.dumps(record))
    with pytest.raises(transport.BudgetUnavailable):transport.load_receipt(frozen)


def test_complete_count_and_generation_identity_and_shared_allowance(client,prepared,monkeypatch):
    ready(monkeypatch,prepared);source,data,schema,frozen=prepared;calls=[]
    def fake(req,operation,key,**kwargs):
        calls.append((req,operation));return result(source,prompt=105)
    monkeypatch.setattr(transport,'post',fake)
    answer=client.post('/experimental/source-answers',json=request(source['id'])).json()
    assert answer['status']=='answered' and answer['actual_provider_attempts']==len(calls)==1
    assert calls[0]==(frozen,'generateContent')
    assert frozen.counting_body['generateContentRequest']=={'model':'models/'+transport.MODEL,**frozen.generation_body}
    saved=client.get('/experimental/source-answers/'+answer['record_id']).json()
    assert saved['count_usage_difference']==5  # exact equality is deliberately NOT required.
    assert saved['frozen_request']==frozen.value and saved['actual_usage']['total_input_tokens']==105
    assert saved['model_version']=='mock-version' and saved['api_surface']=='generateContent'
    assert not db.knowledge_assets and not db.extraction_jobs


@pytest.mark.parametrize('status,attempts',[(503,2),(400,1),(429,1),(500,1)])
def test_gateway_retry_and_quota_controls_unchanged(client,prepared,monkeypatch,status,attempts):
    ready(monkeypatch,prepared);source=prepared[0];calls=[]
    def fake(req,op,key,**kw):
        calls.append(req.encoded)
        if len(calls)==1:raise transport.ProviderHTTPError(status)
        return result(source)
    monkeypatch.setattr(transport,'post',fake)
    response=client.post('/experimental/source-answers',json=request(source['id']))
    assert len(calls)==ai_gateway.status()['calls_today']==attempts
    if status==503:
        assert response.json()['status']=='answered' and calls[0]==calls[1]
    else:assert response.status_code in (429,502)
    if status==429:assert ai_gateway.status()['paused']


def test_retry_requires_second_allowance_admission(client,prepared,monkeypatch):
    ready(monkeypatch,prepared);monkeypatch.setenv('GEMINI_DAILY_CALL_LIMIT','1');calls=[]
    def fake(*args,**kw):calls.append(1);raise transport.ProviderHTTPError(503)
    monkeypatch.setattr(transport,'post',fake)
    response=client.post('/experimental/source-answers',json=request(prepared[0]['id']))
    assert response.status_code==429 and len(calls)==ai_gateway.status()['calls_today']==1


@pytest.mark.parametrize('failure',['truncated','missing_usage','contradictory_total','headroom','output','citation','schema'])
def test_invalid_generation_stops_once_and_retains_audit(client,prepared,monkeypatch,failure):
    ready(monkeypatch,prepared);source=prepared[0];raw=result(source);calls=[]
    if failure=='truncated':raw['candidates'][0]['finishReason']='MAX_TOKENS'
    if failure=='missing_usage':raw.pop('usageMetadata')
    if failure=='contradictory_total':raw['usageMetadata']['totalTokenCount']+=1
    if failure=='headroom':raw=result(source,prompt=100+8192+1)
    if failure=='output':raw['usageMetadata'].update(candidatesTokenCount=4096,totalTokenCount=101+4096+20)
    if failure in ('citation','schema'):
        payload=good_answer(source['id'])
        if failure=='citation':payload['sections'][0]['citations'][0]['quote']='invented'
        if failure=='schema':payload['unexpected']='extra'
        raw=result(source,answer=payload)
    def fake(*a,**kw):calls.append(1);return raw
    monkeypatch.setattr(transport,'post',fake)
    response=client.post('/experimental/source-answers',json=request(source['id'])).json()
    assert response['status']=='response_rejected' and response['answer'] is None and len(calls)==1
    assert client.get('/experimental/source-answers/'+response['audit_record_id']).status_code==200


def test_changed_payload_or_schema_refused_before_allowance(prepared,monkeypatch):
    r=ready(monkeypatch,prepared);_,data,schema,frozen=prepared
    data['question']+=' changed'
    with pytest.raises(HTTPException) as error:
        ai_gateway.generate(transport.MODEL,data,schema,counted_request=frozen,count_receipt=r,verified_request_sha256=frozen.fingerprint)
    assert error.value.status_code==409 and ai_gateway.status()['calls_today']==0


@pytest.mark.parametrize('outcome',['success','503','interrupted'])
def test_count_only_tool_real_prepare_one_mock_count_restart_marker_and_backup(tmp_path,outcome):
    # Separate process exercises actual application boot and deterministic ingestion.
    workspace=tmp_path/'count-run'
    script="""
import importlib.util,sys,builtins,getpass,httpx,json
from pathlib import Path
spec=importlib.util.spec_from_file_location('count_tool',sys.argv[1]);tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
run=Path(sys.argv[2]);tool.prepare(run)
from types import SimpleNamespace
sys.stdin=SimpleNamespace(isatty=lambda:True)
answers=iter([tool.PHRASE,'FREE TIER BILLING DISABLED']);builtins.input=lambda _:next(answers);getpass.getpass=lambda _:'synthetic-credential'
calls=[]
class FakeHTTP:
 def __init__(self,**kw):assert kw['trust_env'] is False and kw['follow_redirects'] is False
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def post(self,url,**kw):
  assert url.endswith(':countTokens');calls.append(json.loads(kw['content']))
  assert kw['headers']['x-goog-api-key']=='synthetic-credential'
  if sys.argv[3]=='503':return httpx.Response(503,json={'error':'not retained'})
  if sys.argv[3]=='interrupted':raise KeyboardInterrupt()
  return httpx.Response(200,json={'totalTokens':100})
httpx.Client=FakeHTTP
try:tool.count(run)
except SystemExit as error:assert sys.argv[3]!='success' and error.code==1
assert len(calls)==1
try:tool.count(run)
except RuntimeError:pass
else:raise AssertionError('Duplicate count allowed')
assert len(calls)==1
assert not any('synthetic-credential' in p.read_text(errors='ignore') for p in run.rglob('*.json'))
assert (run/'audit/count-intent.json').exists()
tool.verify_backup(run/'exports/count-terminal.zip')
result=json.loads((run/'audit/count-result.json').read_text());assert result['generation_attempts']==0 and result['allowance_before']==result['allowance_after']
"""
    completed=subprocess.run([sys.executable,'-c',script,str(ROOT/'tools/source_answer_count.py'),str(workspace),outcome],capture_output=True,text=True)
    assert completed.returncode==0,completed.stderr
    assert 'synthetic-credential' not in completed.stdout+completed.stderr
    plan=json.loads((workspace/'audit/plan.json').read_text())
    assert plan['planned_count_operations']==1 and plan['planned_generation_operations']==0
    assert not list((workspace/'application').glob('source_answers/*.json'))


def test_count_and_generation_require_separate_authorization(prepared):
    frozen=prepared[3]
    with pytest.raises(transport.BudgetUnavailable,match='Counting is not authorized'):
        transport.post(frozen,'countTokens','synthetic')
    with pytest.raises(transport.BudgetUnavailable,match='Generation is not authorized'):
        transport.post(frozen,'generateContent','synthetic')
    assert ai_gateway.status()['calls_today']==0


def test_private_export_includes_count_snapshot_and_manifest(client,prepared):
    from zipfile import ZipFile
    frozen=prepared[3];r=receipt(frozen);transport.save_receipt(frozen,r,{'totalTokens':100})
    response=client.get('/data/export');assert response.status_code==200
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        name='storage/source_answer_counts/'+frozen.fingerprint+'.json'
        raw=archive.read(name);manifest=json.loads(archive.read('source-answer-manifest.json'))
        assert manifest[name]['sha256']==transport.hashlib.sha256(raw).hexdigest()
        assert json.loads(raw)['request']==frozen.value


def test_actual_body_uses_fixed_endpoint_no_proxy_redirects_or_retries(prepared,monkeypatch):
    frozen=prepared[3];calls=[]
    class FakeHTTP:
        def __init__(self,**kwargs):
            assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
            assert kwargs['timeout']==60
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kwargs):
            calls.append((url,json.loads(kwargs['content'])))
            return transport.httpx.Response(200,json={'totalTokens':100})
    monkeypatch.setattr(transport.httpx,'Client',FakeHTTP)
    raw=transport.post(frozen,'countTokens','synthetic',count_authorized=True)
    assert len(calls)==1 and raw=={'totalTokens':100}
    assert calls[0][0]=='https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:countTokens'
    assert calls[0][1]==frozen.counting_body and ai_gateway.status()['calls_today']==0


def test_count_backup_has_no_hosted_filesystem_or_artifact_io(monkeypatch):
    from zipfile import ZipFile
    monkeypatch.setattr(adapter,'PERSISTENCE_MODE','hosted')
    def deny(*a,**kw):raise AssertionError('Local count backup must not run in hosted mode')
    monkeypatch.setattr(adapter,'get_artifact_store',deny)
    buffer=io.BytesIO()
    with ZipFile(buffer,'w') as archive:adapter.append_private_backup(archive)
    with ZipFile(io.BytesIO(buffer.getvalue())) as archive:assert archive.namelist()==[]
