"""Explicit v3 assets/jobs/lifecycle authority and migration coordinator.

Construction is dormant. Migration, cutover and rollback methods are explicit;
no provider work runs while a PostgreSQL transaction is open.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.persistence.phase2 import (
    Phase2Coordinator, VERSION as PHASE2_VERSION, MARKER as PHASE2_MARKER,
    OWNED, META, job_dto, source_projection,
)
from app.persistence.partitions import PartitionConflict, PartitionMutation, PartitionVersionError
from app.persistence.postgres import StaleStateWriteError, HostedStateStoreError

VERSION = 3
DOMAINS = ['jobs', 'source_lifecycle', 'assets']
MARKER = {'version': VERSION, 'state': 'active', 'domains': DOMAINS}


def active(state):
    if not state or 'partition' not in state:
        return False
    if state['partition'] == MARKER:
        return True
    raise PartitionVersionError('Unsupported or incompatible partition authority marker.')


def compact(state):
    core = deepcopy(state)
    core.pop('extraction_jobs', None)
    core.pop('knowledge_assets', None)
    core['sources'] = [{k: v for k, v in s.items() if k not in OWNED} for s in state.get('sources', [])]
    core['partition'] = deepcopy(MARKER)
    return core


def authority_version(state):
    marker = (state or {}).get('partition')
    if marker is None:
        return 0
    if marker == PHASE2_MARKER:
        return 2
    if marker == MARKER:
        return 3
    raise PartitionVersionError('Unsupported or malformed partition authority marker.')


def _time(value, fallback=None):
    if value is None:
        value = fallback
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _canonical_hash(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _dto(row):
    return deepcopy(row['payload'])


class AssetProvenanceError(PartitionConflict):
    """Legacy asset provenance cannot be mapped without guessing."""


class Phase3Coordinator(Phase2Coordinator):
    """Version-3 authority. It reuses Phase 2 job/lifecycle tables unchanged."""
    version = VERSION

    def _require_active(self, tx):
        row = tx._one("SELECT payload->'partition' AS marker FROM knowledge_engine.state_snapshots "
                      "WHERE workspace_key=%s FOR SHARE", (tx.workspace,))
        if not row or row['marker'] != MARKER:
            raise PartitionConflict('V3 jobs/assets/source authority changed; reload before continuing.')

    def read_source(self, source_id):
        with self.transaction() as tx:
            self._require_active(tx)
            return tx.read_source(source_id)

    def read_job(self, job_id):
        with self.transaction() as tx:
            self._require_active(tx)
            return tx.read_job(job_id)

    def query_jobs(self, source_id, generation, *, chunk_id=None):
        with self.transaction() as tx:
            self._require_active(tx)
            return tx.query_jobs(source_id, generation, chunk_id=chunk_id)

    def query_assets(self, source_id, generation, *, chunk_id=None, active=None):
        with self.transaction() as tx:
            self._require_active(tx)
            return tx.query_assets(source_id, generation, chunk_id=chunk_id, active=active)

    def assets_by_ids(self, asset_ids):
        if not asset_ids:
            return []
        with self.transaction() as tx:
            self._require_active(tx)
            return tx.assets_by_ids(asset_ids)

    def _require_v2_core(self, tx, expected_revision=None):
        core = self._core(tx, expected_revision)
        if core['payload'].get('partition') != PHASE2_MARKER:
            raise PartitionConflict('V3 asset migration requires active v2 job/lifecycle authority.')
        return core

    def _provenance_inputs(self, tx):
        sources = tx._all('SELECT source_id,generation,deleted FROM knowledge_engine.partition_sources '
                          'WHERE workspace_key=%s ORDER BY source_id', (tx.workspace,))
        jobs = tx._all('SELECT job_id,source_id,chunk_id,generation,extraction_version FROM '
                       'knowledge_engine.partition_jobs WHERE workspace_key=%s '
                       'ORDER BY job_id,source_id,chunk_id,generation,extraction_version', (tx.workspace,))
        return {
            'sources': [{'source_id': r['source_id'], 'generation': r['generation'], 'deleted': r['deleted']}
                        for r in sources],
            'jobs': [{'job_id': r['job_id'], 'source_id': r['source_id'], 'chunk_id': r['chunk_id'],
                      'generation': r['generation'], 'extraction_version': r['extraction_version']}
                     for r in jobs],
        }

    def _lock_provenance(self, tx):
        # Job creation and lifecycle transitions already lock their source row.
        # Holding these rows for each short migration transaction stabilizes
        # the canonical mapping without a workspace lock or provider overlap.
        tx._all('SELECT source_id FROM knowledge_engine.partition_sources '
                'WHERE workspace_key=%s ORDER BY source_id FOR UPDATE', (tx.workspace,))

    def provenance_fingerprint(self, tx=None):
        if tx is not None:
            return _canonical_hash(self._provenance_inputs(tx))
        with self.transaction() as owned:
            return _canonical_hash(self._provenance_inputs(owned))

    def _migration(self, tx, expected_revision=None, stage=None):
        row = tx._one('SELECT * FROM knowledge_engine.partition_v3_migrations '
                      'WHERE workspace_key=%s FOR UPDATE', (tx.workspace,))
        if row is None:
            raise PartitionConflict('No Phase 3 migration attempt exists.')
        if row['partition_version'] != VERSION:
            raise PartitionVersionError('Unsupported Phase 3 migration version.')
        if expected_revision is not None and row['source_snapshot_revision'] != expected_revision:
            raise PartitionConflict('Phase 3 core snapshot pin changed.')
        if stage and row['stage'] != stage:
            raise PartitionConflict('Phase 3 migration is not in the required stage.')
        return row

    @staticmethod
    def _require_attempt_authority(core, migration):
        marker=core['payload'].get('partition')
        if migration['source_authority']=='v2' and marker!=PHASE2_MARKER:
            raise PartitionConflict('V3 attempt requires its pinned v2 source authority.')
        if migration['source_authority']=='legacy_rollback' and marker is not None:
            raise PartitionConflict('Re-cutover attempt requires legacy authority after rollback.')

    def _assert_pins(self, tx, core, migration):
        if core['revision'] != migration['source_snapshot_revision']:
            raise PartitionConflict('Phase 3 core snapshot revision drift invalidated this attempt.')
        fingerprint = self.provenance_fingerprint(tx)
        if fingerprint != migration['provenance_fingerprint']:
            raise PartitionConflict('Phase 3 provenance drift invalidated this attempt.')

    def _source_job_maps(self, tx):
        source_rows = tx._all('SELECT source_id,generation,deleted FROM knowledge_engine.partition_sources '
                              'WHERE workspace_key=%s ORDER BY source_id', (tx.workspace,))
        job_rows = tx._all('SELECT job_id,source_id,chunk_id,generation,extraction_version,status '
                           'FROM knowledge_engine.partition_jobs WHERE workspace_key=%s ORDER BY job_id',
                           (tx.workspace,))
        return ({r['source_id']: r for r in source_rows}, {r['job_id']: r for r in job_rows}, job_rows)

    @staticmethod
    def _resolve_asset(asset, source_map, job_map, jobs):
        aid = asset.get('id')
        source_id, chunk_id = asset.get('source_id'), asset.get('chunk_id')
        if not aid or not source_id or not chunk_id:
            raise AssetProvenanceError(f'Asset {aid or "<missing-id>"}: source/chunk identity is incomplete.')
        source = source_map.get(source_id)
        if source is None or source['deleted']:
            raise AssetProvenanceError(f'Asset {aid}: source is missing or deleted.')
        explicit_job = asset.get('extraction_job_id') or asset.get('job_id')
        explicit_generation = asset.get('generation', asset.get('source_generation'))
        explicit_version = asset.get('extraction_version')
        if explicit_job:
            candidates = [job_map.get(explicit_job)]
        else:
            candidates = [j for j in jobs if j['source_id'] == source_id and j['chunk_id'] == chunk_id]
        candidates = [j for j in candidates if j is not None and j['source_id'] == source_id
                      and j['chunk_id'] == chunk_id and j['status'] == 'completed'
                      and (explicit_generation is None or j['generation'] == int(explicit_generation))
                      and (explicit_version is None or j['extraction_version'] == int(explicit_version))]
        if len(candidates) != 1:
            qualifier = 'no defensible provenance match' if not candidates else 'ambiguous provenance match'
            raise AssetProvenanceError(f'Asset {aid}: {qualifier} among immutable Phase 2 jobs.')
        job = candidates[0]
        if job['generation'] > source['generation']:
            raise AssetProvenanceError(f'Asset {aid}: job generation is ahead of the source fence.')
        for key, expected in (('source_id', source_id), ('chunk_id', chunk_id)):
            if job[key] != expected:
                raise AssetProvenanceError(f'Asset {aid}: job {key} does not match asset provenance.')
        if explicit_generation is not None and job['generation'] != int(explicit_generation):
            raise AssetProvenanceError(f'Asset {aid}: explicit generation conflicts with its job.')
        return job

    def _asset_record(self, asset, ordinal, source_map, job_map, jobs):
        job = self._resolve_asset(asset, source_map, job_map, jobs)
        active = asset.get('active', True)
        if not isinstance(active, bool):
            raise AssetProvenanceError(f"Asset {asset['id']}: active state is invalid.")
        version = int(asset.get('extraction_version', job['extraction_version']))
        if version != job['extraction_version']:
            raise AssetProvenanceError(f"Asset {asset['id']}: extraction version conflicts with its job.")
        return {
            'asset_id': asset['id'], 'source_id': asset['source_id'], 'chunk_id': asset['chunk_id'],
            'generation': job['generation'], 'extraction_version': version, 'job_id': job['job_id'],
            'active': active, 'superseded_by_job_id': asset.get('superseded_by_job_id'),
            'revision': 1, 'payload': asset, 'created_at': _time(asset.get('created_at'), job.get('created_at')),
            'ordinal': ordinal,
        }

    def prepare(self, expected_revision, attempt_id):
        with self.transaction() as tx:
            core = self._require_v2_core(tx, expected_revision)
            self._lock_provenance(tx)
            fingerprint = self.provenance_fingerprint(tx)
            existing = tx._one('SELECT * FROM knowledge_engine.partition_v3_migrations '
                               'WHERE workspace_key=%s FOR UPDATE', (tx.workspace,))
            if existing:
                if (existing['attempt_id'] != attempt_id or existing['source_snapshot_revision'] != expected_revision
                        or existing['provenance_fingerprint'] != fingerprint or existing['partition_version'] != VERSION):
                    raise PartitionConflict('A different or drifted v3 attempt already exists.')
                return {'stage': existing['stage'], 'checkpoint': existing['checkpoint'],
                        'attempt_id': existing['attempt_id'], 'provenance_fingerprint': fingerprint}
            tx._one('INSERT INTO knowledge_engine.partition_v3_migrations '
                    '(workspace_key,attempt_id,source_snapshot_revision,provenance_fingerprint) '
                    'VALUES (%s,%s,%s,%s) RETURNING attempt_id',
                    (tx.workspace, attempt_id, core['revision'], fingerprint))
            return {'stage': 'preparing', 'checkpoint': {}, 'attempt_id': attempt_id,
                    'provenance_fingerprint': fingerprint}

    def _archive_attempt(self, tx, migration, reason):
        tx._one('INSERT INTO knowledge_engine.partition_v3_migration_history '
                '(workspace_key,attempt_id,partition_version,source_authority,source_snapshot_revision,provenance_fingerprint,'
                'stage,checkpoint,migration_revision,started_at,verified_at,cutover_revision,terminal_reason) '
                'VALUES (%s,%s,3,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING attempt_id',
                (tx.workspace, migration['attempt_id'], migration['source_authority'],migration['source_snapshot_revision'],
                 migration['provenance_fingerprint'], migration['stage'], Jsonb(migration['checkpoint']),
                 migration['revision'], migration['started_at'], migration['verified_at'],
                 migration['cutover_revision'], reason))

    def restart_after_revision_drift(self, expected_revision, expected_attempt_id,
                                     expected_pinned_revision, expected_fingerprint, new_attempt_id,
                                     *, writers_drained=False):
        if not writers_drained:
            raise PartitionConflict('Migration restart requires explicitly drained writers.')
        with self.transaction() as tx:
            core = self._core(tx, expected_revision)
            self._lock_provenance(tx)
            old = self._migration(tx, stage='preparing')
            self._require_attempt_authority(core,old)
            new_fingerprint = self.provenance_fingerprint(tx)
            if (old['attempt_id'] != expected_attempt_id
                    or old['source_snapshot_revision'] != expected_pinned_revision
                    or old['provenance_fingerprint'] != expected_fingerprint
                    or (old['source_snapshot_revision'] == core['revision'] and old['provenance_fingerprint'] == new_fingerprint)
                    or new_attempt_id == old['attempt_id']):
                raise PartitionConflict('Expected drifted Phase 3 preparing attempt does not match.')
            tx.execute("SELECT set_config('knowledge_engine.phase3_drift_restart','on',true)")
            self._archive_attempt(tx, old, 'revision_drift')
            tx._one('UPDATE knowledge_engine.partition_v3_migrations SET attempt_id=%s,source_snapshot_revision=%s,'
                    'provenance_fingerprint=%s,stage=\'preparing\',checkpoint=\'{}\'::jsonb,revision=revision+1,'
                    'started_at=now(),verified_at=NULL,cutover_revision=NULL,updated_at=now() '
                    'WHERE workspace_key=%s RETURNING revision',
                    (new_attempt_id, core['revision'], new_fingerprint, tx.workspace))
            return {'attempt_id': new_attempt_id, 'stage': 'preparing', 'checkpoint': {},
                    'source_snapshot_revision': core['revision'], 'provenance_fingerprint': new_fingerprint}

    def _all_assets(self, payload):
        return payload.get('knowledge_assets', [])

    def backfill(self, expected_revision, *, max_assets=200):
        if max_assets < 1:
            raise ValueError('max_assets must be positive.')
        with self.transaction() as tx:
            core = self._core(tx, expected_revision)
            migration = self._migration(tx, expected_revision, 'preparing')
            self._require_attempt_authority(core,migration)
            self._lock_provenance(tx)
            self._assert_pins(tx, core, migration)
            source_map, job_map, jobs = self._source_job_maps(tx)
            assets = self._all_assets(core['payload'])
            if len({a.get('id') for a in assets}) != len(assets):
                raise AssetProvenanceError('Legacy asset array contains duplicate asset IDs.')
            start = int(migration['checkpoint'].get('next_ordinal', 0))
            batch = assets[start:start + max_assets]
            values = [self._asset_record(asset, start + offset, source_map, job_map, jobs)
                      for offset, asset in enumerate(batch)]
            tx.execute("SELECT set_config('knowledge_engine.phase3_backfill','on',true)")
            tx.execute("SELECT set_config('knowledge_engine.phase3_backfill_workspace',%s,true)",
                       (tx.workspace,))
            ids = [v['asset_id'] for v in values]
            existing = tx._all('SELECT * FROM knowledge_engine.partition_assets '
                               'WHERE workspace_key=%s AND asset_id=ANY(%s) FOR UPDATE', (tx.workspace, ids)) if ids else []
            existing_by_id = {r['asset_id']: r for r in existing}
            for value in values:
                row = existing_by_id.get(value['asset_id'])
                if row is not None and any(row[key] != value[key] for key in (
                        'source_id','chunk_id','generation','extraction_version','job_id','active',
                        'superseded_by_job_id','ordinal','payload')):
                    raise PartitionConflict(f"Existing v3 asset {value['asset_id']} differs from pinned legacy data.")
            new_values = [dict(v,created_at=(v['created_at'].isoformat() if v['created_at'] else None))
                          for v in values if v['asset_id'] not in existing_by_id]
            if new_values:
                tx._all('INSERT INTO knowledge_engine.partition_assets '
                        '(workspace_key,asset_id,source_id,chunk_id,generation,extraction_version,job_id,active,'
                        'superseded_by_job_id,revision,payload,created_at,ordinal) '
                        'SELECT %s,v.asset_id,v.source_id,v.chunk_id,v.generation,v.extraction_version,v.job_id,v.active,'
                        'v.superseded_by_job_id,v.revision,v.payload,v.created_at,v.ordinal '
                        'FROM jsonb_to_recordset(%s) AS v(asset_id text,source_id text,chunk_id text,generation bigint,'
                        'extraction_version bigint,job_id text,active boolean,superseded_by_job_id text,revision bigint,'
                        'payload jsonb,created_at timestamptz,ordinal bigint) RETURNING asset_id',
                        (tx.workspace, Jsonb(new_values)))
            next_ordinal = start + len(batch)
            tx._one('INSERT INTO knowledge_engine.partition_asset_order(workspace_key,next_ordinal) VALUES (%s,%s) '
                    'ON CONFLICT(workspace_key) DO UPDATE SET next_ordinal=GREATEST('
                    'knowledge_engine.partition_asset_order.next_ordinal,EXCLUDED.next_ordinal),'
                    'revision=knowledge_engine.partition_asset_order.revision+1,updated_at=now() RETURNING next_ordinal',
                    (tx.workspace, next_ordinal))
            checkpoint = {'next_ordinal': next_ordinal}
            tx._one('UPDATE knowledge_engine.partition_v3_migrations SET checkpoint=%s,revision=revision+1,updated_at=now() '
                    'WHERE workspace_key=%s RETURNING revision', (Jsonb(checkpoint), tx.workspace))
            return checkpoint

    def _verify_assets(self, tx, payload):
        assets = self._all_assets(payload)
        source_map, job_map, jobs = self._source_job_maps(tx)
        if len({a.get('id') for a in assets}) != len(assets):
            raise AssetProvenanceError('Legacy asset array contains duplicate asset IDs.')
        expected = [self._asset_record(asset, index, source_map, job_map, jobs)
                    for index, asset in enumerate(assets)]
        actual = tx._all('SELECT * FROM knowledge_engine.partition_assets WHERE workspace_key=%s ORDER BY ordinal,asset_id',
                         (tx.workspace,))
        if len(actual) != len(expected):
            raise PartitionConflict('Asset equivalence verification failed: missing or extra rows.')
        for wanted, row in zip(expected, actual):
            for key in ('asset_id','source_id','chunk_id','generation','extraction_version','job_id',
                        'active','superseded_by_job_id','ordinal','payload','created_at'):
                if row[key] != wanted[key]:
                    raise PartitionConflict(f"Asset equivalence verification failed for {wanted['asset_id']} ({key}).")
        active_versions = {}
        for row in actual:
            if row['active']:
                key=(row['source_id'],row['generation'],row['chunk_id'])
                active_versions.setdefault(key,set()).add(row['extraction_version'])
        if any(len(versions)>1 for versions in active_versions.values()):
            raise PartitionConflict('Asset equivalence verification failed: mixed active extraction versions.')
        order = tx._one('SELECT next_ordinal FROM knowledge_engine.partition_asset_order WHERE workspace_key=%s',
                        (tx.workspace,))
        if (order is None and expected) or (order and order['next_ordinal'] < len(expected)):
            raise PartitionConflict('Asset order allocator is behind the verified legacy order.')

    def verify(self, expected_revision):
        with self.transaction() as tx:
            core=self._core(tx,expected_revision)
            migration=self._migration(tx,expected_revision,'preparing')
            self._require_attempt_authority(core,migration)
            self._lock_provenance(tx)
            self._assert_pins(tx,core,migration)
            expected_count=len(self._all_assets(core['payload']))
            if migration['checkpoint'].get('next_ordinal',0) != expected_count:
                raise PartitionConflict('Asset backfill checkpoint is incomplete.')
            self._verify_assets(tx,core['payload'])
            tx._one("UPDATE knowledge_engine.partition_v3_migrations SET stage='verified',verified_at=now(),"
                    'revision=revision+1,updated_at=now() WHERE workspace_key=%s RETURNING revision',(tx.workspace,))
            return {'stage':'verified','attempt_id':migration['attempt_id']}

    def cutover(self, expected_revision, *, writers_drained=False):
        if not writers_drained:
            raise PartitionConflict('Cutover requires explicitly drained writers.')
        with self.transaction() as tx:
            core=self._core(tx,expected_revision)
            migration=self._migration(tx,expected_revision,'verified')
            self._require_attempt_authority(core,migration)
            self._lock_provenance(tx)
            self._assert_pins(tx,core,migration)
            self._verify_assets(tx,core['payload'])
            running=tx._one("SELECT j.job_id FROM knowledge_engine.partition_jobs j "
                             "JOIN knowledge_engine.partition_sources s USING(workspace_key,source_id) "
                             "WHERE j.workspace_key=%s AND j.status='running' AND j.generation=s.generation AND NOT s.deleted LIMIT 1",
                             (tx.workspace,))
            if running:
                raise PartitionConflict('Current-generation running jobs prevent v3 cutover.')
            tx.execute("SELECT set_config('knowledge_engine.phase3_cutover','on',true)")
            payload=compact(core['payload'])
            revision=self._cas(tx,payload,expected_revision)
            tx._one('UPDATE knowledge_engine.partition_v3_migrations SET cutover_revision=%s,revision=revision+1,'
                    'updated_at=now() WHERE workspace_key=%s RETURNING revision',(revision,tx.workspace))
            return {'revision':revision,'payload':payload,'attempt_id':migration['attempt_id']}

    def _dto_for_row(self, row):
        return deepcopy(row['payload'])

    def compose(self, tx, core, *, source_ids=None, include_jobs=False, generations=None,
                history=False, include_assets=False):
        state=deepcopy(core)
        ids=source_ids if source_ids is not None else [s['id'] for s in state.get('sources',[])]
        rows=tx._all('SELECT source_id,api_payload,deleted,generation FROM knowledge_engine.partition_sources '
                     'WHERE workspace_key=%s AND source_id=ANY(%s)',(tx.workspace,ids)) if ids else []
        mapping={s['source_id']:s for s in rows}
        if generations is not None:generations.update({s['source_id']:s['generation'] for s in rows})
        state['sources']=[s | (mapping[s['id']]['api_payload'] or {}) for s in state.get('sources',[])
                          if s['id'] in mapping and not mapping[s['id']]['deleted']]
        if include_jobs:
            state['extraction_jobs']=[r['api_payload'] for r in tx._all(
                'SELECT j.api_payload FROM knowledge_engine.partition_jobs j JOIN knowledge_engine.partition_sources s '
                'USING(workspace_key,source_id) WHERE j.workspace_key=%s AND j.source_id=ANY(%s) AND NOT s.deleted '
                'AND (j.generation=s.generation OR %s) ORDER BY j.ordinal,j.job_id',(tx.workspace,ids,history))]
        if include_assets:
            state['knowledge_assets']=[r['payload'] for r in tx._all(
                'SELECT a.payload FROM knowledge_engine.partition_assets a '
                'JOIN knowledge_engine.partition_sources s USING(workspace_key,source_id) '
                'WHERE a.workspace_key=%s AND a.source_id=ANY(%s) AND NOT s.deleted '
                'AND (a.generation=s.generation OR %s) ORDER BY a.ordinal,a.asset_id',(tx.workspace,ids,history))]
        else:
            state['knowledge_assets']=[]
        return state

    def _assert_v3_marker(self, tx):
        row=tx._one("SELECT payload->'partition' AS marker FROM knowledge_engine.state_snapshots "
                    'WHERE workspace_key=%s FOR SHARE',(tx.workspace,))
        if not row or row['marker']!=MARKER:
            raise PartitionConflict('V3 authority marker changed.')

    def active_assets(self, *, source_ids=None, chunk_id=None, asset_type=None, asset_ids=None):
        with self.transaction() as tx:
            self._assert_v3_marker(tx)
            clauses=['a.workspace_key=%s','a.active','NOT s.deleted','a.generation=s.generation']
            params=[tx.workspace]
            if source_ids is not None:
                clauses.append('a.source_id=ANY(%s)');params.append(list(source_ids))
            if chunk_id is not None:
                clauses.append('a.chunk_id=%s');params.append(chunk_id)
            if asset_type is not None:
                clauses.append("a.payload->>'asset_type'=%s");params.append(asset_type)
            if asset_ids is not None:
                clauses.append('a.asset_id=ANY(%s)');params.append(list(asset_ids))
            rows=tx._all('SELECT a.payload FROM knowledge_engine.partition_assets a '
                         'JOIN knowledge_engine.partition_sources s USING(workspace_key,source_id) WHERE '
                         +' AND '.join(clauses)+' ORDER BY a.ordinal,a.asset_id',tuple(params))
            return [r['payload'] for r in rows]

    def search_candidates(self, tokens, normalized_query, *, source_ids=None, source_id=None,
                          asset_type=None, limit=None):
        """Exact-match superset query; no candidate limit until indexed parity is proven."""
        if not tokens:return []
        with self.transaction() as tx:
            self._assert_v3_marker(tx)
            clauses=['a.workspace_key=%s','a.active','NOT s.deleted','a.generation=s.generation']
            params=[tx.workspace]
            if source_id is not None:
                clauses.append('a.source_id=%s');params.append(source_id)
            if source_ids is not None:
                clauses.append('a.source_id=ANY(%s)');params.append(list(source_ids))
            if asset_type is not None:
                clauses.append("a.payload->>'asset_type'=%s");params.append(asset_type)
            fields="regexp_replace(lower(a.payload::text),'[^a-z0-9]+',' ','g')"
            terms=[]
            if normalized_query:
                terms.append(f'position(%s in {fields})>0');params.append(normalized_query)
            for token in tokens:
                terms.append(f'position(%s in {fields})>0');params.append(token)
            clauses.append('('+' OR '.join(terms)+')')
            rows=tx._all('SELECT a.payload FROM knowledge_engine.partition_assets a '
                         'JOIN knowledge_engine.partition_sources s USING(workspace_key,source_id) WHERE '
                         +' AND '.join(clauses)+' ORDER BY a.ordinal,a.asset_id',tuple(params))
            return [r['payload'] for r in rows]

    def active_assets_many(self, source_ids):
        if not source_ids:return []
        return self.active_assets(source_ids=source_ids)

    def assets_by_ids(self, asset_ids, *, history=False):
        if not asset_ids:return []
        with self.transaction() as tx:
            self._require_active(tx)
            return [r['payload'] for r in tx._all(
                'SELECT a.payload FROM knowledge_engine.partition_assets a '
                'JOIN knowledge_engine.partition_sources s USING(workspace_key,source_id) '
                'WHERE a.workspace_key=%s AND a.asset_id=ANY(%s) AND NOT s.deleted '
                'AND (%s OR (a.active AND a.generation=s.generation)) ORDER BY a.ordinal,a.asset_id',
                (tx.workspace,list(asset_ids),history))]

    def asset_counts(self, source_ids):
        if not source_ids:return {}
        with self.transaction() as tx:
            self._assert_v3_marker(tx)
            rows=tx._all('SELECT a.source_id,count(*) AS n FROM knowledge_engine.partition_assets a '
                         'JOIN knowledge_engine.partition_sources s USING(workspace_key,source_id) '
                         'WHERE a.workspace_key=%s AND a.source_id=ANY(%s) AND a.active AND NOT s.deleted '
                         'AND a.generation=s.generation GROUP BY a.source_id',(tx.workspace,list(source_ids)))
            return {r['source_id']:r['n'] for r in rows}

    def summary_state(self, source_ids):
        """One transaction batches current jobs, active counts and history flags."""
        if not source_ids:return {'jobs':[],'asset_counts':{},'history_sources':set()}
        with self.transaction() as tx:
            self._require_active(tx)
            jobs=[r['api_payload'] for r in tx._all('SELECT j.api_payload FROM knowledge_engine.partition_jobs j '
                'JOIN knowledge_engine.partition_sources s USING(workspace_key,source_id) '
                'WHERE j.workspace_key=%s AND j.source_id=ANY(%s) AND NOT s.deleted AND j.generation=s.generation '
                'ORDER BY j.ordinal,j.job_id',(tx.workspace,list(source_ids)))]
            counts=tx._all('SELECT a.source_id,count(*) AS n FROM knowledge_engine.partition_assets a '
                'JOIN knowledge_engine.partition_sources s USING(workspace_key,source_id) '
                'WHERE a.workspace_key=%s AND a.source_id=ANY(%s) AND a.active AND NOT s.deleted '
                'AND a.generation=s.generation GROUP BY a.source_id',(tx.workspace,list(source_ids)))
            history=tx._all('SELECT DISTINCT source_id FROM knowledge_engine.partition_jobs '
                'WHERE workspace_key=%s AND source_id=ANY(%s)',(tx.workspace,list(source_ids)))
            return {'jobs':jobs,'asset_counts':{r['source_id']:r['n'] for r in counts},
                    'history_sources':{r['source_id'] for r in history}}

    def enrich_current_assets(self, source_id, updates):
        """Apply only current-generation active payload enrichment in one set update."""
        if not updates:return 0
        if not isinstance(updates,dict):raise ValueError('Asset enrichment must be an ID-to-patch object.')
        op='asset-enrichment:'+uuid4().hex
        def mutate(tx):
            self._require_active(tx)
            source=tx._expect(tx._one('SELECT generation,deleted,revision FROM knowledge_engine.partition_sources '
                                      'WHERE workspace_key=%s AND source_id=%s FOR UPDATE',(tx.workspace,source_id)))
            if source['deleted']:raise PartitionConflict('Cannot enrich a deleted source.')
            ids=list(updates)
            if not ids:return {'updated':0}
            rows=tx._all('UPDATE knowledge_engine.partition_assets a SET payload=a.payload || v.patch,'
                         'revision=a.revision+1,updated_at=now() FROM jsonb_to_recordset(%s) '
                         'AS v(asset_id text,patch jsonb) WHERE a.workspace_key=%s AND a.source_id=%s '
                         'AND a.asset_id=v.asset_id AND a.active AND a.generation=%s RETURNING a.asset_id',
                         (Jsonb([{'asset_id':aid,'patch':patch} for aid,patch in updates.items()]),
                          tx.workspace,source_id,source['generation']))
            if len(rows)!=len(ids):raise PartitionConflict('An enriched asset is no longer current and active.')
            return {'updated':len(rows)}
        return self.apply(op,{'source_id':source_id,'updates':updates},mutate).value['updated']

    def finish(self, claim, *, assets=None, response_id=None, error=None, on_committed=None):
        operation='finish:'+claim['claim_token']
        request={'claim':claim,'assets':assets,'response_id':response_id,'error':error}
        def mutation(tx):
            self._require_active(tx)
            # Fixed order: receipt (apply), source fence, job row, then asset rows.
            identity=tx._expect(tx.read_job(claim['job_id']))
            if any(identity[k]!=claim[k] for k in ('source_id','chunk_id','generation','extraction_version')):
                raise PartitionConflict('Captured job provenance changed.')
            source=tx._expect(tx._one('SELECT * FROM knowledge_engine.partition_sources WHERE workspace_key=%s '
                                      'AND source_id=%s FOR UPDATE',(tx.workspace,claim['source_id'])))
            if source['deleted'] or source['generation']!=claim['generation']:
                raise PartitionConflict('Source is deleted or interpretation generation is stale.')
            job=tx._running(claim['job_id'],claim['generation'],claim['revision'],claim['claim_token'])
            if any(job[k]!=claim[k] for k in ('source_id','chunk_id','extraction_version')):
                raise PartitionConflict('Captured job provenance changed.')
            outcome='failed' if assets is None else 'completed'
            if assets is not None:
                active_rows=tx._all('SELECT extraction_version FROM knowledge_engine.partition_assets '
                                    'WHERE workspace_key=%s AND source_id=%s AND generation=%s AND chunk_id=%s '
                                    'AND active ORDER BY asset_id FOR UPDATE',
                                    (tx.workspace,job['source_id'],job['generation'],job['chunk_id']))
                versions={row['extraction_version'] for row in active_rows}
                completed=tx._one("SELECT job_id,extraction_version,CASE "
                                  "WHEN metadata->>'asset_count' ~ '^[0-9]+$' "
                                  "THEN (metadata->>'asset_count')::integer ELSE 0 END AS asset_count "
                                  "FROM knowledge_engine.partition_jobs WHERE workspace_key=%s AND source_id=%s "
                                  "AND generation=%s AND chunk_id=%s AND status='completed' AND job_id<>%s "
                                  "ORDER BY extraction_version DESC LIMIT 1",
                                  (tx.workspace,job['source_id'],job['generation'],job['chunk_id'],job['job_id']))
                prior_version=completed['extraction_version'] if completed else None
                if (len(versions)>1 or (versions and versions!={prior_version})
                        or (completed and completed['asset_count']!=len(active_rows))
                        or (not completed and active_rows)):
                    raise PartitionConflict('Existing active extraction versions are mixed or inconsistent.')
                if prior_version is not None and prior_version>=job['extraction_version']:
                    raise PartitionConflict('A newer extraction version is already complete.')
                tx._all("UPDATE knowledge_engine.partition_assets SET active=false,superseded_by_job_id=%s,"
                        "payload=jsonb_set(jsonb_set(payload,'{active}','false'::jsonb,true),'{superseded_by_job_id}',to_jsonb(%s::text),true),"
                        'revision=revision+1,updated_at=now() WHERE workspace_key=%s AND source_id=%s '
                        'AND generation=%s AND chunk_id=%s AND active RETURNING asset_id',
                        (job['job_id'],job['job_id'],tx.workspace,job['source_id'],job['generation'],job['chunk_id']))
                values=[]
                for asset in assets:
                    value=dict(asset)
                    if (value.get('source_id')!=job['source_id'] or value.get('chunk_id')!=job['chunk_id']
                            or not value.get('id')):
                        raise ValueError('Asset identity and provenance must match its extraction job.')
                    values.append(value)
                if values:
                    tx._one('INSERT INTO knowledge_engine.partition_asset_order(workspace_key,next_ordinal) '
                            'VALUES (%s,0) ON CONFLICT(workspace_key) DO NOTHING RETURNING next_ordinal',
                            (tx.workspace,))
                    allocation=tx._one('UPDATE knowledge_engine.partition_asset_order SET '
                                       'next_ordinal=next_ordinal+%s,revision=revision+1,updated_at=now() '
                                       'WHERE workspace_key=%s RETURNING next_ordinal',
                                       (len(values),tx.workspace))
                    start=allocation['next_ordinal']-len(values)
                    tx._all('INSERT INTO knowledge_engine.partition_assets '
                            '(workspace_key,asset_id,source_id,chunk_id,generation,extraction_version,job_id,active,'
                            'revision,payload,created_at,ordinal) '
                            'SELECT %s,v.asset_id,%s,%s,%s,%s,%s,true,1,v.payload,v.created_at,%s+v.n-1 '
                            'FROM jsonb_to_recordset(%s) AS v(asset_id text,payload jsonb,created_at timestamptz,n bigint) '
                            'RETURNING asset_id',
                            (tx.workspace,job['source_id'],job['chunk_id'],job['generation'],job['extraction_version'],
                             job['job_id'],start,Jsonb([{'asset_id':v['id'],'payload':v,
                                 'created_at':_time(v.get('created_at')).isoformat(),'n':i+1} for i,v in enumerate(values)])))
            finished=tx.finish_job(job['job_id'],job['generation'],job['revision'],claim['claim_token'],
                                   status=outcome,metadata={'error':error} if assets is None else
                                   {'error':None,'asset_count':len(assets),'model_response_id':response_id})
            if assets is not None:
                summary=tx._one("WITH manifest AS (SELECT coalesce(array_agg(x),ARRAY[]::text[]) AS ids "
                    "FROM knowledge_engine.state_snapshots s CROSS JOIN LATERAL "
                    "jsonb_array_elements_text((SELECT src->'chunk_manifest'->'chunk_ids' "
                    "FROM jsonb_array_elements(s.payload->'sources') src WHERE src->>'id'=%s)) x "
                    "WHERE s.workspace_key=%s), progress AS (SELECT count(DISTINCT j.chunk_id) AS completed "
                    "FROM knowledge_engine.partition_jobs j,manifest m WHERE j.workspace_key=%s "
                    "AND j.source_id=%s AND j.generation=%s AND j.status='completed' AND j.chunk_id=ANY(m.ids)) "
                    "SELECT cardinality(m.ids) AS total,p.completed FROM manifest m CROSS JOIN progress p",
                    (job['source_id'],tx.workspace,tx.workspace,job['source_id'],job['generation']))
                status='knowledge_interpreted' if summary and summary['total'] and summary['completed']==summary['total'] else 'knowledge_interpreting'
                api=dict(source['api_payload'] or {})
                api.update(processing_status=status,stopped_reason=None)
                tx._one('UPDATE knowledge_engine.partition_sources SET interpretation_status=%s,stopped_reason=NULL,'
                        'api_payload=%s,revision=revision+1,updated_at=now() WHERE workspace_key=%s AND source_id=%s '
                        'AND revision=%s RETURNING revision',(status,Jsonb(api),tx.workspace,job['source_id'],source['revision']))
            return finished
        try:
            result=self.apply(operation,request,mutation)
        except HostedStateStoreError:
            receipt=self.read_operation(operation)
            if receipt is None or receipt['request']!=request or not isinstance(receipt.get('result'),dict):
                raise
            result=PartitionMutation(receipt['result'],True)
        return result

    def list_assets(self, *, source_ids=None, history=False):
        with self.transaction() as tx:
            self._require_active(tx)
            ids=source_ids if source_ids is not None else [r['source_id'] for r in tx._all(
                'SELECT source_id FROM knowledge_engine.partition_sources WHERE workspace_key=%s AND NOT deleted ORDER BY source_id',
                (tx.workspace,))]
            if not ids:return []
            rows=tx._all('SELECT a.payload FROM knowledge_engine.partition_assets a '
                'JOIN knowledge_engine.partition_sources s USING(workspace_key,source_id) '
                'WHERE a.workspace_key=%s AND a.source_id=ANY(%s) AND NOT s.deleted '
                'AND (%s OR (a.active AND a.generation=s.generation)) ORDER BY a.ordinal,a.asset_id',
                (tx.workspace,list(ids),history))
            return [r['payload'] for r in rows]

    def _core_payload(self, tx):
        return tx._expect(tx._one('SELECT payload,revision FROM knowledge_engine.state_snapshots '
                                  'WHERE workspace_key=%s FOR UPDATE',(tx.workspace,)))

    def save_core(self, baseline, proposed, expected_revision):
        with self.transaction() as tx:
            core=self._core_payload(tx)
            if core['revision']!=expected_revision or core['payload'].get('partition')!=MARKER:
                raise StaleStateWriteError('Workspace revision or v3 authority changed; reload before saving.')
            old={s['id']:s for s in baseline.get('sources',[])}
            new={s['id']:s for s in proposed.get('sources',[])}
            for sid in sorted(old.keys()|new.keys()):
                before,after=old.get(sid),new.get(sid)
                row=tx._json_record(tx._one('SELECT row_to_json(s) AS record FROM knowledge_engine.partition_sources s '
                    'WHERE workspace_key=%s AND source_id=%s FOR UPDATE',(tx.workspace,sid)))
                if before is None:
                    if row is not None:raise PartitionConflict('Source ID is retained by a lifecycle tombstone.')
                    tx.create_source(sid);row=tx.read_source(sid)
                if after is None:
                    fenced=tx.advance_generation(sid,row['generation'],row['revision'],deleted=True)
                    tx._all('DELETE FROM knowledge_engine.partition_assets WHERE workspace_key=%s AND source_id=%s RETURNING asset_id',
                            (tx.workspace,sid))
                    tx._all('DELETE FROM knowledge_engine.partition_jobs WHERE workspace_key=%s AND source_id=%s RETURNING job_id',
                            (tx.workspace,sid))
                    continue
                old_manifest=before.get('chunk_manifest') if before else None
                new_manifest=after.get('chunk_manifest')
                manifest_fence_changed=(
                    (old_manifest or {}).get('chunk_ids')!=(new_manifest or {}).get('chunk_ids')
                    or (old_manifest or {}).get('total_parts')!=(new_manifest or {}).get('total_parts')
                )
                advanced=bool(before and (before.get('file_path')!=after.get('file_path')
                    or before.get('chunks_path')!=after.get('chunks_path') or manifest_fence_changed))
                if advanced:tx.advance_generation(sid,row['generation'],row['revision']);row=tx.read_source(sid)
                fields={k:deepcopy(v) for k,v in after.items() if k in OWNED}
                if advanced or ((before is None or {k:v for k,v in before.items() if k in OWNED} != fields)
                                and fields != (row['api_payload'] or {})):
                    if before is not None and not advanced and (row['api_payload'] or {}) not in (
                            {k:v for k,v in before.items() if k in OWNED},fields):
                        raise PartitionConflict('Concurrent lifecycle fields changed; reload before saving.')
                    tx._one('UPDATE knowledge_engine.partition_sources SET interpretation_status=%s,stopped_reason=%s,'
                        'api_payload=%s,revision=revision+1,updated_at=now() WHERE workspace_key=%s AND source_id=%s '
                        'AND revision=%s RETURNING revision',(fields.get('processing_status'),fields.get('stopped_reason'),
                        Jsonb(fields),tx.workspace,sid,row['revision']))
            payload=compact(proposed)
            payload.pop('knowledge_assets',None);payload.pop('extraction_jobs',None)
            revision=self._cas(tx,payload,expected_revision) if payload!=core['payload'] else expected_revision
            composed=self.compose(tx,payload,include_jobs=True)
        return revision,composed

    def rollback(self, expected_revision, *, writers_drained=False):
        if not writers_drained:raise PartitionConflict('Rollback requires explicitly drained writers.')
        with self.transaction() as tx:
            core=self._core_payload(tx)
            if core['revision']!=expected_revision or core['payload'].get('partition')!=MARKER:
                raise StaleStateWriteError('Workspace revision or v3 authority changed; reload before rollback.')
            tx._all('SELECT source_id FROM knowledge_engine.partition_sources WHERE workspace_key=%s ORDER BY source_id FOR UPDATE',
                    (tx.workspace,))
            if tx._one("SELECT j.job_id FROM knowledge_engine.partition_jobs j JOIN knowledge_engine.partition_sources s "
                       "USING(workspace_key,source_id) WHERE j.workspace_key=%s AND j.status='running' "
                       "AND j.generation=s.generation AND NOT s.deleted LIMIT 1",(tx.workspace,)):
                raise PartitionConflict('Running current-generation jobs prevent rollback.')
            state=self.compose(tx,core['payload'],include_jobs=True,history=True,include_assets=True)
            fences=tx._all('SELECT source_id,generation FROM knowledge_engine.partition_sources WHERE workspace_key=%s AND NOT deleted',
                           (tx.workspace,))
            generations={r['source_id']:r['generation'] for r in fences}
            jobs=tx._all('SELECT job_id,source_id,generation FROM knowledge_engine.partition_jobs WHERE workspace_key=%s',
                         (tx.workspace,))
            job_generation={r['job_id']:r['generation'] for r in jobs}
            for source in state['sources']:
                if generations.get(source['id'],1)>1:source['generation']=generations[source['id']]
            for job in state['extraction_jobs']:
                if job['id'] in job_generation and job_generation[job['id']]>1:job['generation']=job_generation[job['id']]
            state.pop('partition',None)
            tx.execute("SELECT set_config('knowledge_engine.phase3_rollback','on',true)")
            revision=self._cas(tx,state,expected_revision)
            return {'revision':revision,'payload':state}

    def restart_after_rollback(self, expected_revision, new_attempt_id, *, writers_drained=False):
        if not writers_drained:raise PartitionConflict('Migration restart requires explicitly drained writers.')
        with self.transaction() as tx:
            core=self._core(tx,expected_revision)
            self._lock_provenance(tx)
            if core['payload'].get('partition') is not None:raise PartitionConflict('Restart requires legacy authority after rollback.')
            migration=self._migration(tx,stage='verified')
            if migration['cutover_revision'] is None or migration['cutover_revision']>=expected_revision:
                raise PartitionConflict('Restart requires a verified prior v3 cutover followed by rollback.')
            self._equivalent(tx,core['payload'])
            self._verify_assets(tx,core['payload'])
            fingerprint=self.provenance_fingerprint(tx)
            tx.execute("SELECT set_config('knowledge_engine.phase3_rollback_restart','on',true)")
            self._archive_attempt(tx,migration,'rollback_restart')
            tx._one("UPDATE knowledge_engine.partition_v3_migrations SET attempt_id=%s,source_snapshot_revision=%s,"
                    "source_authority='legacy_rollback',provenance_fingerprint=%s,stage='preparing',checkpoint='{}'::jsonb,revision=revision+1,"
                    "started_at=now(),verified_at=NULL,cutover_revision=NULL,updated_at=now() "
                    'WHERE workspace_key=%s RETURNING revision',
                    (new_attempt_id,expected_revision,fingerprint,tx.workspace))
            return {'attempt_id':new_attempt_id,'stage':'preparing','checkpoint':{},
                    'source_snapshot_revision':expected_revision,'provenance_fingerprint':fingerprint}

    def read_migration(self):
        with self.transaction() as tx:
            row=tx._one('SELECT row_to_json(m) AS record FROM knowledge_engine.partition_v3_migrations m '
                        'WHERE workspace_key=%s',(tx.workspace,))
            return row['record'] if row else None

    def read_migration_history(self):
        with self.transaction() as tx:
            return tx._all('SELECT * FROM knowledge_engine.partition_v3_migration_history '
                           'WHERE workspace_key=%s ORDER BY archived_at,attempt_id',(tx.workspace,))


def rebase_projection(base, local, latest):
    """Rebase core-owned edits while discarding all v3-owned asset/job fields."""
    from app.persistence.reconciliation import merge_state_snapshots, StateReconciliationConflict
    before=compact(base);ours=compact(local);theirs=compact(latest)
    merged=merge_state_snapshots(before,ours,theirs)
    old={s['id']:s for s in base.get('sources',[])}
    new={s['id']:s for s in local.get('sources',[])}
    current={s['id']:s for s in latest.get('sources',[])}
    for source in merged.get('sources',[]):
        sid=source['id'];prior={k:deepcopy(v) for k,v in old.get(sid,{}).items() if k in OWNED}
        proposed={k:deepcopy(v) for k,v in new.get(sid,{}).items() if k in OWNED}
        theirs_owned={k:deepcopy(v) for k,v in current.get(sid,{}).items() if k in OWNED}
        if proposed!=prior:
            if theirs_owned not in (prior,proposed):
                raise StateReconciliationConflict('Concurrent lifecycle fields changed.')
            theirs_owned=proposed
        source.update(theirs_owned)
    merged.pop('knowledge_assets',None)
    merged.pop('extraction_jobs',None)
    merged['knowledge_assets']=[]
    return merged
