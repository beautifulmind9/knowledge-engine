"""Real local ingestion/gateway/adapter; HTTP transport is entirely mocked."""
import json
import subprocess
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('scenario',[
 'success','unauthorized','empty_key','expired','implementation_mismatch','request_mismatch','workspace_mismatch','allowance',
 '503','provider_failure','invalid_citation','incomplete','usage_over','usage_missing','invalid_json',
 'interrupted','audit_failure',
])
def test_one_shot_generation_command_offline(tmp_path,scenario):
    script=r'''
import importlib.util,sys,json,builtins,getpass,httpx,hashlib,os
from pathlib import Path
from types import SimpleNamespace
from datetime import timedelta
root=Path(sys.argv[1]);run=Path(sys.argv[2]);scenario=sys.argv[3]
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
c=module('count_tool',root/'tools/source_answer_count.py');c.prepare(run)
from google import genai
def deny(*a,**kw):raise AssertionError('Real provider client/network forbidden')
genai.Client=deny;httpx.HTTPTransport.handle_request=deny
sys.stdin=SimpleNamespace(isatty=lambda:True)
responses=iter([c.PHRASE,'FREE TIER BILLING DISABLED']);builtins.input=lambda _:next(responses);getpass.getpass=lambda _:'synthetic-private-key'
requests=[]
class FakeHTTP:
 def __init__(self,**kw):assert kw['trust_env'] is False and kw['follow_redirects'] is False
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def post(self,url,**kw):
  body=json.loads(kw['content']);requests.append((url,body))
  assert kw['headers']['x-goog-api-key']=='synthetic-private-key'
  if url.endswith(':countTokens'):return httpx.Response(200,json={'totalTokens':6957})
  assert url.endswith(':generateContent')
  generations=[r for r in requests if r[0].endswith(':generateContent')]
  if scenario=='503' and len(generations)==1:return httpx.Response(503,json={'error':'not saved'})
  if scenario=='provider_failure':return httpx.Response(400,json={'error':'not saved'})
  if scenario=='interrupted':raise KeyboardInterrupt()
  data=json.loads(body['contents'][0]['parts'][0]['text']);package=data['source_context']
  e=next(e for e in package['evidence'] if 'Consent to inspect' in e['text'])
  cite={k:e[k] for k in ('evidence_ref','start_char','end_char')};cite['quote']=e['text']
  if scenario=='invalid_citation':cite['quote']='invented'
  answer={'disposition':'answered','title':'Synthetic mock answer','sections':[{'kind':'source_supported','heading':'Consent',
          'content':'Inspection does not authorize replacement.','citations':[cite]}],'limitations':['Mock, not semantic acceptance.']}
  prompt=6957+5 if scenario!='usage_over' else 6957+8192+1
  raw={'responseId':'mock-generation','modelVersion':'mock-version',
       'candidates':[{'finishReason':'MAX_TOKENS' if scenario=='incomplete' else 'STOP',
       'content':{'parts':[{'text':'not-json' if scenario=='invalid_json' else json.dumps(answer)}]}}],
       'usageMetadata':{'promptTokenCount':prompt,'candidatesTokenCount':100,'thoughtsTokenCount':20,'totalTokenCount':prompt+120}}
  if scenario=='usage_missing':raw.pop('usageMetadata')
  return httpx.Response(200,json=raw)
httpx.Client=FakeHTTP;c.count(run)
originals={str(p.relative_to(run)):hashlib.sha256(p.read_bytes()).hexdigest() for p in run.rglob('*') if p.is_file() and p.name!='knowledge.sqlite3'}
g=module('generation_tool',root/'tools/source_answer_generate.py')
g.DEFAULT_WORKSPACE=run
plan=json.loads((run/'audit/plan.json').read_text());g.EXPECTED_REQUEST=plan['request_sha256'];g.EXPECTED_COUNT_BACKUP=hashlib.sha256((run/'exports/count-terminal.zip').read_bytes()).hexdigest()
g.prepare(run)
from app.services import source_answer_transport as t,ai_gateway,source_answer as adapter
from app.models.source_answer import SourceAnswerRequest
ai_gateway.time.sleep=lambda _:None
# No ordinary source-answer request is armed by the prepared execution plan.
assert not t.generation_authorized()
q=SourceAnswerRequest(question=plan['question'],question_scope='targeted',source_ids=[plan['source_id']],library_id=plan['library_id'])
assert adapter.answer_source(q)['status']=='generation_not_authorized'
responses=iter(['WRONG' if scenario=='unauthorized' else g.PHRASE,'FREE TIER BILLING DISABLED'])
builtins.input=lambda _:next(responses)
getpass.getpass=lambda _:'' if scenario=='empty_key' else 'synthetic-private-key'
if scenario=='expired':t.RECEIPT_MAX_AGE=timedelta(seconds=-1)
if scenario=='implementation_mismatch':g.implementation_hashes=lambda:{'changed':'wrong'}
if scenario=='request_mismatch':g.EXPECTED_REQUEST='0'*64
if scenario=='workspace_mismatch':g.DEFAULT_WORKSPACE=run/'other'
if scenario=='allowance':
 original_status=ai_gateway.status
 def unavailable():
  status=original_status();status.update(calls_today=450,paused=True);return status
 ai_gateway.status=unavailable
if scenario=='audit_failure':
 original_write=g.write
 def fail(path,value):
  if 'generation-attempt-' in path.name:raise OSError('synthetic audit failure')
  return original_write(path,value)
 g.write=fail
failed=False
try:g.generate(run)
except (g.PreflightError,ValueError):failed=True
except SystemExit as error:assert error.code==1;failed=True
assert not t.generation_authorized() and 'GEMINI_API_KEY' not in os.environ
preflight_failure=scenario in ['unauthorized','empty_key','expired','implementation_mismatch','request_mismatch','workspace_mismatch','allowance']
initials=[r for r in requests if r[0].endswith(':countTokens')];actual=[r for r in requests if r[0].endswith(':generateContent')]
assert len(initials)==1
if preflight_failure:
 assert failed and not actual and not (run/'audit/generation-intent.json').exists()
else:
 assert (run/'audit/generation-intent.json').exists()
 terminal=json.loads((run/'audit/generation-result.json').read_text())
 assert terminal['gateway_admitted_attempts']==(2 if scenario=='503' else 1)
 assert len(actual)==(0 if scenario=='audit_failure' else 2 if scenario=='503' else 1)
 c.verify_backup(run/'exports/generation-terminal.zip')
 if scenario in ('success','503'):
  assert terminal['status']=='answered' and terminal['answer_accepted'] and not failed
  saved=json.loads(next((run/'application/source_answers').glob('*.json')).read_text())
  assert saved['count_usage_difference']==5 and saved['provider_output_text']
  assert saved['raw_provider_response']['modelVersion']=='mock-version' and saved['validated_citations']
  assert saved['request_sha256']==plan['request_sha256']
 elif scenario not in ('audit_failure','provider_failure','interrupted'):
  assert terminal['status']=='response_rejected' and failed and not terminal['answer_accepted']
 assert adapter.answer_source(q)['status']=='generation_not_authorized'
 old_count=len(actual)
 try:g.generate(run)
 except g.PreflightError as error:assert str(error)=='generation_intent_exists_never_resend'
 else:raise AssertionError('Replay allowed')
 assert len([r for r in requests if r[0].endswith(':generateContent')])==old_count
 if scenario=='503':assert actual[0][1]==actual[1][1]
 for _,body in actual:
  assert {'model':'models/gemini-3.5-flash-lite',**body}==initials[0][1]['generateContentRequest']
for name,digest in originals.items():assert hashlib.sha256((run/name).read_bytes()).hexdigest()==digest
for p in run.rglob('*'):
 if p.is_file() and p.suffix in ('.json','.log'):assert 'synthetic-private-key' not in p.read_text()
print('MOCK_PROOF_OK',scenario,len(actual))
'''
    completed=subprocess.run([sys.executable,'-c',script,str(ROOT),str(tmp_path/'run'),scenario],capture_output=True,text=True)
    assert completed.returncode==0,completed.stderr[-3500:]
    assert 'MOCK_PROOF_OK' in completed.stdout
    assert 'synthetic-private-key' not in completed.stdout+completed.stderr


def test_scope_is_fingerprint_bound_claim_once_and_thread_isolated(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from app.db import persistence
    from app.services import source_answer_transport as t
    application=tmp_path/'application';application.mkdir()
    audit=tmp_path/'audit';audit.mkdir(mode=0o700)
    marker=audit/'generation-intent.json';marker.write_text(json.dumps({'authorized':True,'request_sha256':'a'*64,'max_provider_attempts':2}));marker.chmod(0o600)
    monkeypatch.setattr(persistence,'STORAGE_ROOT',application)
    assert not t.generation_authorized()
    with t._one_shot_generation_scope('a'*64,marker,lambda *a:None) as permit:
        assert t.generation_authorized('a'*64) and not t.generation_authorized('b'*64)
        with ThreadPoolExecutor(1) as executor:assert executor.submit(t.generation_authorized,'a'*64).result() is False
        t.claim_generation('a'*64)
        with pytest.raises(t.BudgetUnavailable):t.claim_generation('a'*64)
        request=type('Request',(),{'fingerprint':'a'*64})()
        t._start_dispatch(request)
        with pytest.raises(t.BudgetUnavailable):t._start_dispatch(request)
        permit['last_http_status']=503
        t._start_dispatch(request)
        with pytest.raises(t.BudgetUnavailable):t._start_dispatch(request)
    assert not t.generation_authorized()
