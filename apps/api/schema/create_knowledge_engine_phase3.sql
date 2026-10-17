-- Phase 3 additive DDL. Apply only to disposable/test databases in this phase.
-- No hosted schema migration or authority activation is part of this file.
BEGIN;

ALTER TABLE knowledge_engine.partition_assets ADD COLUMN ordinal bigint;
WITH ordered AS (
    SELECT workspace_key, asset_id,
           row_number() OVER (PARTITION BY workspace_key ORDER BY created_at, asset_id) - 1 AS ordinal
    FROM knowledge_engine.partition_assets
)
UPDATE knowledge_engine.partition_assets a SET ordinal=o.ordinal
FROM ordered o WHERE a.workspace_key=o.workspace_key AND a.asset_id=o.asset_id;
ALTER TABLE knowledge_engine.partition_assets ALTER COLUMN ordinal SET NOT NULL;
ALTER TABLE knowledge_engine.partition_assets ADD CONSTRAINT partition_asset_ordinal_nonnegative CHECK (ordinal >= 0);
CREATE UNIQUE INDEX partition_assets_workspace_ordinal
    ON knowledge_engine.partition_assets(workspace_key, ordinal);
CREATE INDEX partition_assets_active_order
    ON knowledge_engine.partition_assets(workspace_key, source_id, generation, ordinal, asset_id)
    WHERE active;

CREATE TABLE knowledge_engine.partition_asset_order (
    workspace_key text PRIMARY KEY,
    next_ordinal bigint NOT NULL CHECK (next_ordinal >= 0),
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE knowledge_engine.partition_asset_order ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON knowledge_engine.partition_asset_order FROM PUBLIC;

CREATE TABLE knowledge_engine.partition_v3_migrations (
    workspace_key text PRIMARY KEY,
    attempt_id text NOT NULL CHECK (attempt_id <> ''),
    partition_version integer NOT NULL DEFAULT 3 CHECK (partition_version = 3),
    source_authority text NOT NULL DEFAULT 'v2' CHECK (source_authority IN ('v2','legacy_rollback')),
    source_snapshot_revision bigint NOT NULL CHECK (source_snapshot_revision >= 0),
    provenance_fingerprint text NOT NULL CHECK (provenance_fingerprint <> ''),
    stage text NOT NULL DEFAULT 'preparing' CHECK (stage IN ('preparing', 'verified')),
    checkpoint jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(checkpoint) = 'object'),
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    started_at timestamptz NOT NULL DEFAULT now(),
    verified_at timestamptz,
    cutover_revision bigint,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((stage = 'preparing' AND verified_at IS NULL)
        OR (stage = 'verified' AND verified_at IS NOT NULL))
);
ALTER TABLE knowledge_engine.partition_v3_migrations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON knowledge_engine.partition_v3_migrations FROM PUBLIC;

CREATE TABLE knowledge_engine.partition_v3_migration_history (
    workspace_key text NOT NULL,
    attempt_id text NOT NULL,
    partition_version integer NOT NULL CHECK (partition_version = 3),
    source_authority text NOT NULL CHECK (source_authority IN ('v2','legacy_rollback')),
    source_snapshot_revision bigint NOT NULL,
    provenance_fingerprint text NOT NULL,
    stage text NOT NULL CHECK (stage IN ('preparing', 'verified')),
    checkpoint jsonb NOT NULL CHECK (jsonb_typeof(checkpoint) = 'object'),
    migration_revision bigint NOT NULL,
    started_at timestamptz NOT NULL,
    verified_at timestamptz,
    cutover_revision bigint,
    terminal_reason text NOT NULL CHECK (terminal_reason IN ('revision_drift', 'rollback_restart')),
    archived_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, attempt_id),
    CHECK ((terminal_reason = 'revision_drift' AND stage = 'preparing'
            AND verified_at IS NULL AND cutover_revision IS NULL)
        OR (terminal_reason = 'rollback_restart' AND stage = 'verified'
            AND verified_at IS NOT NULL AND cutover_revision IS NOT NULL))
);
ALTER TABLE knowledge_engine.partition_v3_migration_history ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON knowledge_engine.partition_v3_migration_history FROM PUBLIC;

CREATE FUNCTION knowledge_engine.phase3_v2_authority(p_workspace text) RETURNS boolean
LANGUAGE sql STABLE AS $$
 SELECT EXISTS (
   SELECT 1 FROM knowledge_engine.state_snapshots s
   WHERE s.workspace_key = p_workspace
     AND s.payload->'partition' = '{"version":2,"state":"active","domains":["jobs","source_lifecycle"]}'::jsonb
 )
$$;

CREATE FUNCTION knowledge_engine.phase3_attempt_authority(p_workspace text) RETURNS boolean
LANGUAGE sql STABLE AS $$
 SELECT EXISTS (
   SELECT 1 FROM knowledge_engine.partition_v3_migrations m
   JOIN knowledge_engine.state_snapshots s USING (workspace_key)
   WHERE m.workspace_key=p_workspace AND (
      (m.source_authority='v2' AND knowledge_engine.phase3_v2_authority(p_workspace))
      OR (m.source_authority='legacy_rollback' AND NOT (s.payload ? 'partition')
          AND EXISTS (SELECT 1 FROM knowledge_engine.partition_v3_migration_history h
                      WHERE h.workspace_key=p_workspace AND h.terminal_reason='rollback_restart'))
   )
 )
$$;

CREATE FUNCTION knowledge_engine.phase3_backfill_allowed(p_workspace text) RETURNS boolean
LANGUAGE sql STABLE AS $$
 SELECT current_setting('knowledge_engine.phase3_backfill', true) = 'on' AND EXISTS (
   SELECT 1 FROM knowledge_engine.partition_v3_migrations m
   JOIN knowledge_engine.state_snapshots s USING (workspace_key)
   WHERE m.workspace_key = p_workspace
     AND p_workspace = current_setting('knowledge_engine.phase3_backfill_workspace', true)
     AND m.partition_version = 3 AND m.stage = 'preparing'
     AND m.source_snapshot_revision = s.revision
     AND knowledge_engine.phase3_attempt_authority(p_workspace)
 )
$$;

CREATE FUNCTION knowledge_engine.guard_partition_v3_migration() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE drift_restart boolean; rollback_restart boolean; cutover boolean;
BEGIN
    drift_restart := TG_OP = 'UPDATE' AND current_setting('knowledge_engine.phase3_drift_restart', true) = 'on';
    rollback_restart := TG_OP = 'UPDATE' AND current_setting('knowledge_engine.phase3_rollback_restart', true) = 'on';
    cutover := TG_OP = 'UPDATE' AND current_setting('knowledge_engine.phase3_cutover', true) = 'on';
    IF TG_OP = 'UPDATE' THEN
        IF NEW.workspace_key <> OLD.workspace_key OR NEW.partition_version <> OLD.partition_version
           OR NEW.revision <> OLD.revision + 1
           OR (NOT drift_restart AND NOT rollback_restart AND
              (NEW.attempt_id <> OLD.attempt_id OR NEW.source_authority <> OLD.source_authority
               OR NEW.source_snapshot_revision <> OLD.source_snapshot_revision
               OR NEW.provenance_fingerprint <> OLD.provenance_fingerprint
               OR NEW.started_at IS DISTINCT FROM OLD.started_at))
           OR (drift_restart AND (OLD.stage <> 'preparing' OR NEW.stage <> 'preparing'
               OR NEW.attempt_id = OLD.attempt_id OR NEW.checkpoint <> '{}'::jsonb
               OR (NEW.source_snapshot_revision = OLD.source_snapshot_revision
                   AND NEW.provenance_fingerprint = OLD.provenance_fingerprint)
               OR NEW.verified_at IS NOT NULL OR NEW.cutover_revision IS NOT NULL
               OR NOT EXISTS (SELECT 1 FROM knowledge_engine.partition_v3_migration_history h
                   WHERE h.workspace_key=OLD.workspace_key AND h.attempt_id=OLD.attempt_id
                     AND h.source_snapshot_revision=OLD.source_snapshot_revision
                     AND h.provenance_fingerprint=OLD.provenance_fingerprint
                     AND h.stage=OLD.stage AND h.checkpoint=OLD.checkpoint
                     AND h.migration_revision=OLD.revision AND h.started_at=OLD.started_at
                     AND h.verified_at IS NULL AND h.cutover_revision IS NULL
                     AND h.terminal_reason='revision_drift')))
           OR (rollback_restart AND (OLD.stage <> 'verified' OR OLD.cutover_revision IS NULL
               OR NEW.stage <> 'preparing' OR NEW.attempt_id = OLD.attempt_id
               OR NEW.checkpoint <> '{}'::jsonb OR NEW.verified_at IS NOT NULL
               OR NEW.cutover_revision IS NOT NULL
               OR NOT EXISTS (SELECT 1 FROM knowledge_engine.partition_v3_migration_history h
                   WHERE h.workspace_key=OLD.workspace_key AND h.attempt_id=OLD.attempt_id
                     AND h.source_snapshot_revision=OLD.source_snapshot_revision
                     AND h.provenance_fingerprint=OLD.provenance_fingerprint
                     AND h.stage=OLD.stage AND h.checkpoint=OLD.checkpoint
                     AND h.migration_revision=OLD.revision AND h.started_at=OLD.started_at
                     AND h.verified_at=OLD.verified_at AND h.cutover_revision=OLD.cutover_revision
                     AND h.terminal_reason='rollback_restart')))
           OR (cutover AND (OLD.stage <> 'verified' OR NEW.stage <> 'verified'
               OR NEW.attempt_id <> OLD.attempt_id OR NEW.source_snapshot_revision <> OLD.source_snapshot_revision
               OR NEW.provenance_fingerprint <> OLD.provenance_fingerprint
               OR NEW.checkpoint <> OLD.checkpoint OR NEW.cutover_revision IS NULL
               OR NOT EXISTS (SELECT 1 FROM knowledge_engine.state_snapshots s
                   WHERE s.workspace_key=NEW.workspace_key AND s.revision=NEW.cutover_revision
                     AND s.payload->'partition'->>'version'='3'
                     AND s.payload->'partition'->>'state'='active')))
           OR (NOT drift_restart AND NOT rollback_restart AND NOT cutover
               AND (OLD.stage <> 'preparing' OR NEW.cutover_revision IS NOT NULL
                 OR (NEW.stage='preparing' AND NEW.verified_at IS NOT NULL)
                 OR (NEW.stage='verified' AND NEW.verified_at IS NULL)))
        THEN RAISE EXCEPTION 'partition v3 migration transition rejected' USING ERRCODE='23514'; END IF;
    ELSIF NEW.revision <> 1 OR NEW.stage <> 'preparing' OR NEW.verified_at IS NOT NULL OR NEW.cutover_revision IS NOT NULL THEN
        RAISE EXCEPTION 'partition v3 migration initialization rejected' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_partition_v3_migration
 BEFORE INSERT OR UPDATE ON knowledge_engine.partition_v3_migrations
 FOR EACH ROW EXECUTE FUNCTION knowledge_engine.guard_partition_v3_migration();

CREATE FUNCTION knowledge_engine.guard_partition_v3_history() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE m knowledge_engine.partition_v3_migrations%ROWTYPE;
BEGIN
    IF TG_OP <> 'INSERT' OR (current_setting('knowledge_engine.phase3_drift_restart',true) <> 'on'
       AND current_setting('knowledge_engine.phase3_rollback_restart',true) <> 'on') THEN
        RAISE EXCEPTION 'partition v3 migration history is append-only' USING ERRCODE='23514';
    END IF;
    SELECT * INTO m FROM knowledge_engine.partition_v3_migrations WHERE workspace_key=NEW.workspace_key FOR UPDATE;
    IF NOT FOUND OR m.attempt_id<>NEW.attempt_id OR m.source_authority<>NEW.source_authority
       OR m.source_snapshot_revision<>NEW.source_snapshot_revision
       OR m.provenance_fingerprint<>NEW.provenance_fingerprint OR m.stage<>NEW.stage
       OR m.checkpoint<>NEW.checkpoint OR m.revision<>NEW.migration_revision OR m.started_at<>NEW.started_at
       OR m.verified_at IS DISTINCT FROM NEW.verified_at OR m.cutover_revision IS DISTINCT FROM NEW.cutover_revision
       OR (NEW.terminal_reason='revision_drift' AND current_setting('knowledge_engine.phase3_drift_restart',true)<>'on')
       OR (NEW.terminal_reason='rollback_restart' AND current_setting('knowledge_engine.phase3_rollback_restart',true)<>'on') THEN
        RAISE EXCEPTION 'partition v3 history does not match archived attempt' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_partition_v3_history
 BEFORE INSERT OR UPDATE OR DELETE ON knowledge_engine.partition_v3_migration_history
 FOR EACH ROW EXECUTE FUNCTION knowledge_engine.guard_partition_v3_history();

CREATE OR REPLACE FUNCTION knowledge_engine.guard_phase2_core() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE old_version text; new_version text; marker_changed boolean;
BEGIN
    old_version := OLD.payload->'partition'->>'version';
    new_version := NEW.payload->'partition'->>'version';
    marker_changed := NEW.payload->'partition' IS DISTINCT FROM OLD.payload->'partition';
    IF old_version='2' AND OLD.payload->'partition'->>'state'='active' AND marker_changed
       AND current_setting('knowledge_engine.phase2_rollback',true) IS DISTINCT FROM 'on'
       AND NOT (new_version='3' AND current_setting('knowledge_engine.phase3_cutover',true)='on') THEN
        RAISE EXCEPTION 'phase2 authority marker transition rejected' USING ERRCODE='23514';
    END IF;
    IF old_version='3' AND OLD.payload->'partition'->>'state'='active' AND marker_changed
       AND current_setting('knowledge_engine.phase3_rollback',true) IS DISTINCT FROM 'on' THEN
        RAISE EXCEPTION 'phase3 authority marker transition rejected' USING ERRCODE='23514';
    END IF;
    IF new_version='3' AND NEW.payload->'partition'->>'state'='active' AND marker_changed
       AND current_setting('knowledge_engine.phase3_cutover',true) IS DISTINCT FROM 'on' THEN
        RAISE EXCEPTION 'phase3 cutover must be explicit' USING ERRCODE='23514';
    END IF;
    IF new_version='2' AND NEW.payload->'partition'->>'state'='active' THEN
        IF NEW.payload ? 'extraction_jobs' OR EXISTS (
          SELECT 1 FROM jsonb_array_elements(NEW.payload->'sources') s
          WHERE s ?| ARRAY['processing_status','stopped_reason','generation','deleted','interruption_reason']
        ) THEN RAISE EXCEPTION 'phase2 core contains narrow-owned fields' USING ERRCODE='23514'; END IF;
    ELSIF new_version='3' AND NEW.payload->'partition'->>'state'='active' THEN
        IF NEW.payload ? 'knowledge_assets' OR NEW.payload ? 'extraction_jobs' OR EXISTS (
          SELECT 1 FROM jsonb_array_elements(NEW.payload->'sources') s
          WHERE s ?| ARRAY['processing_status','stopped_reason','generation','deleted','interruption_reason']
        ) THEN RAISE EXCEPTION 'phase3 core contains narrow-owned fields' USING ERRCODE='23514'; END IF;
    END IF;
    RETURN NEW;
END $$;

REVOKE ALL ON FUNCTION knowledge_engine.phase3_v2_authority(text),
    knowledge_engine.phase3_attempt_authority(text),
    knowledge_engine.phase3_backfill_allowed(text),
    knowledge_engine.guard_partition_v3_migration(),
    knowledge_engine.guard_partition_v3_history(),
    knowledge_engine.guard_phase2_core(),
    knowledge_engine.guard_partition_record() FROM PUBLIC;

CREATE OR REPLACE FUNCTION knowledge_engine.guard_partition_record() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE fence knowledge_engine.partition_sources%ROWTYPE;
        backfill_insert boolean;
        v3_backfill_insert boolean;
BEGIN
    backfill_insert := TG_TABLE_NAME = 'partition_jobs' AND TG_OP = 'INSERT'
        AND coalesce(knowledge_engine.phase2_backfill_allowed(NEW.workspace_key), false);
    v3_backfill_insert := TG_TABLE_NAME = 'partition_assets' AND TG_OP = 'INSERT'
        AND coalesce(knowledge_engine.phase3_backfill_allowed(NEW.workspace_key), false);
    SELECT * INTO fence FROM knowledge_engine.partition_sources
        WHERE workspace_key = NEW.workspace_key AND source_id = NEW.source_id FOR UPDATE;
    IF NOT FOUND OR fence.deleted OR NEW.generation > fence.generation
       OR (NEW.generation < fence.generation AND NOT backfill_insert AND NOT v3_backfill_insert) THEN
        RAISE EXCEPTION 'partition generation fenced' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF NEW.workspace_key <> OLD.workspace_key OR NEW.source_id <> OLD.source_id
           OR NEW.generation <> OLD.generation OR NEW.chunk_id <> OLD.chunk_id
           OR NEW.extraction_version <> OLD.extraction_version OR NEW.revision <> OLD.revision + 1
           OR NEW.created_at IS DISTINCT FROM OLD.created_at
        THEN RAISE EXCEPTION 'partition immutable identity or revision rejected' USING ERRCODE = '23514'; END IF;
    ELSIF NEW.revision <> 1 THEN
        RAISE EXCEPTION 'partition initial revision rejected' USING ERRCODE = '23514';
    END IF;
    IF backfill_insert THEN RETURN NEW; END IF;
    IF v3_backfill_insert THEN
        IF NEW.generation > fence.generation OR NOT EXISTS (
            SELECT 1 FROM knowledge_engine.partition_jobs j WHERE j.workspace_key=NEW.workspace_key
              AND j.job_id=NEW.job_id AND j.source_id=NEW.source_id AND j.chunk_id=NEW.chunk_id
              AND j.generation=NEW.generation AND j.extraction_version=NEW.extraction_version
              AND j.status='completed'
        ) THEN RAISE EXCEPTION 'phase3 asset provenance rejected' USING ERRCODE='23514'; END IF;
        RETURN NEW;
    END IF;
    IF TG_TABLE_NAME = 'partition_jobs' THEN
        IF TG_OP = 'UPDATE' AND NEW.status IN ('pending_ai','running','completed') AND EXISTS (
            SELECT 1 FROM knowledge_engine.partition_jobs j WHERE j.workspace_key=NEW.workspace_key
              AND j.source_id=NEW.source_id AND j.generation=NEW.generation AND j.chunk_id=NEW.chunk_id
              AND j.extraction_version>NEW.extraction_version
        ) THEN RAISE EXCEPTION 'partition extraction version is superseded' USING ERRCODE='23514'; END IF;
    END IF;
    IF TG_TABLE_NAME = 'partition_jobs' THEN
        IF TG_OP = 'INSERT' AND (NEW.status <> 'pending_ai' OR NEW.claim_token IS NOT NULL) THEN
            RAISE EXCEPTION 'partition initial job state rejected' USING ERRCODE = '23514';
        ELSIF TG_OP = 'INSERT' AND NEW.extraction_version <> (
            SELECT coalesce(max(extraction_version), 0) + 1 FROM knowledge_engine.partition_jobs
            WHERE workspace_key = NEW.workspace_key AND source_id = NEW.source_id
              AND generation = NEW.generation AND chunk_id = NEW.chunk_id
        ) THEN RAISE EXCEPTION 'partition extraction version rejected' USING ERRCODE = '23514';
        ELSIF TG_OP = 'UPDATE' THEN
            IF NEW.job_id <> OLD.job_id OR NOT (
                (OLD.status = 'pending_ai' AND NEW.status = 'running') OR
                (OLD.status = 'running' AND NEW.status IN ('completed', 'failed')) OR
                (OLD.status = 'failed' AND NEW.status = 'pending_ai') OR
                (OLD.status = 'running' AND NEW.status = 'pending_ai'
                    AND OLD.started_at <= now() - interval '10 minutes')
            ) THEN RAISE EXCEPTION 'partition job transition rejected' USING ERRCODE = '23514'; END IF;
        END IF;
    ELSE
        IF TG_OP = 'UPDATE' AND (NEW.asset_id <> OLD.asset_id OR NEW.job_id <> OLD.job_id
            OR NEW.ordinal <> OLD.ordinal) THEN
            RAISE EXCEPTION 'partition asset identity rejected' USING ERRCODE = '23514';
        END IF;
        IF TG_OP = 'INSERT' AND NOT EXISTS (
            SELECT 1 FROM knowledge_engine.partition_jobs j
            WHERE j.workspace_key = NEW.workspace_key AND j.job_id = NEW.job_id AND j.status = 'running'
        ) THEN RAISE EXCEPTION 'partition asset job is not running' USING ERRCODE = '23514'; END IF;
        IF TG_OP = 'UPDATE' AND NOT OLD.active AND NEW.active THEN
            RAISE EXCEPTION 'partition supersession is irreversible' USING ERRCODE = '23514';
        END IF;
        IF TG_OP = 'UPDATE' AND (NOT OLD.active OR OLD.generation <> fence.generation) THEN
            RAISE EXCEPTION 'historical partition assets are immutable' USING ERRCODE = '23514';
        END IF;
        IF TG_OP = 'UPDATE' AND OLD.active AND NOT NEW.active AND NEW.superseded_by_job_id IS NULL THEN
            RAISE EXCEPTION 'asset supersession provenance required' USING ERRCODE='23514';
        END IF;
        IF NEW.superseded_by_job_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM knowledge_engine.partition_jobs j
            WHERE j.workspace_key = NEW.workspace_key AND j.job_id = NEW.superseded_by_job_id
              AND j.source_id = NEW.source_id AND j.chunk_id = NEW.chunk_id
              AND j.generation = NEW.generation AND j.extraction_version > NEW.extraction_version
        ) THEN RAISE EXCEPTION 'partition replacement provenance rejected' USING ERRCODE = '23514'; END IF;
        IF NEW.active AND EXISTS (
            SELECT 1 FROM knowledge_engine.partition_assets a
            WHERE a.workspace_key = NEW.workspace_key AND a.source_id = NEW.source_id
              AND a.generation = NEW.generation AND a.chunk_id = NEW.chunk_id
              AND a.extraction_version <> NEW.extraction_version AND a.active
        ) THEN RAISE EXCEPTION 'partition competing active extraction rejected' USING ERRCODE = '23514'; END IF;
    END IF;
    RETURN NEW;
END $$;

COMMIT;
