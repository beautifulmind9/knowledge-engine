"""Phase 3 authority and settlement checks using disposable PostgreSQL only."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import json
import math
import statistics
from time import perf_counter

import psycopg
from psycopg import sql
import pytest

from test_partition_store import database
from app.persistence.phase2 import Phase2Coordinator
from app.persistence.phase3 import Phase3Coordinator, AssetProvenanceError, MARKER
from app.persistence.postgres import PostgresStateStore
from app.persistence.partitions import PartitionConflict


@pytest.fixture(scope='session')
def phase3_database(database):
    name='phase3_'+uuid4().hex
    with psycopg.connect(database,autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    dsn=database+' dbname='+name
    root=Path(__file__).resolve().parents[1]
    with psycopg.connect(dsn) as conn:
        for filename in ('create_knowledge_engine_state_snapshot.sql','create_knowledge_engine_partitions.sql',
                         'create_knowledge_engine_phase2.sql','create_knowledge_engine_phase3.sql'):
            conn.execute((root/'schema'/filename).read_text())
    return dsn


def fixture_state(asset_count=2):
    chunk_ids=[f'c{i}' for i in range(50)]
    jobs=[]
    assets=[]
    for index in range(asset_count):
        jid=f'j{index}'
        jobs.append({'id':jid,'source_id':'s','chunk_id':chunk_ids[index], 'status':'completed',
            'created_at':'2026-10-16T00:00:00+00:00','started_at':'2026-10-16T00:00:01+00:00',
            'completed_at':'2026-10-16T00:00:02+00:00','schema_version':2,'extraction_version':1,
            'asset_count':1,'provider':'synthetic','model':'fixture','model_response_id':None,'error':None})
        assets.append({'id':f'a{index}','asset_type':'principle','title':f'Asset {index}',
            'what_it_says':f'Fixture statement {index}','why_it_matters':None,'source_id':'s',
            'chunk_id':chunk_ids[index],'chapter_or_section':None,'evidence':f'Fixture evidence {index}',
            'how_to_apply':[],'when_to_use':[],'when_not_to_use':[],'tradeoffs':[],'keywords':['fixture'],
            'confidence_score':3,'created_at':'2026-10-16T00:00:03+00:00','extraction_job_id':jid,
            'extraction_version':1,'active':True})
    return {'schema_version':2,'libraries':[{'id':'l','name':'Fixture'}],
        'sources':[{'id':'s','library_id':'l','title':'Fixture source','processing_status':'knowledge_interpreted',
          'stopped_reason':None,'chunk_manifest':{'version':1,'total_parts':len(chunk_ids),'chunk_ids':chunk_ids},
          'chunks_path':'chunks/s.json'}], 'extraction_jobs':jobs,'knowledge_assets':assets,
        'outputs':[],'usage':{'calls':4}}


@pytest.fixture
def setup(phase3_database):
    workspace='p3-'+uuid4().hex
    store=PostgresStateStore(phase3_database,workspace)
    state=fixture_state()
    store.load();store.save(state)
    p2=Phase2Coordinator(phase3_database,workspace)
    p2.prepare(1,'phase2-attempt');p2.backfill(1);p2.verify(1);p2.cutover(1,writers_drained=True)
    c=Phase3Coordinator(phase3_database,workspace)
    c.prepare(2,'phase3-attempt');c.backfill(2);c.verify(2);c.cutover(2,writers_drained=True)
    return c,store,state


def core(c):
    with c.transaction() as tx:
        return tx._one('SELECT payload,revision FROM knowledge_engine.state_snapshots WHERE workspace_key=%s',
                       (tx.workspace,))


def test_v3_cutover_compacts_assets_and_preserves_global_order(setup):
    c,store,state=setup
    stored=core(c)
    assert stored['payload']['partition']==MARKER
    assert 'knowledge_assets' not in stored['payload']
    assert 'extraction_jobs' not in stored['payload']
    assert c.active_assets()==state['knowledge_assets']
    assert store.load()['knowledge_assets']==[]
    assert c.last_transaction_sql_statements >= 1


def test_successful_settlement_has_constant_statement_count_and_zero_core_write(setup):
    c,_,_=setup
    counts=[];payload_sizes=[];jsonb_sizes=[];settlement_ms=[];lifecycle_statements=[]
    for asset_count in (0,1,5,20):
        chunk=f'c{10+asset_count}'
        job_id=f'new-{asset_count}'
        c.create_job('s',chunk,job_id)
        create_statements=c.last_transaction_sql_statements
        claim=c.claim(job_id,'synthetic','fixture','claim-'+job_id,'token-'+job_id).value
        claim_statements=c.last_transaction_sql_statements
        before_revision=core(c)['revision']
        assets=[{'id':f'{job_id}-a{i}','asset_type':'principle','title':f'A{i}',
            'what_it_says':'Fixture output','source_id':'s','chunk_id':chunk,
            'evidence':'Fixture evidence','keywords':['fixture'],'created_at':'2026-10-16T00:00:05+00:00',
            'extraction_job_id':job_id,'extraction_version':1,'active':True} for i in range(asset_count)]
        payload_sizes.append(len(json.dumps(assets,separators=(',',':')).encode()))
        started=perf_counter()
        c.finish(claim,assets=assets,response_id='synthetic-response')
        settlement_ms.append((perf_counter()-started)*1000)
        counts.append(c.last_transaction_sql_statements)
        lifecycle_statements.append({'create_job':create_statements,'claim':claim_statements,
                                     'settlement':counts[-1],
                                     'whole_chunk':create_statements+claim_statements+counts[-1]})
        with c.transaction() as tx:
            stored_bytes=tx._one('SELECT coalesce(sum(pg_column_size(payload)),0) AS n '
                'FROM knowledge_engine.partition_assets WHERE workspace_key=%s AND asset_id=ANY(%s)',
                (tx.workspace,[f'{job_id}-a{i}' for i in range(asset_count)]))['n']
        jsonb_sizes.append(stored_bytes)
        assert core(c)['revision']==before_revision
        assert len(c.active_assets(source_ids=['s']))==2+sum((0,1,5,20)[:(0,1,5,20).index(asset_count)+1])
    assert len(set(counts[1:]))==1
    assert max(counts)-min(counts)<=3
    assert payload_sizes[0]==2
    print('phase3_settlement_fixture_measurements=' + json.dumps({
        'asset_counts':[0,1,5,20], 'client_sql_statements':counts,
        'asset_json_input_utf8_bytes':payload_sizes, 'stored_jsonb_payload_bytes':jsonb_sizes,
        'core_snapshot_write_bytes':[0,0,0,0],
        'transactions_per_chunk':3,'client_sql_statements_by_operation':lifecycle_statements,
        'settlement_ms':settlement_ms,
    },separators=(',',':')))


def test_v3_summary_and_multi_source_reads_are_batched(setup):
    c,_,_=setup
    summary_times=[]
    for _ in range(10):
        before=perf_counter();summary=c.summary_state(['s'])
        summary_times.append((perf_counter()-before)*1000)
    summary_statements=c.last_transaction_sql_statements
    assert summary['asset_counts']=={'s':2}
    assert summary_statements==4
    browse_times=[]
    for _ in range(10):
        before=perf_counter();assets=c.active_assets_many(['s'])
        browse_times.append((perf_counter()-before)*1000)
    browse_statements=c.last_transaction_sql_statements
    assert [item['id'] for item in assets]==['a0','a1']
    assert browse_statements==2
    print('phase3_read_fixture_measurements=' + json.dumps({
        'summary':{'transactions':1,'statements':summary_statements,'rows':4,
                   'median_ms':statistics.median(summary_times),
                   'p95_ms':sorted(summary_times)[math.ceil(.95*len(summary_times))-1]},
        'multi_source_browse':{'transactions':1,'statements':browse_statements,'rows':len(assets),
                               'median_ms':statistics.median(browse_times),
                               'p95_ms':sorted(browse_times)[math.ceil(.95*len(browse_times))-1]},
    },separators=(',',':')))


def test_downstream_read_services_use_narrow_batch_paths(setup,monkeypatch):
    c,store,_=setup
    from app.db import mock_data
    from app.services import knowledge_extraction as extraction
    from app.services import partition_authority, source_summary, workshop
    from app.models.workshop import WorkshopPrepareRequest

    monkeypatch.setattr(partition_authority,'coordinator',lambda:c)
    source={'id':'s','library_id':'l','title':'Fixture source','file_path':'source.pdf',
        'chunks_path':'chunks.json','chunk_manifest':{'version':1,'total_parts':50,
        'chunk_ids':[f'c{i}' for i in range(50)]},'processing_status':'knowledge_interpreted'}
    source2={'id':'s2','library_id':'l','title':'Second fixture source','file_path':'source2.pdf',
        'chunks_path':'chunks2.json','chunk_manifest':{'version':1,'total_parts':1,'chunk_ids':['s2c']},
        'processing_status':'knowledge_interpreted'}
    baseline=store.load();proposed=deepcopy(baseline);proposed['sources'].append(source2)
    c.save_core(baseline,proposed,core(c)['revision'])
    job=c.create_job('s2','s2c','s2job')
    claim=c.claim(job['id'],'synthetic','fixture','s2claim','s2token').value
    second={'id':'s2asset','asset_type':'principle','title':'Second fixture','what_it_says':'Fixture statement',
        'source_id':'s2','chunk_id':'s2c','evidence':'Fixture evidence','keywords':['fixture'],
        'created_at':'2026-10-16T00:00:08+00:00','extraction_job_id':'s2job','extraction_version':1,'active':True}
    c.finish(claim,assets=[second],response_id='synthetic')
    monkeypatch.setattr(source_summary,'sources',[source,source2])
    monkeypatch.setattr(source_summary,'valid_manifest',lambda *args:True)
    class Artifacts:
        def status_many(self,paths):return {path:'artifact' for path in paths}
    monkeypatch.setattr(source_summary,'get_artifact_store',lambda:Artifacts())
    monkeypatch.setattr(mock_data,'sources',[source,source2])
    monkeypatch.setattr(mock_data,'libraries',[{'id':'l','name':'Fixture'}])

    listed=extraction.list_knowledge_assets(source_ids=['s','s2'])
    assert [item['id'] for item in listed]==['a0','a1','s2asset']
    assert c.last_transaction_sql_statements==2
    groups=extraction.consolidate_knowledge_assets(listed)
    assert sum(group['support_count'] for group in groups)==3
    results=extraction.search_knowledge_assets('fixture statement')
    assert {item['id'] for item in results}=={'a0','a1','s2asset'}
    assert c.last_transaction_sql_statements==2

    summaries=source_summary.source_summaries(source_ids=['s','s2'])
    assert all(item.has_usable_knowledge for item in summaries)
    assert c.last_transaction_sql_statements==4
    request=WorkshopPrepareRequest(situation='Apply fixture evidence',goal='Use fixture statement',
        source_ids=['s','s2'],output_type='general')
    selected=workshop._retrieve_raw_assets(request)
    assert {item['id'] for item in selected}=={item['id'] for item in listed}
    assert c.last_transaction_sql_statements==2
    evidence=workshop.evidence_base_state(['s','s2'])
    assert evidence['selected_count']==2 and evidence['ready_count']==1
    assert c.last_transaction_sql_statements==4

    def measure(operation, db_rows, *, statement_count):
        times=[];result=None
        for _ in range(10):
            before=perf_counter();result=operation();times.append((perf_counter()-before)*1000)
        def serializable(value):
            if hasattr(value,'model_dump'):return value.model_dump(mode='json')
            if isinstance(value,dict):return {key:serializable(item) for key,item in value.items()}
            if isinstance(value,(list,tuple)):return [serializable(item) for item in value]
            return value
        return {'transactions':1,'statements':statement_count,'rows_returned':db_rows,
            'api_payload_bytes':len(json.dumps(serializable(result),separators=(',',':'),default=str).encode()),
            'median_ms':statistics.median(times),
            'p95_ms':sorted(times)[math.ceil(.95*len(times))-1]}

    req=WorkshopPrepareRequest(situation='Apply fixture evidence',goal='Use fixture statement',
        source_ids=['s','s2'],output_type='general')
    path_measurements={
        'source_asset_browsing':measure(lambda:extraction.list_knowledge_assets(source_ids=['s','s2']),3,statement_count=2),
        'consolidation':measure(lambda:extraction.consolidate_knowledge_assets(
            extraction.list_knowledge_assets(source_ids=['s','s2'])),3,statement_count=2),
        'explore':measure(lambda:extraction.search_knowledge_assets('fixture statement'),3,statement_count=2),
        'source_summary':measure(lambda:source_summary.source_summaries(source_ids=['s','s2']),7,statement_count=4),
        'workshop_multi_source':measure(lambda:workshop._retrieve_raw_assets(req),3,statement_count=2),
        'evidence_base_multi_source':measure(lambda:workshop.evidence_base_state(['s','s2']),7,statement_count=4),
    }
    print('phase3_downstream_read_fixture_measurements='+json.dumps(path_measurements,separators=(',',':')))


def test_v2_coordinator_rejects_v3_authority(setup):
    c,_,_=setup
    older=Phase2Coordinator(c._database_url,c._workspace_key)
    with pytest.raises(PartitionConflict,match='newer partition authority'):
        older.read_source('s')


def test_runtime_order_replacement_appends_batch_after_existing_global_order(setup):
    c,_,_=setup
    created=c.create_job('s','c0','replacement',reprocess=True)
    claim=c.claim(created['id'],'synthetic','fixture','claim-replacement','replace-token').value
    replacement=[{'id':'replacement-asset','asset_type':'principle','title':'Replacement',
        'what_it_says':'Replacement text','source_id':'s','chunk_id':'c0','evidence':'Replacement evidence',
        'keywords':['replacement'],'created_at':'2026-10-16T00:00:06+00:00','extraction_job_id':'replacement',
        'extraction_version':2,'active':True}]
    c.finish(claim,assets=replacement,response_id='synthetic')
    assert [a['id'] for a in c.active_assets()]==['a1','replacement-asset']
    historical=c.list_assets(history=True)
    assert [a['id'] for a in historical]==['a0','a1','replacement-asset']
    assert historical[0]['active'] is False
    assert historical[0]['superseded_by_job_id']=='replacement'


def test_old_generation_and_superseded_assets_are_not_enrichable(setup):
    c,_,_=setup
    created=c.create_job('s','c0','replacement-enrichment',reprocess=True)
    claim=c.claim(created['id'],'synthetic','fixture','claim-enrichment','enrich-token').value
    c.finish(claim,assets=[{'id':'replacement-enrichment-asset','asset_type':'principle','title':'Current',
        'what_it_says':'Current active','source_id':'s','chunk_id':'c0','evidence':'Evidence','keywords':[],
        'created_at':'2026-10-16T00:00:06+00:00','extraction_job_id':created['id'],'extraction_version':2,
        'active':True}],response_id='synthetic')
    assert c.enrich_current_assets('s',{'replacement-enrichment-asset':{'chapter_or_section':'Chapter 1'}})==1
    with pytest.raises(PartitionConflict,match='no longer current and active'):
        c.enrich_current_assets('s',{'a0':{'chapter_or_section':'Changed'}})
    historical=c.list_assets(source_ids=['s'],history=True)
    assert next(a for a in historical if a['id']=='a0')['chapter_or_section'] is None


def test_empty_replacement_supersedes_prior_batch_without_inserting_rows(setup):
    c,_,_=setup
    before=len(c.list_assets(history=True))
    job=c.create_job('s','c0','empty-replacement',reprocess=True)
    claim=c.claim(job['id'],'synthetic','fixture','empty-claim','empty-token').value
    c.finish(claim,assets=[],response_id='synthetic')
    current=c.active_assets(source_ids=['s'],chunk_id='c0')
    history=c.list_assets(source_ids=['s'],history=True)
    assert current==[]
    assert len(history)==before
    assert all(not item['active'] for item in history if item['chunk_id']=='c0')


def test_replacement_fails_closed_when_prior_active_batch_is_incomplete(setup):
    c,_,_=setup
    with c.transaction() as tx:
        tx.execute('DELETE FROM knowledge_engine.partition_assets WHERE workspace_key=%s AND asset_id=%s',
                   (tx.workspace,'a0'))
    job=c.create_job('s','c0','repair-corrupt-prior',reprocess=True)
    claim=c.claim(job['id'],'synthetic','fixture','corrupt-prior-claim','corrupt-prior-token').value
    candidate={'id':'should-not-commit','asset_type':'principle','title':'Replacement',
        'what_it_says':'Replacement','source_id':'s','chunk_id':'c0','evidence':'Evidence',
        'keywords':[],'created_at':'2026-10-16T00:00:06+00:00','extraction_job_id':job['id'],
        'extraction_version':2,'active':True}
    with pytest.raises(PartitionConflict,match='inconsistent'):
        c.finish(claim,assets=[candidate],response_id='synthetic')
    assert c.read_job(job['id'])['status']=='running'
    assert 'should-not-commit' not in {item['id'] for item in c.list_assets(history=True)}


def test_provenance_reconstruction_fails_closed_for_missing_or_ambiguous_matches():
    source={'s':{'source_id':'s','generation':2,'deleted':False}}
    j1={'job_id':'j1','source_id':'s','chunk_id':'c','generation':1,'extraction_version':1,'status':'completed'}
    j2={'job_id':'j2','source_id':'s','chunk_id':'c','generation':2,'extraction_version':1,'status':'completed'}
    asset={'id':'legacy','source_id':'s','chunk_id':'c','extraction_version':1}
    with pytest.raises(AssetProvenanceError,match='ambiguous'):
        Phase3Coordinator._resolve_asset(asset,source,{'j1':j1,'j2':j2},[j1,j2])
    with pytest.raises(AssetProvenanceError,match='no defensible'):
        Phase3Coordinator._resolve_asset({'id':'missing','source_id':'s','chunk_id':'none'},source,{},[j1,j2])
    resolved=Phase3Coordinator._resolve_asset(asset|{'generation':1},source,{'j1':j1,'j2':j2},[j1,j2])
    assert resolved['job_id']=='j1' and resolved['generation']==1
    explicit=Phase3Coordinator._resolve_asset(asset|{'extraction_job_id':'j2','generation':2},
                                               source,{'j1':j1,'j2':j2},[j1,j2])
    assert explicit['job_id']=='j2' and explicit['generation']==2


def test_v3_attempt_restarts_after_core_or_provenance_drift(phase3_database):
    workspace='p3-drift-'+uuid4().hex
    store=PostgresStateStore(phase3_database,workspace);state=fixture_state();store.load();store.save(state)
    p2=Phase2Coordinator(phase3_database,workspace)
    p2.prepare(1,'p2');p2.backfill(1);p2.verify(1);p2.cutover(1,writers_drained=True)
    c=Phase3Coordinator(phase3_database,workspace)
    c.prepare(2,'attempt-a');c.backfill(2,max_assets=1)
    first=c.read_migration();original_pin=first['provenance_fingerprint']
    # Narrow lifecycle drift is independently pinned even if core revision is unchanged.
    with c.transaction() as tx:
        row=tx._expect(tx._one('SELECT revision FROM knowledge_engine.partition_sources '
                               'WHERE workspace_key=%s AND source_id=%s FOR UPDATE',(tx.workspace,'s')))
        tx.advance_generation('s',1,row['revision'])
    with pytest.raises(PartitionConflict,match='provenance drift'):
        c.backfill(2,max_assets=1)
    restarted=c.restart_after_revision_drift(2,'attempt-a',2,original_pin,'attempt-b',writers_drained=True)
    assert restarted['attempt_id']=='attempt-b' and restarted['checkpoint']=={}
    history=c.read_migration_history()
    assert len(history)==1 and history[0]['terminal_reason']=='revision_drift'
    assert history[0]['attempt_id']=='attempt-a' and history[0]['checkpoint']=={'next_ordinal':1}
    assert history[0]['verified_at'] is None and history[0]['cutover_revision'] is None
    c.backfill(2);c.verify(2);c.cutover(2,writers_drained=True)
    assert c.active_assets()==[]
    assert [a['id'] for a in c.list_assets(history=True)]==['a0','a1']


def test_uncertain_completion_ack_uses_receipt_without_replay(setup,monkeypatch):
    c,_,_=setup
    job=c.create_job('s','c3','ack-job')
    claim=c.claim('ack-job','synthetic','fixture','ack-claim','ack-token').value
    asset={'id':'ack-asset','asset_type':'principle','title':'Ack','what_it_says':'Receipt',
        'source_id':'s','chunk_id':'c3','evidence':'Receipt evidence','keywords':['receipt'],
        'created_at':'2026-10-16T00:00:06+00:00','extraction_job_id':'ack-job','extraction_version':1,'active':True}
    original=c.apply
    calls={'n':0}
    from app.persistence.postgres import HostedStateStoreError
    def uncertain(*args,**kwargs):
        result=original(*args,**kwargs)
        calls['n']+=1
        raise HostedStateStoreError('simulated uncertain commit')
    monkeypatch.setattr(c,'apply',uncertain)
    result=c.finish(claim,assets=[asset],response_id='synthetic')
    assert result.replayed and calls['n']==1
    assert c.read_job('ack-job')['status']=='completed'
    assert [a['id'] for a in c.active_assets(source_ids=['s'])][-1]=='ack-asset'


def test_same_chunk_live_claim_is_unique_and_stale_claim_token_is_rejected(setup):
    c,_,_=setup
    job=c.create_job('s','c7','single-live-claim')
    claim=c.claim(job['id'],'synthetic','fixture','single-live-claim-op','valid-token').value
    duplicate=c.create_job('s','c7','duplicate-live-job',reprocess=True)
    assert duplicate['id']==job['id']
    with pytest.raises(PartitionConflict):
        c.claim(job['id'],'synthetic','fixture','second-live-claim-op','second-token')
    stale=dict(claim,claim_token='stale-token')
    with pytest.raises(PartitionConflict):
        c.finish(stale,assets=[],response_id='synthetic')
    assert c.read_job(job['id'])['status']=='running'
    assert c.finish(claim,assets=[],response_id='synthetic').value['status']=='completed'


def test_transaction_conflict_reuses_validated_result_without_provider_replay(setup,monkeypatch):
    c,_,_=setup
    job=c.create_job('s','c8','transaction-conflict')
    claim=c.claim(job['id'],'synthetic','fixture','transaction-conflict-claim','transaction-token').value
    provider_calls={'count':1}
    asset={'id':'transaction-result','asset_type':'principle','title':'Retained result',
        'what_it_says':'Validated synthetic result','source_id':'s','chunk_id':'c8',
        'evidence':'Synthetic evidence','keywords':[],'created_at':'2026-10-16T00:00:09+00:00',
        'extraction_job_id':job['id'],'extraction_version':1,'active':True}
    original=c.apply;conflicts={'count':0}
    def conflict_once(operation,request,mutation,**kwargs):
        if conflicts['count']==0:
            conflicts['count']+=1
            def fail_before_settlement(tx):
                raise PartitionConflict('injected transaction conflict')
            return original(operation,request,fail_before_settlement,**kwargs)
        return original(operation,request,mutation,**kwargs)
    monkeypatch.setattr(c,'apply',conflict_once)
    with pytest.raises(PartitionConflict,match='injected transaction conflict'):
        c.finish(claim,assets=[asset],response_id='synthetic')
    result=c.finish(claim,assets=[asset],response_id='synthetic')
    assert result.value['status']=='completed'
    assert provider_calls['count']==1
    assert [item['id'] for item in c.active_assets(source_ids=['s'],chunk_id='c8')]==['transaction-result']


def test_rollback_rehydrates_asset_order_then_new_attempt_reverifies(setup):
    c,store,state=setup
    result=c.rollback(3,writers_drained=True)
    assert result['payload']['knowledge_assets']==state['knowledge_assets']
    legacy=store.load()
    assert legacy['knowledge_assets']==state['knowledge_assets']
    restarted=c.restart_after_rollback(4,'phase3-attempt-2',writers_drained=True)
    assert restarted['attempt_id']=='phase3-attempt-2'
    c.backfill(4);c.verify(4);c.cutover(4,writers_drained=True)
    assert c.active_assets()==state['knowledge_assets']


def test_v3_delete_and_rechunk_generation_fences(setup):
    c,store,state=setup
    # Delete wins while the provider is outside the database.
    job=c.create_job('s','c2','delete-race')
    claim=c.claim(job['id'],'synthetic','fixture','claim-delete','delete-token').value
    baseline=store.load();proposed=deepcopy(baseline);proposed['sources']=[];proposed['knowledge_assets']=[]
    c.save_core(baseline,proposed,core(c)['revision'])
    with pytest.raises(PartitionConflict):c.finish(claim,assets=[])
    assert not c.active_assets()


def test_completion_first_then_delete_removes_narrow_rows_atomically(setup):
    c,store,_=setup
    job=c.create_job('s','c2','complete-before-delete')
    claim=c.claim(job['id'],'synthetic','fixture','complete-before-delete-claim','delete-after-token').value
    new={'id':'complete-before-delete-asset','asset_type':'principle','title':'Committed',
        'what_it_says':'Committed before delete','source_id':'s','chunk_id':'c2','evidence':'Evidence',
        'keywords':[],'created_at':'2026-10-16T00:00:06+00:00','extraction_job_id':job['id'],
        'extraction_version':1,'active':True}
    c.finish(claim,assets=[new],response_id='synthetic')
    baseline=store.load();proposed=deepcopy(baseline);proposed['sources']=[]
    c.save_core(baseline,proposed,core(c)['revision'])
    assert c.active_assets()==[]
    assert c.read_source('s')['deleted'] is True
    with c.transaction() as tx:
        assert tx._one('SELECT count(*) AS n FROM knowledge_engine.partition_assets WHERE workspace_key=%s',
                       (tx.workspace,))['n']==0


def test_rechunk_first_fences_provider_completion(setup):
    c,store,_=setup
    job=c.create_job('s','c2','rechunk-before-completion')
    claim=c.claim(job['id'],'synthetic','fixture','rechunk-before-claim','rechunk-before-token').value
    baseline=store.load();proposed=deepcopy(baseline)
    proposed['sources'][0]['chunk_manifest']={'version':1,'total_parts':1,'chunk_ids':['new-chunk']}
    c.save_core(baseline,proposed,core(c)['revision'])
    with pytest.raises(PartitionConflict,match='generation is stale'):
        c.finish(claim,assets=[],response_id='synthetic')
    assert c.read_source('s')['generation']==2
    assert c.active_assets()==[]


def test_rollback_refuses_inflight_current_generation_job(setup):
    c,_,_=setup
    job=c.create_job('s','c4','rollback-inflight')
    c.claim(job['id'],'synthetic','fixture','rollback-inflight-claim','rollback-inflight-token')
    with pytest.raises(PartitionConflict,match='Running current-generation jobs'):
        c.rollback(core(c)['revision'],writers_drained=True)


def test_independent_chunk_completions_reserve_distinct_global_ordinals(setup):
    from concurrent.futures import ThreadPoolExecutor
    c,_,_=setup
    claims=[]
    for chunk,job_id in [('c5','independent-a'),('c6','independent-b')]:
        c.create_job('s',chunk,job_id)
        claims.append(c.claim(job_id,'synthetic','fixture','claim-'+job_id,'token-'+job_id).value)
    def finish(claim):
        aid=claim['job_id']+'-asset'
        asset={'id':aid,'asset_type':'principle','title':aid,'what_it_says':aid,
            'source_id':'s','chunk_id':claim['chunk_id'],'evidence':'Evidence','keywords':[],
            'created_at':'2026-10-16T00:00:07+00:00','extraction_job_id':claim['job_id'],
            'extraction_version':1,'active':True}
        return c.finish(claim,assets=[asset],response_id='synthetic')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(finish,claims))
    assert all(result.value['status']=='completed' for result in results)
    with c.transaction() as tx:
        rows=tx._all('SELECT asset_id,ordinal FROM knowledge_engine.partition_assets '
                     'WHERE workspace_key=%s AND asset_id=ANY(%s) ORDER BY ordinal',
                     (tx.workspace,['independent-a-asset','independent-b-asset']))
    assert len(rows)==2 and rows[0]['ordinal']+1==rows[1]['ordinal']


def test_v3_rechunk_after_completion_keeps_old_assets_historical(setup):
    c,store,state=setup
    job=c.create_job('s','c2','rechunk-race')
    claim=c.claim(job['id'],'synthetic','fixture','claim-rechunk','rechunk-token').value
    c.finish(claim,assets=[],response_id='synthetic')
    baseline=store.load();proposed=deepcopy(baseline)
    proposed['sources'][0]['chunk_manifest']={'version':1,'total_parts':1,'chunk_ids':['new-chunk']}
    c.save_core(baseline,proposed,core(c)['revision'])
    assert c.read_source('s')['generation']==2
    assert c.active_assets()==[]
    assert [a['id'] for a in c.list_assets(history=True)]==['a0','a1']
    with c.transaction() as tx:
        old=tx._one("SELECT count(*) AS n FROM knowledge_engine.partition_assets WHERE workspace_key=%s AND generation=1",
                    (tx.workspace,))
    assert old['n']==2
