"""Explicit version-2 jobs/lifecycle authority. Assets remain core-owned.

No migration is invoked at startup. All data migration/activation/rollback methods
require explicit calls by a drained-writer administrative workflow.
"""
import psycopg
from datetime import datetime, timezone
from copy import deepcopy
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.persistence.partitions import PostgresPartitionStore, PartitionConflict, PartitionVersionError, PartitionMutation
from app.persistence.postgres import StaleStateWriteError, HostedStateStoreError
from app.persistence.reconciliation import merge_state_snapshots

VERSION = 2
DOMAINS = ['jobs', 'source_lifecycle']
OWNED = {'processing_status', 'stopped_reason', 'generation', 'deleted', 'interruption_reason'}
META = {'provider', 'model', 'model_response_id', 'asset_count', 'error'}
MARKER = {'version': VERSION, 'state': 'active', 'domains': DOMAINS}


def active(state):
    if not state or 'partition' not in state:
        return False
    marker = state['partition']
    if marker == MARKER:
        return True
    raise PartitionVersionError('Unsupported partition authority marker.')


def compact(state):
    core = deepcopy(state)
    core.pop('extraction_jobs', None)
    core['sources'] = [{k: v for k, v in s.items() if k not in OWNED} for s in state.get('sources', [])]
    core['partition'] = deepcopy(MARKER)
    return core


def owned(source):
    return {k: deepcopy(v) for k, v in source.items() if k in OWNED}


def source_projection(source):
    """Ignore only fields added by rollback but absent from legacy source JSON."""
    return {k: deepcopy(v) for k, v in owned(source).items()
            if k not in {'generation', 'deleted'}}


def job_dto(row):
    return deepcopy(row['api_payload']) if row else None


def job_projection_matches(api_payload, legacy_job):
    """Generation may be relationally present after rollback but absent in old JSON."""
    actual = deepcopy(api_payload or {})
    expected = deepcopy(legacy_job)
    if 'generation' in expected:
        generation = expected.pop('generation')
        if 'generation' in actual and actual.pop('generation') != generation:
            return False
    return actual == expected


class Phase2Coordinator(PostgresPartitionStore):
    def _core(self, tx, expected=None):
        row = tx._expect(tx._one('SELECT payload, revision FROM knowledge_engine.state_snapshots '
                                'WHERE workspace_key = %s FOR UPDATE', (tx.workspace,)))
        if expected is not None and row['revision'] != expected:
            raise StaleStateWriteError('Workspace revision changed; reload before saving.')
        return row

    def _cas(self, tx, payload, revision):
        row = tx._one('UPDATE knowledge_engine.state_snapshots SET payload = %s, revision = revision + 1, '
                      'updated_at = now() WHERE workspace_key = %s AND revision = %s RETURNING revision',
                      (Jsonb(payload), tx.workspace, revision))
        if row is None:
            raise StaleStateWriteError('Workspace revision changed; reload before saving.')
        return row['revision']

    def _require_active(self, tx):
        row = tx._one("SELECT payload->'partition' AS marker FROM knowledge_engine.state_snapshots WHERE workspace_key = %s",
                      (tx.workspace,))
        if not row or row['marker'] != MARKER:
            raise PartitionConflict('Jobs/lifecycle authority changed; reload before continuing.')

    def read_migration(self):
        with self.transaction() as tx:
            row=tx._one('SELECT row_to_json(m) AS record FROM knowledge_engine.partition_migrations m '
                        'WHERE workspace_key=%s',(tx.workspace,))
            if row and row['record']['partition_version']!=VERSION:
                raise PartitionVersionError('Unsupported Phase 2 staging version.')
            return row['record'] if row else None

    def read_migration_history(self):
        """Return immutable attempts superseded by rollback or drift restarts."""
        with self.transaction() as tx:
            return tx._all('SELECT workspace_key,migration_id,partition_version,source_snapshot_revision,stage,checkpoint,'
                           'migration_revision,started_at,verified_at,cutover_revision,terminal_reason,archived_at '
                           'FROM knowledge_engine.partition_migration_attempt_history '
                           'WHERE workspace_key=%s ORDER BY migration_revision,migration_id',(tx.workspace,))

    def _migration(self, tx, revision=None, stage=None):
        row = tx._expect(tx._one('SELECT * FROM knowledge_engine.partition_migrations '
                                'WHERE workspace_key = %s FOR UPDATE', (tx.workspace,)))
        if row['partition_version'] != VERSION or (revision is not None and row['source_snapshot_revision'] != revision):
            raise PartitionConflict('Migration snapshot revision drift or incompatible version.')
        if stage and row['stage'] != stage:
            raise PartitionConflict('Migration is not in the required stage.')
        return row

    def prepare(self, expected_revision, migration_id):
        with self.transaction() as tx:
            core = self._core(tx, expected_revision)
            if core['payload'].get('partition') is not None:
                raise PartitionConflict('Migration requires legacy authority.')
            existing = tx._one('SELECT * FROM knowledge_engine.partition_migrations WHERE workspace_key = %s FOR UPDATE',
                               (tx.workspace,))
            if existing:
                if (existing['migration_id'] != migration_id or existing['source_snapshot_revision'] != expected_revision
                        or existing['partition_version'] != VERSION):
                    raise PartitionConflict('A different or drifted migration attempt already exists.')
                return dict(stage=existing['stage'], checkpoint=existing['checkpoint'])
            tx._one('INSERT INTO knowledge_engine.partition_migrations '
                    '(workspace_key,migration_id,partition_version,source_snapshot_revision) VALUES (%s,%s,2,%s) '
                    'RETURNING revision', (tx.workspace, migration_id, expected_revision))
            return {'stage': 'preparing', 'checkpoint': {}}

    def restart_after_rollback(self, expected_revision, migration_id, *, writers_drained=False):
        """Start a new pinned attempt reusing verified retained rows after rollback.

        This does not discard retained lifecycle fences, jobs or receipts. The
        prior attempt is archived, and the old staging set must exactly match
        the rehydrated legacy snapshot before the new attempt is created.
        """
        if not writers_drained:
            raise PartitionConflict('Migration restart requires explicitly drained writers.')
        with self.transaction() as tx:
            core = self._core(tx, expected_revision)
            if core['payload'].get('partition') is not None:
                raise PartitionConflict('Migration restart requires legacy authority after rollback.')
            migration = self._migration(tx, stage='verified')
            if (migration['source_snapshot_revision'] >= expected_revision
                    or migration['cutover_revision'] is None
                    or migration['cutover_revision'] >= expected_revision):
                raise PartitionConflict('Migration restart requires a later legacy revision after a recorded cutover.')
            self._equivalent(tx, core['payload'])
            tx.connection.execute("SELECT set_config('knowledge_engine.phase2_restart','on',true)")
            tx._one('INSERT INTO knowledge_engine.partition_migration_attempt_history '
                    '(workspace_key,migration_id,partition_version,source_snapshot_revision,stage,checkpoint,'
                    'migration_revision,started_at,verified_at,cutover_revision,terminal_reason) '
                    'SELECT workspace_key,migration_id,partition_version,source_snapshot_revision,stage,checkpoint,'
                    'revision,started_at,verified_at,cutover_revision,\'rollback_restart\' FROM knowledge_engine.partition_migrations '
                    'WHERE workspace_key=%s RETURNING migration_id',(tx.workspace,))
            tx._one("UPDATE knowledge_engine.partition_migrations SET migration_id=%s,source_snapshot_revision=%s,"
                    "stage='preparing',checkpoint='{}'::jsonb,verified_at=NULL,cutover_revision=NULL,"
                    'started_at=now(),revision=revision+1,updated_at=now() '
                    "WHERE workspace_key=%s RETURNING revision",
                    (migration_id, expected_revision, tx.workspace))
            return {'stage': 'preparing', 'checkpoint': {}}

    def restart_after_revision_drift(self, expected_revision, expected_migration_id,
                                     expected_pinned_revision, migration_id, *, writers_drained=False):
        """Archive a drifted preparing attempt and start fresh under legacy authority.

        This explicit administrative transition never changes the old pin or
        carries its checkpoint into the new attempt. Repeating it with the old
        expected attempt ID is rejected after the atomic switch.
        """
        if not writers_drained:
            raise PartitionConflict('Migration restart requires explicitly drained writers.')
        with self.transaction() as tx:
            core = self._core(tx, expected_revision)
            if core['payload'].get('partition') is not None:
                raise PartitionConflict('Drift restart requires legacy authority.')
            current = self._migration(tx, stage='preparing')
            if (current['migration_id'] != expected_migration_id
                    or current['source_snapshot_revision'] != expected_pinned_revision
                    or current['source_snapshot_revision'] == expected_revision
                    or current.get('verified_at') is not None
                    or current.get('cutover_revision') is not None
                    or migration_id == current['migration_id']):
                raise PartitionConflict('Expected drifted preparing attempt does not match current migration state.')
            tx.connection.execute("SELECT set_config('knowledge_engine.phase2_drift_restart','on',true)")
            tx._one('INSERT INTO knowledge_engine.partition_migration_attempt_history '
                    '(workspace_key,migration_id,partition_version,source_snapshot_revision,stage,checkpoint,'
                    'migration_revision,started_at,verified_at,cutover_revision,terminal_reason) '
                    'SELECT workspace_key,migration_id,partition_version,source_snapshot_revision,stage,checkpoint,'
                    'revision,started_at,verified_at,cutover_revision,\'revision_drift\' '
                    'FROM knowledge_engine.partition_migrations WHERE workspace_key=%s RETURNING migration_id',
                    (tx.workspace,))
            tx._one("UPDATE knowledge_engine.partition_migrations SET migration_id=%s,source_snapshot_revision=%s,"
                    "stage='preparing',checkpoint='{}'::jsonb,verified_at=NULL,cutover_revision=NULL,"
                    'started_at=now(),revision=revision+1,updated_at=now() '
                    'WHERE workspace_key=%s RETURNING revision',
                    (migration_id, expected_revision, tx.workspace))
            return {'stage': 'preparing', 'checkpoint': {}}

    def backfill(self, expected_revision, *, max_sources=100):
        if max_sources < 1:
            raise ValueError('max_sources must be positive.')
        with self.transaction() as tx:
            core = self._core(tx, expected_revision)
            migration = self._migration(tx, expected_revision, 'preparing')
            if core['payload'].get('partition') is not None:
                raise PartitionConflict('Shadow backfill requires legacy authority.')
            tx.connection.execute("SELECT set_config('knowledge_engine.backfill','on',true)")
            tx.connection.execute("SELECT set_config('knowledge_engine.backfill_workspace',%s,true)", (tx.workspace,))
            checkpoint = migration['checkpoint']
            done = set(checkpoint.get('sources', []))
            source_ids = {s['id'] for s in core['payload'].get('sources', [])}
            jobs = core['payload'].get('extraction_jobs', [])
            if any(j['source_id'] not in source_ids for j in jobs):
                raise PartitionConflict('Backfill contains orphaned jobs.')
            selected = [s for s in core['payload'].get('sources', []) if s['id'] not in done][:max_sources]
            for s in sorted(selected,key=lambda s:s['id']):
                generation = s.get('generation', 1)
                existing_source = tx._one('SELECT * FROM knowledge_engine.partition_sources '
                                          'WHERE workspace_key=%s AND source_id=%s FOR UPDATE',
                                          (tx.workspace,s['id']))
                if existing_source is None:
                    tx._one('INSERT INTO knowledge_engine.partition_sources '
                            '(workspace_key,source_id,generation,deleted,interpretation_status,stopped_reason,api_payload) '
                            'VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING source_id',
                            (tx.workspace,s['id'],generation,s.get('deleted',False),s.get('processing_status'),
                             s.get('stopped_reason'),Jsonb(owned(s))))
                elif (existing_source['generation'] != generation or existing_source['deleted'] != s.get('deleted',False)
                      or source_projection(existing_source['api_payload'] or {}) != source_projection(s)
                      or existing_source['interpretation_status'] != s.get('processing_status')
                      or existing_source['stopped_reason'] != s.get('stopped_reason')):
                    raise PartitionConflict('Retained source fence differs from the pinned snapshot.')
                for ordinal, j in enumerate(jobs):
                    if j['source_id'] != s['id']:
                        continue
                    # Generation is immutable job provenance, not the live source fence.
                    job_generation = j.get('generation', 1)
                    if job_generation > generation:
                        raise PartitionConflict('Backfill job generation is ahead of its source.')
                    existing_job = tx._one('SELECT * FROM knowledge_engine.partition_jobs '
                                            'WHERE workspace_key=%s AND job_id=%s FOR UPDATE',
                                            (tx.workspace,j['id']))
                    if existing_job is not None:
                        metadata={k:v for k,v in j.items() if k in META}
                        if (existing_job['generation'] != job_generation or existing_job['source_id'] != s['id']
                                or existing_job['chunk_id'] != j['chunk_id']
                                or existing_job['extraction_version'] != j.get('extraction_version',1)
                                or existing_job['status'] != j['status'] or existing_job['metadata'] != metadata
                                or not job_projection_matches(existing_job['api_payload'],j)
                                or existing_job['ordinal'] != ordinal):
                            raise PartitionConflict('Retained job provenance differs from the pinned snapshot.')
                        continue
                    tx._one('INSERT INTO knowledge_engine.partition_jobs '
                            '(workspace_key,job_id,source_id,chunk_id,generation,extraction_version,status,claim_token,metadata,'
                            'created_at,started_at,completed_at,recovered_at,api_payload,ordinal) '
                            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING job_id',
                            (tx.workspace,j['id'],s['id'],j['chunk_id'],job_generation,j.get('extraction_version',1),j['status'],
                             uuid4().hex if j['status']=='running' else None,Jsonb({k:v for k,v in j.items() if k in META}),
                             j['created_at'],j.get('started_at') or (j['created_at'] if j['status']=='running' else None),
                             j.get('completed_at'),j.get('recovered_at'),Jsonb(j),ordinal))
                done.add(s['id'])
            checkpoint = {'sources': sorted(done)}
            tx._one('UPDATE knowledge_engine.partition_migrations SET checkpoint=%s,revision=revision+1,updated_at=now() '
                    'WHERE workspace_key=%s RETURNING revision', (Jsonb(checkpoint),tx.workspace))
            return checkpoint

    def _equivalent(self, tx, payload):
        sources = tx._all('SELECT * FROM knowledge_engine.partition_sources WHERE workspace_key=%s AND NOT deleted ORDER BY source_id',
                          (tx.workspace,))
        expected = sorted(payload.get('sources', []), key=lambda s:s['id'])
        if len(sources) != len(expected):
            raise PartitionConflict('Source equivalence verification failed.')
        for row, s in zip(sources, expected):
            if (row['source_id'] != s['id']
                    or source_projection(row['api_payload'] or {}) != source_projection(s)
                    or row['generation'] != s.get('generation',1) or row['deleted'] != s.get('deleted',False)
                    or row['interpretation_status'] != s.get('processing_status')
                    or row['stopped_reason'] != s.get('stopped_reason')):
                raise PartitionConflict('Source equivalence verification failed.')
        rows = tx._all('SELECT j.* FROM knowledge_engine.partition_jobs j '
                       'JOIN knowledge_engine.partition_sources s USING (workspace_key,source_id) '
                       'WHERE j.workspace_key=%s AND NOT s.deleted ORDER BY j.ordinal,j.job_id',
                       (tx.workspace,))
        expected_jobs=payload.get('extraction_jobs', [])
        if len(rows) != len(expected_jobs) or any(
                not job_projection_matches(job_dto(row),job)
                for row,job in zip(rows,expected_jobs)):
            raise PartitionConflict('Job equivalence verification failed.')
        for ordinal,row in enumerate(rows):
            j = row['api_payload']
            if (row['job_id']!=j['id'] or row['ordinal']!=ordinal or row['extraction_version']!=j.get('extraction_version',1)
                    or row['status'] != j['status'] or row['source_id'] != j['source_id'] or row['chunk_id'] != j['chunk_id']
                    or row['metadata'] != {k:v for k,v in j.items() if k in META}
                    or row['generation'] != j.get('generation',1)):
                raise PartitionConflict('Job relational equivalence failed.')
            for key in ('created_at','started_at','completed_at','recovered_at'):
                expected_time=j.get(key)
                if key=='started_at' and expected_time is None and j['status']=='running':
                    expected_time=j['created_at']
                if expected_time is not None:
                    expected_time=datetime.fromisoformat(expected_time.replace('Z','+00:00'))
                    if expected_time.tzinfo is None: expected_time=expected_time.replace(tzinfo=timezone.utc)
                if row[key]!=expected_time:
                    raise PartitionConflict('Job timestamp equivalence failed.')


    def verify(self, expected_revision):
        with self.transaction() as tx:
            core = self._core(tx, expected_revision)
            self._migration(tx, expected_revision, 'preparing')
            self._equivalent(tx, core['payload'])
            tx._one("UPDATE knowledge_engine.partition_migrations SET stage='verified',verified_at=now(),revision=revision+1 "
                    'WHERE workspace_key=%s RETURNING revision', (tx.workspace,))
            return {'stage':'verified'}

    def cutover(self, expected_revision, *, writers_drained=False):
        if not writers_drained:
            raise PartitionConflict('Cutover requires explicitly drained legacy writers.')
        with self.transaction() as tx:
            core = self._core(tx, expected_revision)
            self._migration(tx, expected_revision, 'verified')
            if core['payload'].get('partition') is not None:
                raise PartitionConflict('Cutover requires legacy authority.')
            tx._all('SELECT source_id FROM knowledge_engine.partition_sources WHERE workspace_key=%s ORDER BY source_id FOR UPDATE',(tx.workspace,))
            self._equivalent(tx,core['payload'])
            generations={s['id']:s.get('generation',1) for s in core['payload'].get('sources',[])}
            if any(j['status']=='running' and j.get('generation',1)==generations[j['source_id']]
                   for j in core['payload'].get('extraction_jobs',[])):
                raise PartitionConflict('Running legacy jobs prevent cutover.')
            payload = compact(core['payload'])
            revision = self._cas(tx,payload,expected_revision)
            tx.connection.execute("SELECT set_config('knowledge_engine.phase2_cutover','on',true)")
            tx._one('UPDATE knowledge_engine.partition_migrations SET cutover_revision=%s,revision=revision+1,updated_at=now() '
                    'WHERE workspace_key=%s RETURNING revision',(revision,tx.workspace))
        return {'revision':revision,'payload':payload}

    def compose(self, tx, core, *, source_ids=None, include_jobs=False, generations=None, history=False):
        state = deepcopy(core)
        ids = source_ids if source_ids is not None else [s['id'] for s in state.get('sources',[])]
        rows = tx._all('SELECT source_id,api_payload,deleted,generation FROM knowledge_engine.partition_sources '
                       'WHERE workspace_key=%s AND source_id=ANY(%s)',(tx.workspace,ids)) if ids else []
        mapping = {s['source_id']:s for s in rows}
        if generations is not None:
            generations.update({s['source_id']:s['generation'] for s in rows})
        state['sources'] = [s | (mapping[s['id']]['api_payload'] or {}) for s in state.get('sources',[])
                            if s['id'] in mapping and not mapping[s['id']]['deleted']]
        if include_jobs:
            state['extraction_jobs'] = [r['api_payload'] for r in tx._all(
                'SELECT j.api_payload FROM knowledge_engine.partition_jobs j JOIN knowledge_engine.partition_sources s '
                'USING(workspace_key,source_id) WHERE j.workspace_key=%s AND j.source_id=ANY(%s) '
                'AND NOT s.deleted AND (j.generation=s.generation OR %s) ORDER BY j.ordinal,j.job_id',(tx.workspace,ids,history))]
        return state

    def scoped(self, source_ids=None, *, job_id=None, include_jobs=True):
        with self.transaction() as tx:
            tx.connection.isolation_level=psycopg.IsolationLevel.REPEATABLE_READ
            self._require_active(tx)
            if job_id:
                j=tx.read_job(job_id)
                source_ids=[j['source_id']] if j else []
            row=tx._one("SELECT jsonb_build_object('sources',coalesce((SELECT jsonb_agg(s ORDER BY ord) FROM "
                        "jsonb_array_elements(payload->'sources') WITH ORDINALITY AS p(s,ord) WHERE %s::text[] IS NULL OR s->>'id'=ANY(%s)), '[]'::jsonb)) AS payload "
                        'FROM knowledge_engine.state_snapshots WHERE workspace_key=%s',
                        (source_ids,source_ids,tx.workspace))
            generations={}
            result=self.compose(tx,row['payload'],include_jobs=include_jobs,generations=generations)
            result['_generations']=generations
            return result

    def create_job(self, source_id, chunk_id, job_id, reprocess=False, *, expected_generation=None):
        def mutation(tx):
            self._require_active(tx)
            s=tx._expect(tx._one('SELECT * FROM knowledge_engine.partition_sources WHERE workspace_key=%s '
                                 'AND source_id=%s AND NOT deleted FOR UPDATE',(tx.workspace,source_id)))
            if expected_generation is not None and s['generation']!=expected_generation:
                raise PartitionConflict('Request source generation is stale.')
            self._require_active(tx)
            manifest=tx._one("SELECT s->'chunk_manifest' AS manifest FROM knowledge_engine.state_snapshots, "
                             "LATERAL jsonb_array_elements(payload->'sources') s WHERE workspace_key=%s AND s->>'id'=%s",
                             (tx.workspace,source_id))
            if not manifest or (manifest['manifest'] and chunk_id not in manifest['manifest'].get('chunk_ids',[])):
                raise PartitionConflict('Chunk no longer belongs to the current source generation.')
            jobs=tx.query_jobs(source_id,s['generation'],chunk_id=chunk_id)
            for j in reversed(jobs):
                if j['status'] in {'pending_ai','running'}:
                    return job_dto(j)
            if any(j['status']=='completed' for j in jobs) and not reprocess:
                raise ValueError('Chunk already completed. Set reprocess=true to intentionally create a replacement extraction.')
            version=max((j['extraction_version'] for j in jobs),default=0)+1
            from datetime import datetime, timezone
            created=datetime.now(timezone.utc).isoformat()
            dto={'id':job_id,'source_id':source_id,'chunk_id':chunk_id,'status':'pending_ai',
                 'created_at':created,'completed_at':None,'schema_version':2,'extraction_version':version,
                 'asset_count':0,'provider':None,'model':None,'model_response_id':None,'error':None}
            return tx._one('INSERT INTO knowledge_engine.partition_jobs '
                           '(workspace_key,job_id,source_id,chunk_id,generation,extraction_version,metadata,created_at,api_payload,ordinal) '
                           'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'
                           '(SELECT coalesce(max(ordinal),-1)+1 FROM knowledge_engine.partition_jobs WHERE workspace_key=%s)) '
                           'RETURNING api_payload',
                           (tx.workspace,job_id,source_id,chunk_id,s['generation'],version,
                            Jsonb({k:v for k,v in dto.items() if k in META}),created,Jsonb(dto),tx.workspace))['api_payload']
        # Initialization of API projection is allowed separately from status transitions by SQL guard below.
        return self.apply(uuid4().hex,{'create':job_id,'source_id':source_id,'chunk_id':chunk_id},mutation).value

    def claim(self, job_id, provider, model, operation_id, token):
        def mutation(tx):
            self._require_active(tx)
            j=tx._expect(tx.read_job(job_id))
            row=tx.claim_job(job_id,j['generation'],j['revision'],token,provider=provider,model=model)
            self._require_active(tx)
            s=tx.read_source(j['source_id'])
            self._source_fields(tx,s,dict((s['api_payload'] or {}),processing_status='knowledge_interpreting',stopped_reason=None))
            return row
        return self.apply(operation_id,{'claim':job_id,'provider':provider,'model':model,'token':token},mutation)

    def _source_fields(self,tx,s,fields):
        fields=dict(fields)
        if 'generation' in fields: fields['generation']=s['generation']
        if 'deleted' in fields: fields['deleted']=s['deleted']
        tx._fence(s['source_id'],s['generation'])
        return tx._expect(tx._one('UPDATE knowledge_engine.partition_sources SET interpretation_status=%s,stopped_reason=%s,'
                                 'api_payload=%s,revision=revision+1,updated_at=now() WHERE workspace_key=%s AND source_id=%s '
                                 'AND revision=%s RETURNING revision',
                                 (fields.get('processing_status'),fields.get('stopped_reason'),Jsonb(fields),tx.workspace,s['source_id'],s['revision'])))

    def source_fields(self,source_id,fields,*,generation=None):
        def mutate(tx):
            self._require_active(tx)
            s=tx._expect(tx._json_record(tx._one('SELECT row_to_json(s) AS record FROM knowledge_engine.partition_sources s '
                                                'WHERE workspace_key=%s AND source_id=%s FOR UPDATE',(tx.workspace,source_id))))
            self._require_active(tx)
            if generation is not None and s['generation']!=generation:
                raise PartitionConflict('Source generation changed before finalization.')
            tx._fence(source_id,s['generation'])
            actual=dict(fields)
            if actual.get('processing_status') in {'knowledge_interpreting','knowledge_interpreted'}:
                summary=tx._one("SELECT s->'chunk_manifest'->'chunk_ids' AS ids FROM knowledge_engine.state_snapshots, "
                                "LATERAL jsonb_array_elements(payload->'sources') s WHERE workspace_key=%s AND s->>'id'=%s",
                                (tx.workspace,source_id))
                ids=(summary or {}).get('ids') or []
                completed=tx._one("SELECT count(DISTINCT chunk_id) AS n FROM knowledge_engine.partition_jobs "
                                 "WHERE workspace_key=%s AND source_id=%s AND generation=%s AND status='completed' AND chunk_id=ANY(%s)",
                                 (tx.workspace,source_id,s['generation'],ids))['n']
                if ids:
                    actual['processing_status']='knowledge_interpreted' if completed==len(ids) else 'knowledge_interpreting'
            return self._source_fields(tx,s,actual)
        return self.apply(uuid4().hex,{'source_id':source_id,'fields':fields},mutate).value

    def finish(self,claim,*,assets=None,response_id=None,error=None,on_committed=None):
        """Only completion with asset changes touches the core. Provider never runs here."""
        operation='finish:'+claim['claim_token']
        committed={}
        def mutation(tx):
            self._require_active(tx)
            core=self._core(tx) if assets is not None else None
            current_job=tx._running(claim['job_id'],claim['generation'],claim['revision'],claim['claim_token'])
            if any(current_job[k]!=claim[k] for k in ('source_id','chunk_id','extraction_version')):
                raise PartitionConflict('Captured job provenance changed.')
            self._require_active(tx)
            if assets is not None:
                payload=core['payload']
                for a in payload.get('knowledge_assets',[]):
                    if a['source_id']==claim['source_id'] and a['chunk_id']==claim['chunk_id'] and a.get('active',True):
                        a.update(active=False,superseded_by_job_id=claim['job_id'])
                payload.setdefault('knowledge_assets',[]).extend(deepcopy(assets))
                revision=self._cas(tx,payload,core['revision'])
                committed.update(payload=payload,revision=revision)
            row=tx.finish_job(claim['job_id'],claim['generation'],claim['revision'],claim['claim_token'],
                              status='failed' if assets is None else 'completed',
                              metadata={'error':error} if assets is None else {'error':None,'asset_count':len(assets),'model_response_id':response_id})
            if assets is not None:
                source=tx.read_source(claim['source_id'])
                core_source=next(s for s in core['payload']['sources'] if s['id']==claim['source_id'])
                ids=(core_source.get('chunk_manifest') or {}).get('chunk_ids')
                fields=dict(source['api_payload'] or {},stopped_reason=None)
                if ids:
                    completed=tx._one("SELECT count(DISTINCT chunk_id) AS n FROM knowledge_engine.partition_jobs "
                                     "WHERE workspace_key=%s AND source_id=%s AND generation=%s AND status='completed' AND chunk_id=ANY(%s)",
                                     (tx.workspace,claim['source_id'],claim['generation'],ids))['n']
                    fields['processing_status']='knowledge_interpreted' if completed==len(ids) else 'knowledge_interpreting'
                self._source_fields(tx,source,fields)
            return row
        request={'claim':claim,'assets':assets,'response_id':response_id,'error':error}
        try:
            for reconciliation in range(3):
                try:
                    result=self.apply(operation,request,mutation)
                    break
                except StaleStateWriteError:
                    committed.clear()
                    if reconciliation==2: raise
        except HostedStateStoreError:
            receipt=self.read_operation(operation)
            if receipt is None or receipt['request']!=request or not isinstance(receipt['result'],dict):
                raise
            result=PartitionMutation(receipt['result'],True)
            committed.clear()  # Do not trust local buffers after an uncertain commit.
        if on_committed is not None:
            if committed and not result.replayed:
                with self.transaction() as tx:
                    composed=self.compose(tx,committed['payload'])
                on_committed(composed,committed['revision'])
            elif result.replayed and assets is not None:
                with self.transaction() as tx:
                    latest=self._core(tx)
                    composed=self.compose(tx,latest['payload'])
                on_committed(composed,latest['revision'])
        return result

    def recover(self,job_id):
        def mutation(tx):
            self._require_active(tx)
            j=tx._expect(tx.read_job(job_id))
            row=tx.recover_job(job_id,j['generation'],j['revision'])
            self._require_active(tx)
            s=tx.read_source(j['source_id'])
            jobs=tx.query_jobs(j['source_id'],j['generation'])
            latest={j['chunk_id']:j for j in jobs}
            if not any(j['status'] in {'failed','running'} for j in latest.values()):
                fields=dict(s['api_payload'] or {});fields['stopped_reason']=None
                self._source_fields(tx,s,fields)
            return row
        return self.apply(uuid4().hex,{'recover':job_id},mutation).value

    def save_core(self,baseline,proposed,expected_revision):
        with self.transaction() as tx:
            core=self._core(tx,expected_revision)
            self._require_active(tx)
            old={s['id']:s for s in baseline.get('sources',[])}
            new={s['id']:s for s in proposed.get('sources',[])}
            for sid in sorted(old.keys()|new.keys()):
                before,after=old.get(sid),new.get(sid)
                s=tx._json_record(tx._one('SELECT row_to_json(s) AS record FROM knowledge_engine.partition_sources s '
                                         'WHERE workspace_key=%s AND source_id=%s FOR UPDATE',(tx.workspace,sid)))
                if before is None:
                    if s is not None:
                        raise PartitionConflict('Source ID is retained by a lifecycle fence.')
                    tx.create_source(sid);s=tx.read_source(sid)
                if after is None:
                    tx.advance_generation(sid,s['generation'],s['revision'],deleted=True)
                    # Keep the tombstone and receipts; logical deletion removes job records.
                    tx._all('DELETE FROM knowledge_engine.partition_jobs WHERE workspace_key=%s AND source_id=%s RETURNING job_id',
                            (tx.workspace,sid))
                    continue
                advanced=bool(before and any(before.get(k)!=after.get(k) for k in ('file_path','chunks_path','chunk_manifest')))
                if advanced:
                    tx.advance_generation(sid,s['generation'],s['revision']);s=tx.read_source(sid)
                fields=owned(after)
                if advanced or ((before is None or owned(before) != fields) and fields != (s['api_payload'] or {})):
                    if before is not None and not advanced and (s['api_payload'] or {}) not in (owned(before),fields):
                        raise PartitionConflict('Concurrent lifecycle fields changed; reload before saving.')
                    self._source_fields(tx,s,fields)
            payload=compact(proposed)
            revision=self._cas(tx,payload,expected_revision) if payload!=core['payload'] else expected_revision
            composed=self.compose(tx,payload)
        return revision,composed

    def rollback(self,expected_revision,*,writers_drained=False):
        if not writers_drained:
            raise PartitionConflict('Rollback requires explicitly drained writers.')
        with self.transaction() as tx:
            core=self._core(tx,expected_revision);self._require_active(tx)
            tx._all('SELECT source_id FROM knowledge_engine.partition_sources WHERE workspace_key=%s ORDER BY source_id FOR UPDATE',(tx.workspace,))
            if tx._one("SELECT j.job_id FROM knowledge_engine.partition_jobs j JOIN knowledge_engine.partition_sources s USING(workspace_key,source_id) "
                       "WHERE j.workspace_key=%s AND j.status='running' AND j.generation=s.generation AND NOT s.deleted",
                       (tx.workspace,)):
                raise PartitionConflict('Running jobs prevent rollback.')
            state=self.compose(tx,core['payload'],include_jobs=True,history=True)
            fences=tx._all('SELECT source_id,generation FROM knowledge_engine.partition_sources WHERE workspace_key=%s AND NOT deleted',
                           (tx.workspace,))
            generations={s['source_id']:s['generation'] for s in fences}
            multi={j['source_id'] for j in state['extraction_jobs'] if j.get('extraction_version',1)>1}
            for source in state['sources']:
                if generations[source['id']]>1 or source['id'] in multi:source['generation']=generations[source['id']]
            rows=tx._all('SELECT job_id,generation FROM knowledge_engine.partition_jobs WHERE workspace_key=%s',(tx.workspace,))
            job_generations={j['job_id']:j['generation'] for j in rows}
            for job in state['extraction_jobs']:
                if generations[job['source_id']]>1:job['generation']=job_generations[job['id']]
            state.pop('partition',None)
            tx.connection.execute("SELECT set_config('knowledge_engine.phase2_rollback','on',true)")
            revision=self._cas(tx,state,expected_revision)
        return {'revision':revision,'payload':state}

    def history_jobs(self,source_id=None):
        with self.transaction() as tx:
            return [r['api_payload'] for r in tx._all('SELECT j.api_payload FROM knowledge_engine.partition_jobs j '
                'JOIN knowledge_engine.partition_sources s USING(workspace_key,source_id) '
                'WHERE j.workspace_key=%s AND NOT s.deleted AND (%s::text IS NULL OR j.source_id=%s) '
                'ORDER BY j.ordinal,j.job_id',(tx.workspace,source_id,source_id))]

    def asset_counts(self,source_ids):
        with self.transaction() as tx:
            rows=tx._all("SELECT a->>'source_id' AS source_id,count(*) AS n FROM knowledge_engine.state_snapshots, "
                         "LATERAL jsonb_array_elements(payload->'knowledge_assets') a WHERE workspace_key=%s "
                         "AND a->>'source_id'=ANY(%s) AND coalesce((a->>'active')::boolean,true) GROUP BY a->>'source_id'",
                         (tx.workspace,source_ids))
            return {r['source_id']:r['n'] for r in rows}

    def history_sources(self,source_ids):
        with self.transaction() as tx:
            return {r['source_id'] for r in tx._all('SELECT DISTINCT source_id FROM knowledge_engine.partition_jobs '
                                                   'WHERE workspace_key=%s AND source_id=ANY(%s)',(tx.workspace,source_ids))}


def rebase_projection(base,local,latest):
    from app.persistence.reconciliation import StateReconciliationConflict
    result=merge_state_snapshots(compact(base),compact(local),compact(latest))
    before={s['id']:s for s in base.get('sources',[])}
    ours={s['id']:s for s in local.get('sources',[])}
    theirs={s['id']:s for s in latest.get('sources',[])}
    for source in result.get('sources',[]):
        sid=source['id']
        fields=owned(theirs.get(sid,{}))
        proposed=owned(ours.get(sid,{}));previous=owned(before.get(sid,{}))
        if proposed!=previous:
            if fields not in (previous,proposed):
                raise StateReconciliationConflict('Concurrent lifecycle fields changed.')
            fields=proposed
        source.update(fields)
    return result
