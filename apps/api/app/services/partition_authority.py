"""Read-boundary composition and captured claim context, never another authority."""
from contextvars import ContextVar
from uuid import uuid4
from app.persistence.factory import PERSISTENCE_MODE, get_state_store, get_phase2_coordinator, get_phase3_coordinator
from app.persistence.partitions import PartitionConflict
from app.persistence.phase2 import job_dto, owned

_claims=ContextVar('ke_phase2_claims',default=None)


def coordinator():
    from app.db.request_state import request_mode
    store=get_state_store()
    version=3 if bool(getattr(store,'phase3',False)) else (2 if bool(getattr(store,'phase2',False)) else 0)
    enabled=PERSISTENCE_MODE=='hosted' and version in (2,3)
    if request_mode.get() is not None and enabled!=request_mode.get():
        from app.db.persistence import StateMutationConflict
        raise StateMutationConflict('Persistence authority changed during the request; reload before continuing.')
    if enabled:
        return get_phase3_coordinator() if version==3 else get_phase2_coordinator()
    return None


def claims():
    from app.db.request_state import view
    current=view.get()
    if current is not None:
        return current['claims']
    if _claims.get() is None:
        _claims.set({})
    return _claims.get()


def source(record):
    c=coordinator()
    if not c or record is None:
        return record
    from app.db.request_state import view
    if view.get() is not None and record['id'] in view.get()['generations']:
        return record
    rows=c.scoped([record['id']],include_jobs=False)['sources']
    if not rows:
        return None
    record.clear();record.update(rows[0])
    return record


def jobs(source_id=None,*,history=False):
    c=coordinator()
    if c:
        if history: return c.history_jobs(source_id)
        from app.db.request_state import view
        current=view.get()
        if current is not None and source_id is not None and source_id in current['job_sources']:
            return [j for j in current['extraction_jobs'] if j['source_id']==source_id]
        return c.scoped([source_id] if source_id is not None else None)['extraction_jobs']
    from app.db.mock_data import extraction_jobs
    from app.db.mock_data import sources
    generations={s['id']:s.get('generation',1) for s in sources}
    return [j for j in extraction_jobs if (source_id is None or j['source_id']==source_id)
            and (history or j.get('generation',1)==generations.get(j['source_id'],1))]


def find_job(job_id):
    c=coordinator()
    from app.db.request_state import view
    current=view.get()
    if current is not None:
        cached=next((j for j in current['extraction_jobs'] if j['id']==job_id),None)
        if cached is not None: return cached
    row=c.read_job(job_id)
    if row:
        s=c.read_source(row['source_id'])
        if not s or s['deleted']:
            return None
    return job_dto(row)


def claim(job_id,provider,model):
    c=coordinator()
    result=c.claim(job_id,provider,model,uuid4().hex,uuid4().hex)
    if result.replayed:
        raise PartitionConflict('A replayed claim cannot dispatch another provider request.')
    claims()[job_id]=result.value
    return remember_job(job_dto(result.value))


def complete(job_id,assets,response_id):
    c=coordinator()
    captured=claims().get(job_id)
    if captured is None:
        # Manual result submission may complete pending work, but never hijack a running claim.
        job=find_job(job_id)
        if not job or job['status']!='pending_ai':
            raise PartitionConflict('Completion requires this request\'s current claim.')
        claim(job_id,job.get('provider'),job.get('model'))
        captured=claims()[job_id]
    result=c.finish(captured,assets=assets,response_id=response_id,on_committed=get_state_store().accept_committed)
    return remember_job(job_dto(result.value))


def fail(job_id,error):
    captured=claims().get(job_id)
    if captured is None:
        raise PartitionConflict('Failure transition requires the captured claim.')
    return remember_job(job_dto(coordinator().finish(captured,error=error).value))


def checkpoint_source(source_id,status,reason):
    c=coordinator()
    s=c.read_source(source_id)
    if not s or s['deleted']:
        raise PartitionConflict('Source lifecycle is deleted or missing.')
    fields=dict(s['api_payload'] or {},processing_status=status,stopped_reason=reason)
    from app.db.request_state import view
    current=view.get()
    generation=current['generations'].get(source_id) if current is not None else None
    c.source_fields(source_id,fields,generation=generation)


def has_history(source_id):
    c=coordinator()
    if not c:
        return bool(jobs(source_id,history=True))
    with c.transaction() as tx:
        return tx._one('SELECT job_id FROM knowledge_engine.partition_jobs WHERE workspace_key=%s AND source_id=%s LIMIT 1',
                       (tx.workspace,source_id)) is not None


def remember_job(job):
    from app.db.request_state import view
    current=view.get()
    if current is not None:
        current['extraction_jobs'][:]=[j for j in current['extraction_jobs'] if j['id']!=job['id']]+[job]
    return job


def create_job(source_id,chunk_id,job_id,reprocess):
    from app.db.request_state import view
    current=view.get()
    generation=current['generations'].get(source_id) if current is not None else None
    return remember_job(coordinator().create_job(source_id,chunk_id,job_id,reprocess,expected_generation=generation))


def legacy_generation_guard(job):
    from app.db.mock_data import sources
    source=next((s for s in sources if s['id']==job['source_id']),None)
    if source is None or source.get('deleted',False) or job.get('generation',1)!=source.get('generation',1):
        raise ValueError('This historical job belongs to a fenced source generation.')


def guard_chunk_read(job_id):
    from app.db.request_state import view
    current=view.get()
    if current is not None and any(j['id']==job_id for j in current['extraction_jobs']):
        return
    c=coordinator();job=c.read_job(job_id)
    s=c.read_source(job['source_id']) if job else None
    if not job or not s or s['deleted'] or job['generation']!=s['generation']:
        raise ValueError('This historical job belongs to a fenced source generation.')


def jobs_many(source_ids):
    from app.db.request_state import view
    current=view.get()
    wanted=set(source_ids)
    if current is not None and wanted<=current['job_sources']:
        return [j for j in current['extraction_jobs'] if j['source_id'] in wanted]
    return coordinator().scoped(source_ids)['extraction_jobs']


def assets(source_ids=None, *, history=False):
    c=coordinator()
    if c is not None and getattr(c,'version',2)==3:
        return c.list_assets(source_ids=source_ids,history=history)
    from app.db.mock_data import knowledge_assets
    records=list(knowledge_assets)
    if source_ids is not None:
        wanted=set(source_ids);records=[a for a in records if a.get('source_id') in wanted]
    return records if history else [a for a in records if a.get('active',True)]


def legacy_mutation_guard(job):
    legacy_generation_guard(job)
    from app.db.mock_data import sources,extraction_jobs
    source=next(s for s in sources if s['id']==job['source_id'])
    if 'generation' in source:
        latest=max((j.get('extraction_version',1) for j in extraction_jobs
                    if j['source_id']==job['source_id'] and j['chunk_id']==job['chunk_id']
                    and j.get('generation',1)==job.get('generation',1)),default=1)
        if job.get('extraction_version',1)!=latest:
            raise ValueError('This historical extraction version has been superseded.')


def refresh_authority():
    """Poll only the small core marker, never the corpus, on authenticated ingress.

    Reload once on an actual authority change. This prevents already-running
    compatible workers serving legacy job caches after an external cutover.
    """
    if PERSISTENCE_MODE!='hosted':return
    from app.persistence.postgres import PostgresStateStore
    store=get_state_store()
    if not isinstance(store,PostgresStateStore) or not store._loaded:return
    c=get_phase2_coordinator()
    if (c._workspace_key,c._database_url)!=(store._workspace_key,store._database_url):
        from app.persistence.phase2 import Phase2Coordinator
        c=Phase2Coordinator(store._database_url,store._workspace_key)
    with c.transaction() as tx:
        row=tx._one("SELECT payload->'partition' AS marker,payload ? 'partition' AS present "
                    'FROM knowledge_engine.state_snapshots WHERE workspace_key=%s',(tx.workspace,))
    with store._lock:
        previous=store._loaded_snapshot or {}
        changed=bool(row) and (row['present']!=('partition' in previous) or row['marker']!=previous.get('partition'))
    if changed:
        state=store.load()
        from app.db import mock_data as db
        from app.db.persistence import _restore_live_state
        _restore_live_state(state,db.libraries,db.sources,db.extraction_jobs,db.knowledge_assets,preserve_record_objects=False)
