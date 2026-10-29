#!/usr/bin/env python3
"""One-shot SYNTHETIC counting only. No generation command or dispatch path.

prepare: offline explicit empty SQLite bootstrap + normal deterministic ingestion.
count: separate interactive authorization, credential, durable intent, ONE count.
status: read-only standard-library inspection of retained audit and verified ZIP.
"""
import argparse
from datetime import datetime,timezone
import getpass
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'acceptance/extraction_quality_2026-10-17/source.md'
SOURCE_SHA='93afffd120832c93694a2e854e4a8dd444e0d1f83bc05d812ab7d49390485de8'
QUESTION='What does consent to inspect authorize, and what actions require further consent?'
PHRASE='AUTHORIZE ONE SYNTHETIC COUNT ONLY'


def implementation_hashes():
    names=['tools/source_answer_count.py','apps/api/app/services/source_answer.py','apps/api/app/services/source_answer_transport.py',
           'apps/api/app/services/ai_gateway.py','apps/api/app/services/source_context.py','apps/api/app/services/source_search.py',
           'apps/api/app/models/source_answer.py']
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}


def now():return datetime.now(timezone.utc).isoformat()
def require(condition,message):
    if not condition:raise RuntimeError(message)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def write(path,value):
    raw=json.dumps(value,ensure_ascii=False,indent=2).encode()
    with path.open('xb') as stream:
        os.chmod(path,0o600);stream.write(raw);stream.flush();os.fsync(stream.fileno())


def environment(workspace):
    os.environ['KNOWLEDGE_ENGINE_STORAGE']=str(workspace/'application')
    os.environ['KNOWLEDGE_ENGINE_PERSISTENCE_MODE']='local'
    for key in list(os.environ):
        if key.startswith(('GEMINI_','SUPABASE_')) or key in ('KNOWLEDGE_ENGINE_DATABASE_URL','KNOWLEDGE_ENGINE_WORKSPACE_KEY'):
            os.environ.pop(key,None)
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(ROOT/'apps/api'))


def backup(workspace):
    files=sorted(p for p in workspace.rglob('*') if p.is_file() and 'exports' not in p.relative_to(workspace).parts)
    manifest={str(p.relative_to(workspace)):digest(p.read_bytes()) for p in files}
    target=workspace/'exports'/('count-terminal.zip' if (workspace/'audit/count-intent.json').exists() else 'prepared.zip')
    with target.open('xb') as stream:
        os.chmod(target,0o600)
        with ZipFile(stream,'w',ZIP_DEFLATED) as archive:
            for path in files:archive.writestr(str(path.relative_to(workspace)),path.read_bytes())
            archive.writestr('MANIFEST.json',json.dumps(manifest,sort_keys=True,indent=2))
        stream.flush();os.fsync(stream.fileno())
    verify_backup(target)
    return {'path':str(target),'sha256':digest(target.read_bytes()),'files':len(files)}


def verify_backup(path):
    with ZipFile(path) as archive:
        require(archive.testzip() is None,'Backup CRC failure')
        for name,expected in json.loads(archive.read('MANIFEST.json')).items():
            require(digest(archive.read(name))==expected,'Backup digest mismatch')


def current_request(plan):
    from app.db import mock_data as db
    from app.services.source_context import build_source_context,verify_snapshot
    from app.services.source_answer import INSTRUCTIONS,SourceAnswerDocument
    from app.services.source_answer_transport import freeze,MODEL
    require(len(db.sources)==1 and not db.knowledge_assets and not db.extraction_jobs,'Unexpected application state')
    require(db.sources[0]['id']==plan['source_id'],'Unexpected source identity')
    require(digest(SOURCE.read_bytes())==SOURCE_SHA,'Frozen source changed')
    require(plan['question']==QUESTION and plan['source_sha256']==SOURCE_SHA,'Synthetic plan changed')
    package=build_source_context(QUESTION,[plan['source_id']],plan['library_id'])
    require(verify_snapshot(package),'Source snapshot invalid')
    require(package['sources'][0]['original_sha256']==SOURCE_SHA,'Stored source differs from frozen synthetic source')
    schema=SourceAnswerDocument.model_json_schema()
    schema['$defs']['SourceCitation']['properties']['evidence_ref']['enum']=sorted(e['evidence_ref'] for e in package['evidence'])
    return freeze(MODEL,{'instructions':INSTRUCTIONS,'question':QUESTION,'source_context':package},schema)


def prepare(workspace):
    require(subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='research/source-first-search','Wrong branch')
    require(digest(SOURCE.read_bytes())==SOURCE_SHA,'Frozen source hash mismatch')
    workspace.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    workspace.mkdir(mode=0o700)  # Never reuse/reset a workspace.
    for name in ('application','audit','exports'):(workspace/name).mkdir(mode=0o700)
    environment(workspace)
    from app.persistence.sqlite import SQLiteStateStore
    store=SQLiteStateStore(workspace/'application',workspace/'application/state.json',workspace/'application/knowledge.sqlite3',ROOT/'apps/api')
    empty={key:[] for key in ('libraries','sources','extraction_jobs','knowledge_assets','outputs')};empty['usage']={}
    store.save(empty);require(store.load()==empty,'Empty bootstrap verification failed')
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        library=client.post('/libraries',json={'name':'Synthetic consent count only'});require(library.status_code==200,'Library preparation failed')
        source=client.post('/sources',json={'library_id':library.json()['id'],'title':'Frozen synthetic repair source'});require(source.status_code==200,'Source preparation failed')
        sid=source.json()['id']
        uploaded=client.post(f'/sources/{sid}/upload',files={'file':('source.md',SOURCE.read_bytes(),'text/markdown')})
        require(uploaded.status_code==200,'Upload failed')
        processed=client.post(f'/sources/{sid}/process');require(processed.status_code==200,'Deterministic processing failed')
        plan={'contract':'source-answer-count-plan-v1','created_at':now(),'source_id':sid,'library_id':library.json()['id'],
              'source_sha256':SOURCE_SHA,'question':QUESTION,'implementation_hashes':implementation_hashes(),'code_baseline':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()}
        frozen=current_request(plan)
        plan.update(request_sha256=frozen.fingerprint,request=frozen.value,
                    planned_count_operations=1,planned_generation_operations=0)
        write(workspace/'audit/plan.json',plan)
        write(workspace/'audit/prepared-usage.json',client.get('/usage').json())
    # SQLite now closed. Make every retained artifact owner-only.
    for path in workspace.rglob('*'):os.chmod(path,0o700 if path.is_dir() else 0o600)
    result=backup(workspace)
    print(json.dumps({'prepared':True,'request_sha256':frozen.fingerprint,'backup':result,'generation_enabled':False},indent=2))


def count(workspace):
    require(not (workspace/'audit/count-intent.json').exists(),'Counting intent already exists; NEVER retry/reset')
    plan=json.loads((workspace/'audit/plan.json').read_text())
    require(plan.get('implementation_hashes')==implementation_hashes(),'Implementation changed after preparation')
    environment(workspace)
    from app.services import source_answer_transport as transport,ai_gateway
    frozen=current_request(plan)
    require(frozen.fingerprint==plan['request_sha256'] and frozen.value==plan['request'],'Prepared request changed')
    require(not transport.generation_authorized(),'Generation must be disabled')
    require(sys.stdin.isatty(),'Interactive Terminal required for hidden credential entry')
    print('One countTokens request, zero generation. Cost/quota caveat applies; owner approval required.')
    print('Request SHA-256:',frozen.fingerprint)
    require(input('Type '+PHRASE+': ')==PHRASE,'Authorization not supplied; no request')
    require(input('Confirm Free Tier and billing disabled by typing FREE TIER BILLING DISABLED: ')=='FREE TIER BILLING DISABLED','Free Tier confirmation missing')
    key=getpass.getpass('Gemini API key (hidden, memory only): ')
    require(bool(key),'Credential missing')
    before=ai_gateway.current_usage_state()
    # Durable intent BEFORE any possible network dispatch. An interruption is never retried.
    write(workspace/'audit/count-intent.json',{'at_utc':now(),'request_sha256':frozen.fingerprint,'operation':'countTokens','maximum_attempts':1,'generation_attempts':0})
    result={'started_at':now(),'request_sha256':frozen.fingerprint,'count_dispatches_reserved':1,'generation_attempts':0,'allowance_before':before}
    try:
        response=transport.post(frozen,'countTokens',key,count_authorized=True)
        result['response']=response
        receipt=transport.receipt_from_response(frozen,response)
        transport.save_receipt(frozen,receipt,response)
        transport.verify_receipt(frozen,receipt)
        result.update(status='counted_with_headroom',counted_input_tokens=receipt.total_tokens,
                      headroom=transport.INPUT_HEADROOM,input_limit=transport.INPUT_LIMIT)
    except BaseException as error:
        # Includes interruption: preserve intent and terminal audit, never resend.
        # No raw exception, response headers or error body is saved/printed.
        result.update(status='stopped_for_review',error_category=type(error).__name__,http_status=getattr(error,'status_code',None))
    finally:
        key=None
        after=ai_gateway.current_usage_state();result.update(completed_at=now(),allowance_after=after)
        if after!=before:result.update(status='stopped_for_review',error_category='generation_allowance_changed')
        write(workspace/'audit/count-result.json',result)
        summary=backup(workspace)
        print(json.dumps({'status':result['status'],'generation_attempts':0,'backup':summary,'stop':'Owner review required. No generation authorized.'},indent=2))
    if result['status']!='counted_with_headroom':raise SystemExit(1)


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare','status','count']);parser.add_argument('--workspace',type=Path,default=ROOT/'storage/source-answer-count-only/run-001')
    args=parser.parse_args();workspace=args.workspace.expanduser().resolve()
    require(workspace.is_relative_to((ROOT/'storage').resolve()),'Workspace must be under private repository storage')
    if args.command=='prepare':prepare(workspace)
    elif args.command=='count':count(workspace)
    else:
        plan=json.loads((workspace/'audit/plan.json').read_text())
        exports=sorted((workspace/'exports').glob('*.zip'))
        for path in exports:verify_backup(path)
        print(json.dumps({'workspace':str(workspace),'request_sha256':plan['request_sha256'],
              'count_intent':(workspace/'audit/count-intent.json').exists(),
              'implementation_matches':plan.get('implementation_hashes')==implementation_hashes(),
              'result':json.loads((workspace/'audit/count-result.json').read_text()) if (workspace/'audit/count-result.json').exists() else None,
              'verified_backups':[str(p) for p in exports],'generation_enabled':False},indent=2))


if __name__=='__main__':
    try:main()
    except Exception:
        # Avoid traceback/source/request/credential exposure. Audit remains authoritative.
        print('STOP: preflight or audit failure. No retry/reset. Inspect private records.',file=sys.stderr)
        sys.exit(1)
