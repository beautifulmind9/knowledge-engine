"""Phase 2 authority tests; only a disposable local PostgreSQL database."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
import json
import time

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest

from test_partition_store import database
from app.persistence.phase2 import Phase2Coordinator, MARKER, OWNED, compact
from app.persistence.partitions import PartitionConflict
from app.persistence.postgres import PostgresStateStore, StaleStateWriteError, HostedStateStoreError


@pytest.fixture(scope='session')
def phase2_database(database):
    name='phase2_'+uuid4().hex
    with psycopg.connect(database,autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    dsn=database+' dbname='+name
    root=Path(__file__).resolve().parents[1]
    with psycopg.connect(dsn) as conn:
        for filename in ('create_knowledge_engine_state_snapshot.sql','create_knowledge_engine_partitions.sql',
                         'create_knowledge_engine_phase2.sql'):
            conn.execute((root/'schema'/filename).read_text())
    return dsn


def fixture_state():
    return {'schema_version':2,'libraries':[{'id':'l','name':'Synthetic'}],
            'sources':[{'id':'s','library_id':'l','title':'Synthetic','processing_status':'chunked',
                        'stopped_reason':None,'chunk_manifest':{'version':1,'total_parts':2,
                         'chunk_ids':['chunk_s_1','chunk_s_2']},'chunks_path':'chunks/s.json'}],
            'extraction_jobs':[{'id':'j','source_id':'s','chunk_id':'chunk_s_1','status':'pending_ai',
              'asset_count':0,'provider':None,'model':None,'model_response_id':None,'error':None,
              'created_at':'2026-10-16T00:00:00+00:00','completed_at':None,'schema_version':2,'extraction_version':1}],
            'knowledge_assets':[{'id':'old','source_id':'s','chunk_id':'chunk_s_1','active':True,'content':'synthetic '*1000}],
            'outputs':[],'usage':{'calls':7}}


@pytest.fixture
def setup(phase2_database):
    key='phase2-'+uuid4().hex
    state=fixture_state()
    store=PostgresStateStore(phase2_database,key)
    store.load();store.save(state)
    return Phase2Coordinator(phase2_database,key),store,state


def core(c):
    with c.transaction() as tx:
        return tx._one('SELECT payload,revision FROM knowledge_engine.state_snapshots WHERE workspace_key=%s',(tx.workspace,))


def activate(c,revision=1):
    c.prepare(revision,'migration')
    c.backfill(revision)
    c.verify(revision)
    return c.cutover(revision,writers_drained=True)


def claim(c,jid='j',token='token'):
    return c.claim(jid,'synthetic','fixture','claim:'+token,token).value


def test_shadow_preparing_verified_do_not_change_legacy_authority(setup):
    c,store,state=setup
    c.prepare(1,'migration');c.backfill(1)
    assert store.load()==state and not store.phase2
    assert c.prepare(1,'migration')['checkpoint']=={'sources':['s']}
    c.verify(1)
    assert store.load()==state and not store.phase2
    with pytest.raises(PartitionConflict): c.cutover(1)
    c.cutover(1,writers_drained=True)
    after=store.load()
    assert store.phase2 and after['sources']==state['sources']
    assert 'extraction_jobs' not in core(c)['payload']
    assert c.scoped(['s'])['extraction_jobs']==state['extraction_jobs']
    assert core(c)['payload']['knowledge_assets']==state['knowledge_assets']
    assert all(not (set(s)&OWNED) for s in core(c)['payload']['sources'])


def test_partial_checkpoint_resume_and_revision_drift(setup):
    c,store,state=setup
    state['sources'].append({'id':'s2','library_id':'l','title':'Second','processing_status':'not_started'})
    store.save(state)
    c.prepare(2,'migration')
    c.backfill(2,max_sources=1)
    assert c.read_migration()['checkpoint']=={'sources':['s']}
    c.backfill(2,max_sources=1);c.backfill(2,max_sources=1)
    assert c.read_migration()['checkpoint']=={'sources':['s','s2']}
    store.save(state)
    for action in (lambda:c.prepare(3,'migration'),lambda:c.backfill(2),lambda:c.backfill(3),lambda:c.verify(3)):
        with pytest.raises((PartitionConflict,StaleStateWriteError)):action()


def test_exact_verification_detects_tampering(setup):
    c,_,_=setup
    c.prepare(1,'migration');c.backfill(1)
    with c.transaction() as tx:
        tx.connection.execute("UPDATE knowledge_engine.partition_sources SET api_payload='{}',revision=revision+1 "
                              'WHERE workspace_key=%s',(tx.workspace,))
    with pytest.raises(PartitionConflict,match='equivalence'):c.verify(1)


def test_running_legacy_writer_blocks_cutover(setup):
    c,store,state=setup
    state['extraction_jobs'][0].update(status='running',started_at='2026-10-16T00:01:00+00:00')
    store.save(state)
    c.prepare(2,'migration');c.backfill(2);c.verify(2)
    with pytest.raises(PartitionConflict,match='Running'):c.cutover(2,writers_drained=True)


def test_old_writer_cannot_reintroduce_narrow_fields_or_remove_marker(setup):
    c,store,state=setup
    activate(c)
    # Even an old client ignoring CAS cannot overwrite a live authority marker.
    with pytest.raises(PartitionConflict):
        with c.transaction() as tx:
            tx.connection.execute('UPDATE knowledge_engine.state_snapshots SET payload=%s WHERE workspace_key=%s',
                                  (Jsonb(state),tx.workspace))
    with pytest.raises(StaleStateWriteError):store.save(state)


def test_claim_finish_assets_core_and_source_state_atomically(setup):
    c,_,state=setup
    activate(c)
    before=core(c)
    captured=claim(c)
    assert core(c)==before
    assert c.scoped(['s'])['sources'][0]['processing_status']=='knowledge_interpreting'
    assets=[{'id':'new','source_id':'s','chunk_id':'chunk_s_1','active':True}]
    c.finish(captured,assets=assets,response_id='synthetic')
    assert c.read_job('j')['status']=='completed'
    after=core(c)
    assert after['revision']==before['revision']+1
    assert after['payload']['knowledge_assets'][0]['active'] is False
    assert after['payload']['knowledge_assets'][1]==assets[0]
    assert 'extraction_jobs' not in after['payload']
    with c.transaction() as tx:
        assert tx._one('SELECT count(*) AS n FROM knowledge_engine.partition_assets WHERE workspace_key=%s',
                       (tx.workspace,))['n']==0
    replay=c.finish(captured,assets=assets,response_id='synthetic')
    assert replay.replayed and core(c)==after
    with pytest.raises(PartitionConflict):c.finish(captured,error='different command')


def test_failed_completion_rolls_back_core_and_narrow(setup,monkeypatch):
    c,_,_=setup;activate(c);captured=claim(c);before=core(c)
    from app.persistence.partitions import PartitionTransaction
    original=PartitionTransaction.finish_job
    def fail(*args,**kwargs):raise RuntimeError('synthetic failure after core CAS')
    with monkeypatch.context() as patch:
        patch.setattr(PartitionTransaction,'finish_job',fail)
        with pytest.raises(RuntimeError):c.finish(captured,assets=[])
    assert core(c)==before and c.read_job('j')['status']=='running'
    assert c.read_operation('finish:token') is None
    c.finish(captured,assets=[])


@pytest.mark.parametrize('deleted',[False,True])
@pytest.mark.parametrize('lifecycle_first',[False,True])
def test_delete_rechunk_both_commit_orders(setup,deleted,lifecycle_first):
    c,store,_=setup;activate(c);captured=claim(c)
    baseline=store.load();proposed=deepcopy(baseline)
    if deleted:
        proposed['sources']=[];proposed['knowledge_assets']=[]
    else:
        proposed['sources'][0]['chunk_manifest']['chunk_ids']=['chunk_s_new']
        proposed['sources'][0]['chunk_manifest']['total_parts']=1
    if not lifecycle_first:
        c.finish(captured,assets=[])
        baseline=store.load()
        # Preserve the lifecycle change, with refreshed core state after completion.
        proposed['knowledge_assets']=[] if deleted else deepcopy(baseline['knowledge_assets'])
    revision=core(c)['revision']
    c.save_core(baseline,proposed,revision)
    assert c.read_source('s')['generation']==2
    assert c.read_source('s')['deleted'] is deleted
    if lifecycle_first:
        with pytest.raises(PartitionConflict):c.finish(captured,assets=[])
    elif deleted:assert c.read_job('j') is None
    else:assert c.read_job('j')['status']=='completed'
    with pytest.raises(PartitionConflict):c.claim('j','fake','fake','another','other')
    if deleted:
        with pytest.raises(PartitionConflict):
            c.apply('resurrect',{},lambda tx:tx.create_source('s'))


def test_independent_chunks_and_duplicate_claims(setup):
    c,_,_=setup;activate(c)
    second=c.create_job('s','chunk_s_2','j2')
    assert second['status']=='pending_ai'
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims=list(pool.map(lambda pair:claim(c,*pair),[('j','a'),('j2','b')]))
    with pytest.raises(PartitionConflict):claim(c,'j','another')
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda captured:c.finish(captured,assets=[]),claims))
    assert {j['status'] for j in c.scoped(['s'])['extraction_jobs']}=={'completed'}


def test_recovery_stale_claim_and_interruption_state(setup):
    c,_,_=setup;activate(c);captured=claim(c)
    with pytest.raises(PartitionConflict):c.recover('j')
    c.finish(captured,error='synthetic unavailable')
    c.source_fields('s',{'processing_status':'knowledge_interpreting','stopped_reason':'interrupted'})
    assert c.scoped(['s'])['sources'][0]['stopped_reason']=='interrupted'
    c.recover('j')
    assert c.scoped(['s'])['sources'][0]['stopped_reason'] is None
    newer=claim(c,token='new')
    # A receipt replay is inert; a new stale claim command cannot mutate newer work.
    assert c.finish(captured,error='synthetic unavailable').replayed
    with pytest.raises(PartitionConflict):
        c.apply('stale',{},lambda tx:tx.finish_job('j',captured['generation'],captured['revision'],captured['claim_token'],status='failed'))
    c.finish(newer,assets=[])


def test_rollback_rehydrates_only_current_phase2_domains(setup):
    c,store,state=setup;activate(c)
    assert c.rollback(2,writers_drained=True)['payload']==state
    assert store.load()==state
    assert c.read_migration()['stage']=='verified'
    with pytest.raises(PartitionConflict):c.create_job('s','chunk_s_2','after-rollback')


def test_snapshot_reconciliation_preserves_independent_core_changes(setup):
    c,store,_=setup;activate(c);baseline=store.load()
    other=PostgresStateStore(c._database_url,c._workspace_key);other.load()
    first=deepcopy(baseline);first['sources'][0]['title']='Changed'
    second=deepcopy(baseline);second['libraries'][0]['name']='Other'
    store.save(first)
    with pytest.raises(StaleStateWriteError):other.save(second)
    from app.persistence.reconciliation import merge_state_snapshots
    latest=other.load();merged=merge_state_snapshots(baseline,second,latest)
    other.save(merged)
    assert core(c)['payload']['sources'][0]['title']=='Changed'
    assert core(c)['payload']['libraries'][0]['name']=='Other'


@pytest.fixture
def api(setup,tmp_path,monkeypatch):
    import os
    monkeypatch.setenv('KNOWLEDGE_ENGINE_PERSISTENCE_MODE','local')
    monkeypatch.setenv('KNOWLEDGE_ENGINE_STORAGE',str(tmp_path))
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    monkeypatch.delenv('GEMINI_FREE_TIER_CONFIRMED',raising=False)
    from app.main import app
    from app.db import mock_data as db
    from app.db import persistence as persistence
    from app.persistence import factory
    from app.services import partition_authority as authority
    from fastapi.testclient import TestClient
    c,store,state=setup
    root=persistence.STORAGE_ROOT
    chunks=root/'chunks'/'s.json';chunks.parent.mkdir(parents=True,exist_ok=True)
    chunks.write_text(json.dumps([{'id':f'chunk_s_{i}','source_id':'s','text':'Use synthetic fixtures.',
                                  'chunk_index':i,'chapter_or_section':'Synthetic'} for i in (1,2)]))
    source_file=root/'s.txt';source_file.write_text('Use synthetic fixtures.')
    state['sources'][0].update(chunks_path=str(chunks),file_path=str(source_file),file_type='.txt',file_name='s.txt')
    store.save(state)
    for name in ('libraries','sources','extraction_jobs','knowledge_assets','outputs'):
        getattr(db,name)[:]=deepcopy(state.get(name,[]))
    monkeypatch.setattr(factory,'_state_store',store)
    monkeypatch.setattr(factory,'_phase2_coordinator',c)
    monkeypatch.setattr(factory,'PERSISTENCE_MODE','hosted')
    monkeypatch.setattr(authority,'PERSISTENCE_MODE','hosted')
    monkeypatch.setattr(persistence,'PERSISTENCE_MODE','hosted')
    # No cloud artifacts or actual provider calls: artifacts are private local fixtures.
    with TestClient(app) as client:
        yield client,c,store,state


def test_api_parity_preparing_verified_active_and_manual_completion(api):
    client,c,store,state=api
    paths=['/sources/s','/sources/s/summary','/sources/s/status','/sources/s/interpretation','/knowledge-extractions/j']
    def snapshot():
        results=[]
        for path in paths:
            response=client.get(path)
            assert response.status_code==200,(path,response.text)
            results.append(response.json())
        return results
    before=snapshot()
    c.prepare(2,'migration');c.backfill(2);c.verify(2)
    assert snapshot()==before
    c.cutover(2,writers_drained=True);store.load()
    assert snapshot()==before
    submitted={'assets':[{'asset_type':'principle','source_id':'s','chunk_id':'chunk_s_1',
                         'title':'Synthetic','what_it_says':'Use synthetic fixtures.',
                         'evidence':'Use synthetic fixtures.','keywords':['fixtures']}]}
    response=client.post('/knowledge-extractions/j/results',json=submitted)
    assert response.status_code==200,response.text
    assert response.json()['job']['status']=='completed'
    assert client.get('/sources/s/summary').json()['completed_parts']==1
    assert client.get('/sources/s/interpretation').json()['completed_chunks']==1
    assert 'extraction_jobs' not in core(c)['payload']
    assert len(core(c)['payload']['knowledge_assets'])==2


def test_api_synthetic_interpretation_no_full_snapshot_for_claim_or_final_status(api,monkeypatch):
    from types import SimpleNamespace
    from app.services import gemini_knowledge_extraction as gemini
    client,c,store,state=api;activate(c,2);store.load()
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-key')
    calls=[]
    def fake(**kwargs):
        calls.append(kwargs['request']['chunk_id'])
        return SimpleNamespace(output_text=json.dumps({'assets':[]}),id='synthetic')
    monkeypatch.setattr(gemini,'generate_structured_interaction',fake)
    before=core(c)['revision']
    result=client.post('/sources/s/interpret?max_chunks=2')
    assert result.status_code==200,result.text
    assert result.json()['processed_this_run']==2
    assert calls==['chunk_s_1','chunk_s_2']
    assert core(c)['revision']==before+2  # One asset-completion core write per chunk only.
    assert client.get('/sources/s/summary').json()['completed_parts']==2
    assert core(c)['payload']['knowledge_assets'][0]['active'] is False


def test_api_independent_requests_can_reach_synthetic_provider_concurrently(api,monkeypatch):
    from threading import Barrier
    from types import SimpleNamespace
    from app.services import gemini_knowledge_extraction as gemini
    client,c,store,_=api;activate(c,2);store.load()
    c.create_job('s','chunk_s_2','j2')
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-key')
    barrier=Barrier(2)
    def fake(**kwargs):
        barrier.wait(timeout=10)
        return SimpleNamespace(output_text='{"assets":[]}',id='synthetic')
    monkeypatch.setattr(gemini,'generate_structured_interaction',fake)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda jid:client.post('/knowledge-extractions/'+jid+'/run'),['j','j2']))
    assert [r.status_code for r in responses]==[200,200],[r.text for r in responses]
    assert [j['status'] for j in c.scoped(['s'])['extraction_jobs']]==['completed','completed']


def test_api_interruption_resume_and_recovery(api,monkeypatch):
    from fastapi import HTTPException
    from types import SimpleNamespace
    from app.services import gemini_knowledge_extraction as gemini
    client,c,store,_=api;activate(c,2);store.load()
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-key')
    def unavailable(**kwargs):raise HTTPException(503,'synthetic',headers={'X-KE-Interruption-Category':'ai_unavailable'})
    monkeypatch.setattr(gemini,'generate_structured_interaction',unavailable)
    result=client.post('/sources/s/interpret?max_chunks=1')
    assert result.status_code==200,result.text
    assert result.json()['interruption_category']=='ai_unavailable'
    assert client.get('/knowledge-extractions/j').json()['status']=='failed'
    assert client.post('/knowledge-extractions/j/recover').status_code==200
    monkeypatch.setattr(gemini,'generate_structured_interaction',lambda **kw:SimpleNamespace(output_text='{"assets":[]}',id='fixture'))
    result=client.post('/sources/s/interpret?max_chunks=1')
    assert result.status_code==200,result.text
    assert result.json()['processed_this_run']==1


def test_api_deletion_durable_before_artifact_cleanup(api,monkeypatch):
    from app.routers import control
    client,c,store,_=api;activate(c,2);store.load()
    original=control._artifact_store.remove
    observations=[]
    def remove(path):
        observations.append(c.read_source('s')['deleted'])
        assert all(s['id']!='s' for s in core(c)['payload']['sources'])
        return original(path)
    monkeypatch.setattr(control._artifact_store,'remove',remove)
    result=client.delete('/sources/s')
    assert result.status_code==200,result.text
    assert observations and all(observations)
    assert client.get('/sources/s').status_code==404
    assert c.read_source('s')['deleted']


def test_fixture_measurements(api,monkeypatch):
    from app.persistence.partitions import PartitionTransaction
    client,c,store,state=api
    big=deepcopy(state);big['knowledge_assets'][0]['content']='x'*500000
    store.save(big)
    before_bytes=len(json.dumps(big,ensure_ascii=False,separators=(',',':')).encode())
    activate(c,3);store.load()
    after_bytes=len(json.dumps(core(c)['payload'],ensure_ascii=False,separators=(',',':')).encode())
    stats={'queries':0,'transactions':0,'jsonb_write_bytes':0,'response_bytes':0,'core_writes':0,'core_write_bytes':0}
    original=PartitionTransaction._all
    from contextlib import contextmanager
    original_transaction=c.transaction
    @contextmanager
    def measured_transaction(*args,**kwargs):
        stats['transactions']+=1
        with original_transaction(*args,**kwargs) as tx: yield tx
    monkeypatch.setattr(c,'transaction',measured_transaction)
    def measured(tx,query,params=()):
        stats['queries']+=1
        if query.lstrip().startswith(('INSERT','UPDATE')):
            sizes=[len(json.dumps(p.obj,ensure_ascii=False,separators=(',',':')).encode()) for p in params if isinstance(p,Jsonb)]
            stats['jsonb_write_bytes']+=sum(sizes)
            if query.startswith('UPDATE knowledge_engine.state_snapshots'):
                stats['core_writes']+=1;stats['core_write_bytes']+=sum(sizes)
        rows=original(tx,query,params)
        stats['response_bytes']+=len(json.dumps(rows,default=str,separators=(',',':')).encode())
        return rows
    monkeypatch.setattr(PartitionTransaction,'_all',measured)
    def observe(fn):
        for key in stats:stats[key]=0
        started=time.perf_counter();result=fn()
        return result,dict(stats,latency_ms=(time.perf_counter()-started)*1000)
    captured,claim_stats=observe(lambda:claim(c))
    _,finish_stats=observe(lambda:c.finish(captured,assets=[]))
    summaries=[]
    for _ in range(12):
        response,sample=observe(lambda:client.get('/sources/s/summary'))
        assert response.status_code==200,response.text
        summaries.append(sample)
    latencies=sorted(s['latency_ms'] for s in summaries)
    measurements={'fixture_core_utf8_before':before_bytes,'fixture_core_utf8_after':after_bytes,
                  'claim':claim_stats,'completion':finish_stats,
                  'summary':{'queries':summaries[0]['queries'],'transactions':summaries[0]['transactions'],'response_bytes':summaries[0]['response_bytes'],
                             'median_ms':latencies[len(latencies)//2],'p95_ms':latencies[-1]},
                  'remaining_core_writes_per_chunk':1}
    from types import SimpleNamespace
    from app.services import gemini_knowledge_extraction as gemini
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-key')
    monkeypatch.setattr(gemini,'generate_structured_interaction',lambda **kw:SimpleNamespace(output_text='{"assets":[]}',id='synthetic'))
    response,whole=observe(lambda:client.post('/sources/s/interpret?max_chunks=1'))
    assert response.status_code==200,response.text
    assert response.json()['processed_this_run']==1
    measurements['whole_interpretation']=whole
    status_samples=[]
    for _ in range(12):
        response,sample=observe(lambda:client.get('/sources/s/status'))
        assert response.status_code==200,response.text
        status_samples.append(sample)
    status_latencies=sorted(s['latency_ms'] for s in status_samples)
    measurements['status']={'queries':status_samples[0]['queries'],'transactions':status_samples[0]['transactions'],
                            'response_bytes':status_samples[0]['response_bytes'],
                            'median_ms':status_latencies[len(status_latencies)//2],'p95_ms':status_latencies[-1]}
    replacement=c.create_job('s','chunk_s_2','replacement',reprocess=True)
    captured2=claim(c,'replacement','reconciliation')
    original_cas=c._cas
    attempts=[]
    def stale_once(tx,payload,revision):
        attempts.append(True)
        return original_cas(tx,payload,revision-1 if len(attempts)==1 else revision)
    monkeypatch.setattr(c,'_cas',stale_once)
    _,reconciled=observe(lambda:c.finish(captured2,assets=[]))
    measurements['reconciliation']=reconciled
    # Exercise actual legacy API claim/completion on an isolated workspace clone,
    # not an estimated before value. Its provider is the same synthetic fixture.
    from app.persistence import factory
    from app.db import mock_data as db
    legacy=PostgresStateStore(c._database_url,'legacy-measure-'+uuid4().hex)
    legacy.load();legacy.save(deepcopy(big))
    legacy_writes=[];legacy_save=legacy.save
    def tracked_legacy_save(payload):
        legacy_writes.append(len(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()))
        return legacy_save(payload)
    with monkeypatch.context() as patch:
        patch.setattr(factory,'_state_store',legacy)
        patch.setattr(legacy,'save',tracked_legacy_save)
        for name in ('libraries','sources','extraction_jobs','knowledge_assets','outputs'):
            getattr(db,name)[:]=deepcopy(big.get(name,[]))
        legacy_latencies=[];legacy_query_counts=[]
        for _ in range(12):
            count_before=stats['queries']
            started=time.perf_counter();summary_response=client.get('/sources/s/summary')
            assert summary_response.status_code==200,summary_response.text
            legacy_latencies.append((time.perf_counter()-started)*1000)
            legacy_query_counts.append(stats['queries']-count_before)
        legacy_response=client.post('/knowledge-extractions/j/run')
        assert legacy_response.status_code==200,legacy_response.text
    assert len(legacy_writes)==2
    measurements['legacy_claim_core_write_bytes']=legacy_writes[0]
    measurements['legacy_completion_core_write_bytes']=legacy_writes[1]
    measurements['legacy_claim_completion_transactions']=2
    legacy_latencies.sort()
    measurements['legacy_summary']={'queries':legacy_query_counts[0],'median_ms':legacy_latencies[len(legacy_latencies)//2],
                                    'p95_ms':legacy_latencies[-1]}
    restored=store.load()
    for name in ('libraries','sources','extraction_jobs','knowledge_assets','outputs'):
        getattr(db,name)[:]=deepcopy(restored.get(name,[]))
    assert len(attempts)==2 and reconciled['core_writes']==2
    assert claim_stats['core_writes']==0 and finish_stats['core_writes']==1
    assert after_bytes<before_bytes
    Path('/tmp/ke-phase2-measurements.json').write_text(json.dumps(measurements,indent=2))


@pytest.mark.parametrize('field',['ordinal','created_at','generation','metadata'])
def test_exact_job_verification_rejects_relational_drift(setup,field):
    c,_,_=setup;c.prepare(1,'migration');c.backfill(1)
    with c.transaction() as tx:
        tx.connection.execute('SET LOCAL session_replication_role = replica')
        value={'ordinal':9,'created_at':'2026-10-17T00:00:00Z','generation':3,'metadata':Jsonb({'provider':'wrong'})}[field]
        tx.connection.execute(sql.SQL('UPDATE knowledge_engine.partition_jobs SET {}=%s WHERE workspace_key=%s').format(sql.Identifier(field)),
                              (value,tx.workspace))
    with pytest.raises(PartitionConflict):c.verify(1)


def test_pending_request_cannot_create_job_after_same_id_rechunk(setup):
    c,store,_=setup;activate(c);baseline=store.load();proposed=deepcopy(baseline)
    proposed['sources'][0]['chunks_path']='chunks/new.json'
    c.save_core(baseline,proposed,2)
    with pytest.raises(PartitionConflict):
        c.create_job('s','chunk_s_2','stale',expected_generation=1)


def test_completion_only_reconciles_persistence_and_never_reexecutes_provider(api,monkeypatch):
    from types import SimpleNamespace
    from app.services import gemini_knowledge_extraction as gemini
    client,c,store,_=api;activate(c,2);store.load()
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-key')
    providers=[]
    monkeypatch.setattr(gemini,'generate_structured_interaction',lambda **kw:
                        (providers.append('called') or SimpleNamespace(output_text='{"assets":[]}',id='fixture')))
    original=c._cas;attempts=[]
    def conflict(tx,payload,revision):
        attempts.append(True)
        if len(attempts)==1:raise StaleStateWriteError('synthetic stale core')
        return original(tx,payload,revision)
    monkeypatch.setattr(c,'_cas',conflict)
    result=client.post('/knowledge-extractions/j/run')
    assert result.status_code==200,result.text
    assert len(providers)==1 and len(attempts)==2


def test_completion_receipt_recovers_uncertain_ack_without_provider_repeat(setup,monkeypatch):
    c,_,_=setup;activate(c);captured=claim(c)
    original=c.apply
    def lost(*args,**kwargs):
        original(*args,**kwargs)
        raise HostedStateStoreError('synthetic lost acknowledgement')
    monkeypatch.setattr(c,'apply',lost)
    result=c.finish(captured,assets=[])
    assert result.replayed and c.read_job('j')['status']=='completed'
    assert core(c)['revision']==3


def test_live_delete_can_commit_while_provider_waits(api,monkeypatch):
    from threading import Event
    from types import SimpleNamespace
    from app.services import gemini_knowledge_extraction as gemini
    client,c,store,_=api;activate(c,2);store.load()
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-key')
    entered,release=Event(),Event()
    def fake(**kw):
        entered.set();assert release.wait(10)
        return SimpleNamespace(output_text='{"assets":[]}',id='fixture')
    monkeypatch.setattr(gemini,'generate_structured_interaction',fake)
    with ThreadPoolExecutor(max_workers=2) as pool:
        running=pool.submit(client.post,'/knowledge-extractions/j/run')
        assert entered.wait(10)
        deleted=client.delete('/sources/s')
        assert deleted.status_code==200,deleted.text
        release.set()
        result=running.result(timeout=10)
    assert result.status_code>=400
    assert c.read_source('s')['deleted']
    assert core(c)['payload']['knowledge_assets']==[]


def test_core_cached_after_completion_allows_later_delete(api):
    client,c,store,_=api;activate(c,2);store.load()
    completed=client.post('/knowledge-extractions/j/results',json={'assets':[]})
    assert completed.status_code==200,completed.text
    deleted=client.delete('/sources/s')
    assert deleted.status_code==200,deleted.text
    assert c.read_source('s')['deleted']


def test_cutover_during_legacy_preparation_cannot_dispatch_without_claim(api,monkeypatch):
    from types import SimpleNamespace
    from app.services import gemini_knowledge_extraction as gemini
    client,c,store,_=api
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-key')
    original=gemini.mark_extraction_job_running
    providers=[]
    def transition(*args,**kwargs):
        result=original(*args,**kwargs)
        # Coalesced legacy preparation has not yet persisted its running state.
        activate(c,2);store.load()
        return result
    monkeypatch.setattr(gemini,'mark_extraction_job_running',transition)
    monkeypatch.setattr(gemini,'generate_structured_interaction',lambda **kw:
                        (providers.append(True) or SimpleNamespace(output_text='{"assets":[]}')))
    response=client.post('/sources/s/interpret?max_chunks=1')
    assert response.status_code>=400
    assert providers==[] and c.read_job('j')['status']=='pending_ai'


def test_rollback_keeps_old_generation_job_provenance(setup):
    c,store,_=setup;activate(c);captured=claim(c);c.finish(captured,assets=[])
    before=store.load();changed=deepcopy(before)
    changed['sources'][0]['chunks_path']='chunks/next.json'
    revision,_=c.save_core(before,changed,3)
    assert c.scoped(['s'])['extraction_jobs']==[]
    assert c.history_jobs('s')[0]['id']=='j'
    result=c.rollback(revision,writers_drained=True)
    assert result['payload']['extraction_jobs'][0]['id']=='j'
    assert result['payload']['extraction_jobs'][0]['status']=='completed'


def test_rollback_history_can_migrate_verify_and_recutover(setup):
    c,store,_=setup
    activate(c)
    c.finish(claim(c),assets=[])
    before=store.load();changed=deepcopy(before)
    changed['sources'][0]['chunks_path']='chunks/next.json'
    revision,_=c.save_core(before,changed,core(c)['revision'])
    receipt=c.read_operation('finish:token')
    restored=c.rollback(revision,writers_drained=True)['payload']
    assert restored['sources'][0]['generation']==2
    assert restored['extraction_jobs'][0]['generation']==1

    assert c.read_migration()['stage']=='verified'
    prior=c.read_migration()
    assert prior['source_snapshot_revision']==1 and prior['cutover_revision']==2
    assert prior['verified_at'] is not None
    assert c.restart_after_rollback(core(c)['revision'],'fresh-after-rollback',writers_drained=True)=={
        'stage':'preparing','checkpoint':{}}
    rollback_revision=core(c)['revision']
    current=c.read_migration()
    assert current['migration_id']=='fresh-after-rollback'
    assert current['source_snapshot_revision']==rollback_revision
    assert current['verified_at'] is None and current['cutover_revision'] is None
    history=c.read_migration_history()
    assert len(history)==1
    assert history[0]['migration_id']=='migration'
    assert history[0]['source_snapshot_revision']==1
    assert history[0]['stage']=='verified' and history[0]['cutover_revision']==2
    with pytest.raises(PartitionConflict):
        with c.transaction() as tx:
            tx.connection.execute("UPDATE knowledge_engine.partition_migration_attempt_history "
                                  "SET source_snapshot_revision=99 WHERE workspace_key=%s AND migration_id='migration'",
                                  (tx.workspace,))
    c.backfill(rollback_revision)
    c.backfill(rollback_revision)  # Checkpoint replay preserves retained generations.
    c.verify(rollback_revision)
    assert c.read_job('j')['generation']==1
    cutover=c.cutover(rollback_revision,writers_drained=True)
    assert c.history_jobs('s')[0]['id']=='j'
    assert c.read_job('j')['generation']==1
    assert c.scoped(['s'])['extraction_jobs']==[]
    again=c.rollback(cutover['revision'],writers_drained=True)['payload']
    assert again['sources'][0]['generation']==2
    assert again['extraction_jobs'][0]['generation']==1
    assert c.read_operation('finish:token')==receipt


def test_restart_requires_verified_rollback_legacy_authority_and_drained_writers(setup):
    c,store,_=setup
    activate(c)
    with pytest.raises(PartitionConflict):c.restart_after_rollback(2,'unsafe',writers_drained=True)
    c.rollback(2,writers_drained=True)
    with pytest.raises(PartitionConflict):c.restart_after_rollback(3,'unsafe')
    c.restart_after_rollback(3,'fresh',writers_drained=True)
    assert c.read_migration()['stage']=='preparing'
    with pytest.raises(PartitionConflict):c.restart_after_rollback(3,'second',writers_drained=True)
    baseline=store.load();changed=deepcopy(baseline)
    changed['libraries'][0]['name']='Core revision changed'
    with c.transaction() as tx:
        current=c._core(tx,3)['payload']
        current['libraries'][0]['name']='Core revision changed'
        c._cas(tx,current,3)
    with pytest.raises((PartitionConflict,StaleStateWriteError)):c.backfill(3)
    assert c.read_migration()['stage']=='preparing'


@pytest.mark.parametrize('status',['pending_ai','running','completed','failed'])
def test_migrated_historical_jobs_are_readable_but_never_live(setup,status):
    c,store,state=setup
    state['sources'][0]['generation']=2
    old=state['extraction_jobs'][0]
    old.update(generation=1,status=status)
    if status=='running':old['started_at']='2026-10-16T00:00:01+00:00'
    if status=='completed':old['completed_at']='2026-10-16T00:00:02+00:00'
    store.save(state)
    c.prepare(2,'history');c.backfill(2)
    historical=c.read_job('j')
    assert historical['generation']==1 and historical['api_payload']==old

    # Even a preparing migration's exception is INSERT-only, never a license
    # to update/reanimate history or bypass normal transition guards.
    with pytest.raises(PartitionConflict):
        with c.transaction() as tx:
            tx.connection.execute("SELECT set_config('knowledge_engine.backfill','on',true)")
            tx.connection.execute("SELECT set_config('knowledge_engine.backfill_workspace',%s,true)",(tx.workspace,))
            tx.connection.execute("UPDATE knowledge_engine.partition_jobs SET revision=revision+1 WHERE workspace_key=%s AND job_id='j'",(tx.workspace,))
    c.verify(2)
    # A historical running record is not an in-flight current-generation writer.
    c.cutover(2,writers_drained=True)
    assert c.history_jobs('s')==[old]
    assert c.scoped(['s'])['extraction_jobs']==[]
    assert c.read_job('j')['generation']==1
    for operation in (
        lambda:c.claim('j','synthetic','fixture','old-claim','old-token'),
        lambda:c.recover('j'),
        lambda:c.finish(dict(historical,claim_token='old-token'),assets=[]),
        lambda:c.finish(dict(historical,claim_token='old-token'),error='stale'),
    ):
        with pytest.raises(PartitionConflict):operation()
    # Exercise direct store and SQL paths as well as the coordinator.
    for terminal in ('completed','failed'):
        with pytest.raises(PartitionConflict):
            c.apply('old-'+terminal,{},lambda tx:tx.finish_job('j',1,historical['revision'],'old-token',status=terminal))
    for next_status in ('running','completed','failed','pending_ai'):
        with pytest.raises(PartitionConflict):
            with c.transaction() as tx:
                tx.connection.execute("UPDATE knowledge_engine.partition_jobs SET status=%s,revision=revision+1,"
                                      "claim_token=CASE WHEN %s='running' THEN 'old-token' END,started_at=now(),"
                                      "completed_at=CASE WHEN %s='completed' THEN now() END "
                                      "WHERE workspace_key=%s AND job_id='j'",(next_status,next_status,next_status,tx.workspace))
    with pytest.raises(PartitionConflict):
        with c.transaction() as tx:
            tx.connection.execute("UPDATE knowledge_engine.partition_jobs SET generation=2,revision=revision+1 "
                                  "WHERE workspace_key=%s AND job_id='j'",(tx.workspace,))
    assert c.read_job('j')==historical
    assert c.read_operation('old-claim') is None
    assert c.read_operation('finish:old-token') is None

    # Same chunk in the current generation is new work, not a replacement of
    # historical progress. Ordinary creation still enforces the current fence.
    for generation in (1,3):
        with pytest.raises(PartitionConflict):
            c.apply('wrong-create-'+str(generation),{},lambda tx:tx.create_job('wrong','s','chunk_s_1',generation,1))
    current=c.create_job('s','chunk_s_1','current')
    assert c.read_job(current['id'])['generation']==2
    captured=claim(c,'current','current-token')
    with pytest.raises(PartitionConflict):claim(c,'current','duplicate')
    c.finish(captured,error='synthetic interruption')
    c.recover('current')
    recovered=claim(c,'current','recovered-token')
    c.finish(recovered,assets=[])
    assert c.finish(recovered,assets=[]).replayed
    assert c.finish(captured,error='synthetic interruption').replayed
    assert c.read_job('current')['status']=='completed'
    assert c.read_operation('finish:current-token')['result']['generation']==2
    assert [j['id'] for j in c.scoped(['s'])['extraction_jobs']]==['current']
    assert c.read_source('s')['interpretation_status']=='knowledge_interpreting'
    assert core(c)['payload']['knowledge_assets'][0]['active'] is False


def test_backfill_missing_legacy_job_generation_means_original_generation_one(setup):
    c,store,state=setup
    state['sources'][0]['generation']=2
    store.save(state)
    c.prepare(2,'legacy-history');c.backfill(2);c.verify(2)
    assert c.read_job('j')['generation']==1
    assert 'generation' not in c.read_job('j')['api_payload']
    c.cutover(2,writers_drained=True)
    assert c.scoped(['s'])['extraction_jobs']==[]


def test_future_job_generation_refuses_backfill_atomically(setup):
    c,store,state=setup
    state['sources'][0]['generation']=2
    state['extraction_jobs'][0]['generation']=3
    store.save(state);c.prepare(2,'future')
    before=core(c)
    with pytest.raises(PartitionConflict,match='ahead of its source'):c.backfill(2)
    assert c.read_source('s') is None and c.read_job('j') is None
    assert c.read_migration()['checkpoint']=={}
    assert core(c)==before


@pytest.mark.parametrize('generation',[1,2,3])
def test_database_historical_insert_exception_requires_pinned_migration(setup,generation):
    c,store,state=setup
    state['sources'][0]['generation']=2
    state['extraction_jobs']=[]
    store.save(state);c.prepare(2,'insert-fence');c.backfill(2)
    def insert(*,backfill):
        with c.transaction() as tx:
            if backfill:
                tx.connection.execute("SELECT set_config('knowledge_engine.backfill','on',true)")
                tx.connection.execute("SELECT set_config('knowledge_engine.backfill_workspace',%s,true)",(tx.workspace,))
            tx.connection.execute("INSERT INTO knowledge_engine.partition_jobs "
                                  "(workspace_key,job_id,source_id,chunk_id,generation,extraction_version) "
                                  "VALUES (%s,%s,'s','chunk_s_1',%s,1)",(tx.workspace,'insert-'+str(generation),generation))
    if generation!=2:
        with pytest.raises(PartitionConflict):insert(backfill=False)
    if generation==3:
        with pytest.raises(PartitionConflict):insert(backfill=True)
        assert c.read_job('insert-3') is None
    else:
        insert(backfill=True)
        assert c.read_job('insert-'+str(generation))['generation']==generation


def test_backfill_insert_exception_cannot_bypass_current_job_transition_guard(setup):
    c,_,_=setup
    c.prepare(1,'insert-only');c.backfill(1)
    with pytest.raises(PartitionConflict):
        with c.transaction() as tx:
            tx.connection.execute("SELECT set_config('knowledge_engine.backfill','on',true)")
            tx.connection.execute("SELECT set_config('knowledge_engine.backfill_workspace',%s,true)",(tx.workspace,))
            tx.connection.execute("UPDATE knowledge_engine.partition_jobs SET status='completed',completed_at=now(),"
                                  "revision=revision+1 WHERE workspace_key=%s AND job_id='j'",(tx.workspace,))
    assert c.read_job('j')['status']=='pending_ai'


@pytest.mark.parametrize('invalidated',['verified','revision_drift'])
def test_historical_insert_exception_ends_with_preparing_revision(setup,invalidated):
    c,store,state=setup
    state['sources'][0]['generation']=2
    state['extraction_jobs']=[]
    store.save(state);c.prepare(2,'scoped-history');c.backfill(2)
    if invalidated=='verified':c.verify(2)
    else:store.save(state)
    with pytest.raises(PartitionConflict):
        with c.transaction() as tx:
            tx.connection.execute("SELECT set_config('knowledge_engine.backfill','on',true)")
            tx.connection.execute("SELECT set_config('knowledge_engine.backfill_workspace',%s,true)",(tx.workspace,))
            tx.connection.execute("INSERT INTO knowledge_engine.partition_jobs "
                                  "(workspace_key,job_id,source_id,chunk_id,generation,extraction_version) "
                                  "VALUES (%s,'expired-backfill','s','chunk_s_1',1,1)",(tx.workspace,))
    assert c.read_job('expired-backfill') is None


def test_current_progress_excludes_migrated_historical_completion(api):
    client,c,store,state=api
    state['sources'][0]['generation']=2
    state['extraction_jobs'][0].update(generation=1,status='completed',completed_at='2026-10-16T01:00:00Z')
    store.save(state);activate(c,3);store.load()
    summary=client.get('/sources/s/summary')
    assert summary.status_code==200,summary.text
    assert summary.json()['completed_parts']==0
    assert summary.json()['total_parts']==2
    assert summary.json()['file_replacement_allowed'] is False
    history=client.get('/knowledge-extractions/j')
    assert history.status_code==200,history.text


def test_core_and_narrow_lock_order_is_core_then_source_then_job(setup,monkeypatch):
    from app.persistence.partitions import PartitionTransaction
    c,_,_=setup;activate(c);captured=claim(c)
    statements=[];original=PartitionTransaction._all
    def tracked(tx,query,params=()):
        statements.append(query)
        return original(tx,query,params)
    monkeypatch.setattr(PartitionTransaction,'_all',tracked)
    c.finish(captured,assets=[])
    core_lock=next(i for i,q in enumerate(statements) if 'FROM knowledge_engine.state_snapshots' in q and 'FOR UPDATE' in q)
    source_lock=next(i for i,q in enumerate(statements) if 'FROM knowledge_engine.partition_sources' in q and 'FOR UPDATE' in q)
    job_lock=next(i for i,q in enumerate(statements) if 'FROM knowledge_engine.partition_jobs' in q and 'FOR UPDATE' in q)
    assert core_lock<source_lock<job_lock


@pytest.mark.parametrize('status',['failed','completed','running'])
def test_backfill_preserves_existing_status_metadata_and_timestamp_spelling(setup,status):
    c,store,state=setup
    job=state['extraction_jobs'][0]
    job.update(status=status,provider='gemini',model='synthetic',started_at='2026-10-16T00:01:00Z')
    if status=='completed':job.update(completed_at='2026-10-16T00:02:00Z',model_response_id='response',asset_count=1)
    if status=='failed':job['error']='synthetic interruption'
    store.save(state);c.prepare(2,'migration');c.backfill(2);c.verify(2)
    if status=='running':
        with pytest.raises(PartitionConflict):c.cutover(2,writers_drained=True)
    else:
        c.cutover(2,writers_drained=True)
        assert c.scoped(['s'])['extraction_jobs']==state['extraction_jobs']


def test_historical_chunk_read_cannot_substitute_new_generation_text(api):
    client,c,store,_=api;activate(c,2);store.load()
    captured=claim(c);c.finish(captured,assets=[])
    baseline=store.load();changed=deepcopy(baseline)
    changed['sources'][0]['chunks_path']='chunks/replacement.json'
    c.save_core(baseline,changed,4);store.load()
    assert client.get('/knowledge-extractions/j').status_code==200
    assert client.get('/knowledge-extractions/j/chunk').status_code==400


def test_forged_captured_identity_does_not_mutate_core(setup):
    c,_,_=setup;activate(c);captured=claim(c);before=core(c)
    forged=dict(captured,source_id='other')
    with pytest.raises(PartitionConflict):c.finish(forged,assets=[])
    assert core(c)==before and c.read_job('j')['status']=='running'


def test_superseded_failed_job_cannot_recover_over_later_completed_extraction(setup):
    c,store,state=setup
    old=state['extraction_jobs'][0];old.update(status='failed',error='old failure')
    newer=dict(old,id='newer',status='completed',error=None,completed_at='2026-10-16T01:00:00Z',extraction_version=2)
    state['extraction_jobs'].append(newer)
    store.save(state);activate(c,2)
    with pytest.raises(PartitionConflict):c.recover('j')
    assert c.read_job('j')['status']=='failed'


def test_backfill_exception_is_scoped_to_its_pinned_workspace(setup):
    c,_,_=setup;c.prepare(1,'migration')
    other=Phase2Coordinator(c._database_url,'other-'+uuid4().hex)
    other.apply('source',{},lambda tx:tx.create_source('s'))
    with pytest.raises(PartitionConflict):
        with c.transaction() as tx:
            tx.connection.execute("SELECT set_config('knowledge_engine.backfill','on',true)")
            tx.connection.execute("SELECT set_config('knowledge_engine.backfill_workspace',%s,true)",(tx.workspace,))
            tx.connection.execute("INSERT INTO knowledge_engine.partition_jobs "
                                  "(workspace_key,job_id,source_id,chunk_id,generation,extraction_version,status,completed_at) "
                                  "VALUES (%s,'invalid','s','c',1,1,'completed',now())",(other._workspace_key,))


def test_source_api_projection_cannot_become_independent_status_authority(setup):
    c,_,_=setup;activate(c)
    c.apply('source-status',{},lambda tx:tx.update_source('s',1,1,status='knowledge_interpreting',stopped_reason='fixture'))
    row=c.read_source('s')
    assert row['api_payload']['processing_status']==row['interpretation_status']=='knowledge_interpreting'
    with c.transaction() as tx:
        tx.connection.execute("UPDATE knowledge_engine.partition_sources SET api_payload=%s,revision=revision+1 "
                              'WHERE workspace_key=%s',(Jsonb({'processing_status':'wrong','stopped_reason':'wrong'}),tx.workspace))
    row=c.read_source('s')
    assert row['api_payload']['stopped_reason']==row['stopped_reason']=='fixture'


def test_completion_commits_source_outcome_without_separate_finalization(setup):
    c,_,_=setup;activate(c)
    first=claim(c);c.finish(first,assets=[])
    assert c.read_source('s')['interpretation_status']=='knowledge_interpreting'
    c.create_job('s','chunk_s_2','second')
    second=claim(c,'second','second-token');c.finish(second,assets=[])
    assert c.read_source('s')['interpretation_status']=='knowledge_interpreted'
    assert c.scoped(['s'])['sources'][0]['processing_status']=='knowledge_interpreted'


def test_existing_worker_discovers_cutover_without_manual_store_reload(api):
    client,c,store,state=api
    assert not store.phase2
    activate(c,2)
    response=client.get('/knowledge-extractions/j')
    assert response.status_code==200,response.text
    assert store.phase2
    assert response.json()==state['extraction_jobs'][0]


def test_existing_worker_discovers_rehydrated_rollback_without_stale_job_cache(api):
    client,c,store,state=api;activate(c,2)
    assert client.get('/knowledge-extractions/j').status_code==200
    assert store.phase2
    c.rollback(3,writers_drained=True)
    response=client.get('/knowledge-extractions/j')
    assert response.status_code==200,response.text
    assert not store.phase2 and response.json()==state['extraction_jobs'][0]
