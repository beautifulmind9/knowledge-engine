#!/usr/bin/env python3
"""One frozen synthetic source answer only. prepare/status are entirely offline.

generate needs a separate interactive owner authorization. No count/recount command.
"""
from datetime import datetime,timezone,timedelta
import argparse
import getpass
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE=ROOT/'storage/source-answer-count-only/run-002'
EXPECTED_REQUEST='ea7e0ddf66722f44916dce77b53810357b9c77512bf83e872ac590423a2b7078'
EXPECTED_COUNT_BACKUP='d913eefa3ce3567a705e7bee988897d9936fae85aa0a06333109c97dd8dd4c4e'
PHRASE='AUTHORIZE ONE SYNTHETIC GENERATION'
ALLOWED_COUNT_BASELINE_CHANGES={
    'apps/api/app/services/source_answer.py','apps/api/app/services/source_answer_transport.py',
    'apps/api/app/services/ai_gateway.py'}


class PreflightError(RuntimeError):pass

def require(ok,code):
    if not ok:raise PreflightError(code)

def now():return datetime.now(timezone.utc).isoformat()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(path.read_text())

def counter_tool():
    spec=importlib.util.spec_from_file_location('_ke_count_only',ROOT/'tools/source_answer_count.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def implementation_hashes():
    result=counter_tool().implementation_hashes()
    result['tools/source_answer_generate.py']=sha(Path(__file__).read_bytes())
    return result


def write(path,value):
    counter_tool().write(path,value)
    # Intent/result directory entry must be durable before proceeding.
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def original_evidence(workspace,*,before_generation):
    tool=counter_tool();backup=workspace/'exports/count-terminal.zip'
    require(sha(backup.read_bytes())==EXPECTED_COUNT_BACKUP,'count_backup_fingerprint_mismatch')
    tool.verify_backup(backup)
    with ZipFile(backup) as archive:
        manifest=json.loads(archive.read('MANIFEST.json'))
        for name,digest in manifest.items():
            if name=='application/knowledge.sqlite3' and not before_generation:continue
            path=workspace/name
            require(path.resolve().is_relative_to(workspace) and not path.is_symlink(),'unsafe_evidence_path')
            require(path.is_file() and sha(path.read_bytes())==digest,'original_count_evidence_changed')
    return {name:digest for name,digest in manifest.items() if name!='application/knowledge.sqlite3'}


def preflight(workspace,*,prepared):
    require(workspace==DEFAULT_WORKSPACE.resolve(),'workspace_not_authorized_for_this_test')
    require(not (workspace/'audit/generation-intent.json').exists(),'generation_intent_exists_never_resend')
    require(not list((workspace/'audit').glob('generation-attempt-*')) and not (workspace/'audit/generation-result.json').exists()
            and not (workspace/'exports/generation-terminal.zip').exists(),'ambiguous_generation_evidence_never_resend')
    require(subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='research/source-first-search','wrong_branch')
    for path in [workspace,*workspace.rglob('*')]:
        require(not path.is_symlink() and not path.stat().st_mode&0o077 and path.stat().st_uid==os.getuid(),'workspace_not_private')
    evidence=original_evidence(workspace,before_generation=True)
    tool=counter_tool();plan=read(workspace/'audit/plan.json');count_result=read(workspace/'audit/count-result.json')
    require(plan['request_sha256']==EXPECTED_REQUEST and count_result.get('request_sha256')==EXPECTED_REQUEST,'wrong_frozen_request')
    require(count_result.get('status')=='counted_with_headroom' and count_result.get('generation_attempts')==0
            and count_result.get('allowance_before')==count_result.get('allowance_after'),'count_not_verified')
    current=tool.implementation_hashes()
    differences={name for name,h in plan['implementation_hashes'].items() if current.get(name)!=h}
    require(differences<=ALLOWED_COUNT_BASELINE_CHANGES,'unexpected_count_baseline_code_change')
    if prepared:
        execution=read(workspace/'audit/generation-plan.json')
        require(execution['implementation_hashes']==implementation_hashes(),'execution_implementation_changed')
        require(execution['original_evidence']==evidence and execution['request_sha256']==EXPECTED_REQUEST,'execution_plan_changed')
    tool.environment(workspace)
    from app.services import source_answer_transport as transport,ai_gateway
    from app.db import mock_data as db
    frozen=transport.FrozenRequest(transport.canonical(plan['request'])).validate()
    require(frozen.fingerprint==EXPECTED_REQUEST and tool.current_request(plan)==frozen,'current_source_request_mismatch')
    receipt=transport.load_receipt(frozen)
    require(receipt.total_tokens==count_result['counted_input_tokens'],'count_result_receipt_disagreement')
    require(not transport.generation_authorized(),'generation_already_armed')
    require(not db.outputs and not list((workspace/'application/source_answers').glob('*.json')),'unexpected_prior_answer')
    status=ai_gateway.status()
    require(not status['paused'] and status['daily_call_limit']==450 and status['calls_today']+2<=450,'allowance_unavailable')
    return plan,frozen,receipt,evidence,sorted(differences)


def prepare(workspace):
    require(not (workspace/'audit/generation-plan.json').exists(),'execution_plan_exists_never_overwrite')
    plan,frozen,receipt,evidence,differences=preflight(workspace,prepared=False)
    execution={'contract':'source-answer-generation-plan-v1','prepared_at':now(),'request_sha256':frozen.fingerprint,
        'count_receipt_sha256':evidence['application/source_answer_counts/'+frozen.fingerprint+'.json'],
        'counted_tokens':receipt.total_tokens,'receipt_expires_at':(datetime.fromisoformat(receipt.counted_at)+timedelta(hours=24)).isoformat(),
        'implementation_hashes':implementation_hashes(),'original_evidence':evidence,
        'count_baseline_implementation_hashes':plan['implementation_hashes'],
        'reviewed_code_changes_since_count':differences,'maximum_initial_generations':1,'maximum_provider_attempts':2,
        'generation_enabled_for_other_workflows':False}
    write(workspace/'audit/generation-plan.json',execution)
    print(json.dumps({'prepared':True,'request_sha256':frozen.fingerprint,'execution_plan_sha256':sha((workspace/'audit/generation-plan.json').read_bytes()),
                      'counted_tokens':receipt.total_tokens,'generation_dispatched':False},indent=2))


class GatewayAudit(logging.Handler):
    def __init__(self,path):
        super().__init__();self.stream=path.open('x');os.chmod(path,0o600)
        formatter=logging.Formatter('%(asctime)sZ %(message)s');formatter.converter=time.gmtime;self.setFormatter(formatter)
    def emit(self,record):
        if str(record.msg).startswith(('Gemini provider attempt admitted:','Gemini provider failure diagnostic:')):
            self.stream.write(self.format(record)+'\n');self.stream.flush();os.fsync(self.stream.fileno())
    def close(self):
        self.stream.close();super().close()


def backup(workspace):
    target=workspace/'exports/generation-terminal.zip'
    files=sorted(p for p in workspace.rglob('*') if p.is_file() and 'exports' not in p.relative_to(workspace).parts)
    require(all(not p.is_symlink() for p in files),'unsafe_backup_member')
    manifest={str(p.relative_to(workspace)):sha(p.read_bytes()) for p in files}
    with target.open('xb') as stream:
        os.chmod(target,0o600)
        with ZipFile(stream,'w',ZIP_DEFLATED) as archive:
            for path in files:archive.writestr(str(path.relative_to(workspace)),path.read_bytes())
            archive.writestr('MANIFEST.json',json.dumps(manifest,sort_keys=True,indent=2))
        stream.flush();os.fsync(stream.fileno())
    counter_tool().verify_backup(target)
    return {'path':str(target),'sha256':sha(target.read_bytes()),'member_count':len(files)}


def generate(workspace):
    preflight(workspace,prepared=True)
    require(sys.stdin.isatty(),'interactive_terminal_required')
    print('ONE frozen synthetic answer; at most one identical confirmed-503 retry. No repair or recount.')
    print('Request SHA-256:',EXPECTED_REQUEST)
    require(input('Type '+PHRASE+': ')==PHRASE,'authorization_not_supplied')
    require(input('Confirm Free Tier and billing disabled: ')=='FREE TIER BILLING DISABLED','free_tier_not_confirmed')
    key=getpass.getpass('Same Free Tier Gemini API key (hidden): ')
    require(bool(key) and not any(c.isspace() for c in key),'invalid_credential_input')
    # Recheck freshness/source/code after interactive input, before durable intent.
    plan,frozen,receipt,_,_=preflight(workspace,prepared=True)
    from app.services import source_answer_transport as transport,source_answer as adapter,ai_gateway
    from app.models.source_answer import SourceAnswerRequest
    os.environ.update(GEMINI_API_KEY=key,GEMINI_FREE_TIER_CONFIRMED='true',GEMINI_DAILY_CALL_LIMIT='450',GEMINI_MODEL=transport.MODEL)
    try:
        admission=ai_gateway.status()
        require(admission['configured'] and admission['free_tier_confirmed'] and not admission['paused']
                and admission['daily_call_limit']==450 and admission['calls_today']+2<=450,'allowance_unavailable')
        before=adapter.allowance_snapshot();started=now()
        marker=workspace/'audit/generation-intent.json'
        write(marker,{'at_utc':started,'authorized':True,'request_sha256':frozen.fingerprint,
            'max_provider_attempts':2,'maximum_initial_generations':1,'allowance_before':before,
            'execution_plan_sha256':sha((workspace/'audit/generation-plan.json').read_bytes()),
            'free_tier_confirmed':True,'credential_configured':True})
        terminal={'contract':'source-answer-generation-result-v1','started_at':started,'request_sha256':frozen.fingerprint,
                  'allowance_before':before,'status':'interrupted_or_unconfirmed','answer_accepted':False}
        logger=logging.getLogger('app.services.ai_gateway');old_level=logger.level;handler=None
        def audit(number,event,detail):
            write(workspace/'audit'/f'generation-attempt-{number:03d}-{event}.json',{'at_utc':now(),'attempt_number':number,**detail})
        try:
            handler=GatewayAudit(workspace/'audit/generation-gateway.log');logger.addHandler(handler);logger.setLevel(logging.INFO)
            with transport._one_shot_generation_scope(frozen.fingerprint,marker,audit) as permit:
                operation=adapter.answer_source(SourceAnswerRequest(question=plan['question'],question_scope='targeted',
                    source_ids=[plan['source_id']],library_id=plan['library_id']))
                terminal.update(operation_response=operation,status=operation['status'],
                    answer_accepted=operation.get('answer') is not None,
                    transport_dispatch_reservations=permit['dispatches'])
        except BaseException as error:
            terminal.update(status='stopped_for_review',error_category=type(error).__name__,
                http_status=getattr(error,'status_code',None),
                interruption_category=(getattr(error,'headers',None) or {}).get('X-KE-Interruption-Category'))
        finally:
            if handler is not None:logger.removeHandler(handler);handler.close()
            logger.setLevel(old_level)
            os.environ.pop('GEMINI_API_KEY',None);key=None
            after=adapter.allowance_snapshot();attempts=adapter.attempts_between(before,after)
            terminal.update(completed_at=now(),allowance_after=after,gateway_admitted_attempts=attempts)
            if attempts not in (1,2):terminal.update(status='stopped_for_review',answer_accepted=False,rejection_reason='attempt_accounting_inconsistent')
            try:original_evidence(workspace,before_generation=False)
            except Exception:terminal.update(status='stopped_for_review',answer_accepted=False,rejection_reason='original_evidence_changed')
            write(workspace/'audit/generation-result.json',terminal)
            exported=backup(workspace)
            print(json.dumps({'status':terminal['status'],'answer_accepted':terminal['answer_accepted'],
                'gateway_admitted_attempts':attempts,'backup':exported,'stop':'Human review required. Never resend.'},indent=2))
    finally:
        os.environ.pop('GEMINI_API_KEY',None);key=None
    if terminal['status'] not in ('answered','insufficient_evidence','broader_coverage_required','unsupported_content'):
        raise SystemExit(1)


def status(workspace):
    execution=read(workspace/'audit/generation-plan.json')
    original_evidence(workspace,before_generation=False)
    raw=read(workspace/'application/source_answer_counts'/(EXPECTED_REQUEST+'.json'))
    expiry=datetime.fromisoformat(raw['receipt']['counted_at'])+timedelta(hours=24)
    result=read(workspace/'audit/generation-result.json') if (workspace/'audit/generation-result.json').exists() else {}
    terminal_zip=workspace/'exports/generation-terminal.zip'
    if terminal_zip.exists():counter_tool().verify_backup(terminal_zip)
    print(json.dumps({'request_sha256':execution['request_sha256'],
        'implementation_matches':execution['implementation_hashes']==implementation_hashes(),
        'receipt_fresh':datetime.now(timezone.utc)<expiry,'receipt_expires_at':expiry.isoformat(),
        'generation_intent':(workspace/'audit/generation-intent.json').exists(),'terminal_status':result.get('status'),
        'gateway_admitted_attempts':result.get('gateway_admitted_attempts'),
        'generation_backup_verified':terminal_zip.exists(),'ordinary_api_generation_enabled':False},indent=2))


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare','status','generate']);parser.add_argument('--workspace',type=Path,default=DEFAULT_WORKSPACE)
    args=parser.parse_args();workspace=args.workspace.expanduser().resolve()
    require(workspace.is_relative_to((ROOT/'storage').resolve()),'workspace_outside_private_storage')
    {'prepare':prepare,'status':status,'generate':generate}[args.command](workspace)


if __name__=='__main__':
    try:main()
    except PreflightError as error:print('STOP:',str(error),file=sys.stderr);sys.exit(1)
    except Exception:print('STOP: local preflight/audit failure; never reset intent or resend.',file=sys.stderr);sys.exit(1)
