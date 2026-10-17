-- Phase 2 additive SQL; apply only explicitly. No data migration/cutover here.
BEGIN;
ALTER TABLE knowledge_engine.partition_jobs ADD COLUMN api_payload jsonb;
ALTER TABLE knowledge_engine.partition_jobs ADD COLUMN ordinal bigint NOT NULL DEFAULT 0;
ALTER TABLE knowledge_engine.partition_sources ADD COLUMN api_payload jsonb;
ALTER TABLE knowledge_engine.partition_jobs ADD CONSTRAINT phase2_job_api_object CHECK (api_payload IS NULL OR jsonb_typeof(api_payload)='object');
ALTER TABLE knowledge_engine.partition_sources ADD CONSTRAINT phase2_source_api_object CHECK (api_payload IS NULL OR jsonb_typeof(api_payload)='object');
ALTER TABLE knowledge_engine.partition_jobs ADD CONSTRAINT phase2_ordinal_nonnegative CHECK (ordinal>=0);
ALTER TABLE knowledge_engine.partition_migrations ADD COLUMN verified_at timestamptz;
ALTER TABLE knowledge_engine.partition_migrations ADD COLUMN cutover_revision bigint;
ALTER TABLE knowledge_engine.partition_migrations ADD COLUMN started_at timestamptz NOT NULL DEFAULT now();
CREATE TABLE knowledge_engine.partition_migration_attempt_history (
 workspace_key text NOT NULL,
 migration_id text NOT NULL,
 partition_version integer NOT NULL,
 source_snapshot_revision bigint NOT NULL,
 stage text NOT NULL CHECK (stage IN ('preparing','verified')),
 checkpoint jsonb NOT NULL CHECK (jsonb_typeof(checkpoint)='object'),
 migration_revision bigint NOT NULL,
 started_at timestamptz NOT NULL,
 verified_at timestamptz,
 cutover_revision bigint,
 terminal_reason text NOT NULL CHECK (terminal_reason IN ('rollback_restart','revision_drift')),
 archived_at timestamptz NOT NULL DEFAULT now(),
 CHECK ((terminal_reason='rollback_restart' AND stage='verified' AND verified_at IS NOT NULL)
     OR (terminal_reason='revision_drift' AND stage='preparing' AND verified_at IS NULL AND cutover_revision IS NULL)),
 PRIMARY KEY (workspace_key,migration_id)
);
ALTER TABLE knowledge_engine.partition_migration_attempt_history ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON knowledge_engine.partition_migration_attempt_history FROM PUBLIC;
CREATE INDEX partition_jobs_api_order ON knowledge_engine.partition_jobs
    (workspace_key, source_id, generation, ordinal, job_id);
CREATE FUNCTION knowledge_engine.phase2_backfill_allowed(p_workspace text) RETURNS boolean
LANGUAGE sql STABLE AS $$
 SELECT current_setting('knowledge_engine.backfill', true) = 'on' AND EXISTS (
  SELECT 1 FROM knowledge_engine.partition_migrations m
  JOIN knowledge_engine.state_snapshots s USING (workspace_key)
  WHERE m.workspace_key = p_workspace AND p_workspace = current_setting('knowledge_engine.backfill_workspace', true)
    AND m.partition_version = 2 AND m.stage = 'preparing'
    AND m.source_snapshot_revision = s.revision
    AND NOT (s.payload ? 'partition')
 )
$$;
CREATE FUNCTION knowledge_engine.phase2_restart_after_rollback_allowed(p_workspace text, p_revision bigint, p_migration_id text) RETURNS boolean
LANGUAGE sql STABLE AS $$
 SELECT current_setting('knowledge_engine.phase2_restart', true) = 'on' AND EXISTS (
  SELECT 1 FROM knowledge_engine.partition_migrations m
  JOIN knowledge_engine.state_snapshots s USING (workspace_key)
  WHERE m.workspace_key=p_workspace AND s.workspace_key=p_workspace
    AND m.partition_version=2 AND m.stage='verified'
    AND m.source_snapshot_revision < p_revision AND m.cutover_revision < p_revision AND s.revision=p_revision
    AND NOT (s.payload ? 'partition')
    AND m.migration_id <> p_migration_id
    AND NOT EXISTS (SELECT 1 FROM knowledge_engine.partition_migration_attempt_history h
                    WHERE h.workspace_key=p_workspace AND h.migration_id=p_migration_id)
 )
$$;
CREATE FUNCTION knowledge_engine.phase2_restart_after_revision_drift_allowed(p_workspace text, p_revision bigint, p_migration_id text) RETURNS boolean
LANGUAGE sql STABLE AS $$
 SELECT current_setting('knowledge_engine.phase2_drift_restart', true) = 'on' AND EXISTS (
  SELECT 1 FROM knowledge_engine.partition_migrations m
  JOIN knowledge_engine.state_snapshots s USING (workspace_key)
  WHERE m.workspace_key=p_workspace AND s.workspace_key=p_workspace
    AND m.partition_version=2 AND m.stage='preparing'
    AND m.source_snapshot_revision<>p_revision AND s.revision=p_revision
    AND NOT (s.payload ? 'partition')
    AND m.verified_at IS NULL AND m.cutover_revision IS NULL
    AND m.migration_id<>p_migration_id
    AND NOT EXISTS (SELECT 1 FROM knowledge_engine.partition_migration_attempt_history h
                    WHERE h.workspace_key=p_workspace AND h.migration_id=p_migration_id)
 )
$$;
CREATE FUNCTION knowledge_engine.guard_partition_migration_attempt_history() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE current_attempt knowledge_engine.partition_migrations%ROWTYPE;
        rollback_archive boolean; drift_archive boolean;
BEGIN
    rollback_archive := current_setting('knowledge_engine.phase2_restart',true) = 'on';
    drift_archive := current_setting('knowledge_engine.phase2_drift_restart',true) = 'on';
    IF TG_OP <> 'INSERT' OR (NOT rollback_archive AND NOT drift_archive) THEN
        RAISE EXCEPTION 'partition attempt history is append-only' USING ERRCODE='23514';
    END IF;
    SELECT * INTO current_attempt FROM knowledge_engine.partition_migrations
      WHERE workspace_key=NEW.workspace_key FOR UPDATE;
    IF NOT FOUND OR current_attempt.migration_id<>NEW.migration_id
       OR current_attempt.partition_version<>NEW.partition_version
       OR current_attempt.source_snapshot_revision<>NEW.source_snapshot_revision
       OR current_attempt.stage<>NEW.stage OR current_attempt.checkpoint<>NEW.checkpoint
       OR current_attempt.revision<>NEW.migration_revision
       OR current_attempt.started_at IS DISTINCT FROM NEW.started_at
       OR current_attempt.verified_at IS DISTINCT FROM NEW.verified_at
       OR current_attempt.cutover_revision IS DISTINCT FROM NEW.cutover_revision
       OR (rollback_archive AND (NEW.terminal_reason<>'rollback_restart' OR NEW.stage<>'verified'
                                  OR NEW.verified_at IS NULL OR NEW.cutover_revision IS NULL))
       OR (drift_archive AND (NEW.terminal_reason<>'revision_drift' OR NEW.stage<>'preparing'
                               OR NEW.verified_at IS NOT NULL OR NEW.cutover_revision IS NOT NULL)) THEN
        RAISE EXCEPTION 'partition attempt history does not match terminal attempt' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_partition_migration_attempt_history
 BEFORE INSERT OR UPDATE OR DELETE ON knowledge_engine.partition_migration_attempt_history
 FOR EACH ROW EXECUTE FUNCTION knowledge_engine.guard_partition_migration_attempt_history();
CREATE OR REPLACE FUNCTION knowledge_engine.guard_partition_source() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.workspace_key <> OLD.workspace_key OR NEW.source_id <> OLD.source_id
           OR NEW.revision <> OLD.revision + 1 OR NEW.created_at IS DISTINCT FROM OLD.created_at
           OR NEW.generation NOT IN (OLD.generation, OLD.generation + 1)
           OR (OLD.deleted AND NOT NEW.deleted)
           OR (NOT OLD.deleted AND NEW.deleted AND NEW.generation <> OLD.generation + 1)
        THEN RAISE EXCEPTION 'partition source transition rejected' USING ERRCODE = '23514'; END IF;
    ELSIF NOT knowledge_engine.phase2_backfill_allowed(NEW.workspace_key) AND (NEW.generation <> 1 OR NEW.revision <> 1 OR NEW.deleted) THEN
        RAISE EXCEPTION 'partition source initialization rejected' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION knowledge_engine.guard_partition_migration() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE restart_after_rollback boolean; restart_after_drift boolean; cutover_record boolean;
BEGIN
    restart_after_rollback := TG_OP = 'UPDATE' AND
        knowledge_engine.phase2_restart_after_rollback_allowed(NEW.workspace_key,NEW.source_snapshot_revision,NEW.migration_id);
    restart_after_drift := TG_OP = 'UPDATE' AND
        knowledge_engine.phase2_restart_after_revision_drift_allowed(NEW.workspace_key,NEW.source_snapshot_revision,NEW.migration_id);
    cutover_record := TG_OP = 'UPDATE' AND current_setting('knowledge_engine.phase2_cutover',true)='on';
    IF TG_OP = 'UPDATE' THEN
        IF NEW.workspace_key <> OLD.workspace_key OR NEW.partition_version <> OLD.partition_version
           OR NEW.revision <> OLD.revision + 1
           OR (restart_after_rollback AND
               (OLD.stage <> 'verified' OR NEW.stage <> 'preparing' OR NEW.migration_id = OLD.migration_id
                OR NEW.checkpoint <> '{}'::jsonb OR NEW.source_snapshot_revision <= OLD.source_snapshot_revision
                OR NEW.started_at <= OLD.started_at
                OR NEW.verified_at IS NOT NULL OR NEW.cutover_revision IS NOT NULL
                OR NOT EXISTS (SELECT 1 FROM knowledge_engine.partition_migration_attempt_history h
                               WHERE h.workspace_key=OLD.workspace_key AND h.migration_id=OLD.migration_id
                                 AND h.partition_version=OLD.partition_version
                                 AND h.source_snapshot_revision=OLD.source_snapshot_revision
                                 AND h.stage=OLD.stage AND h.checkpoint=OLD.checkpoint
                                 AND h.migration_revision=OLD.revision AND h.started_at=OLD.started_at
                                 AND h.verified_at=OLD.verified_at
                                 AND h.cutover_revision IS NOT DISTINCT FROM OLD.cutover_revision
                                 AND h.terminal_reason='rollback_restart')))
           OR (restart_after_drift AND
               (OLD.stage <> 'preparing' OR NEW.stage <> 'preparing' OR NEW.migration_id = OLD.migration_id
                OR NEW.checkpoint <> '{}'::jsonb OR NEW.source_snapshot_revision = OLD.source_snapshot_revision
                OR NEW.started_at <= OLD.started_at OR OLD.verified_at IS NOT NULL OR OLD.cutover_revision IS NOT NULL
                OR NEW.verified_at IS NOT NULL OR NEW.cutover_revision IS NOT NULL
                OR NOT EXISTS (SELECT 1 FROM knowledge_engine.partition_migration_attempt_history h
                               WHERE h.workspace_key=OLD.workspace_key AND h.migration_id=OLD.migration_id
                                 AND h.partition_version=OLD.partition_version
                                 AND h.source_snapshot_revision=OLD.source_snapshot_revision
                                 AND h.stage=OLD.stage AND h.checkpoint=OLD.checkpoint
                                 AND h.migration_revision=OLD.revision AND h.started_at=OLD.started_at
                                 AND h.verified_at IS NULL AND h.cutover_revision IS NULL
                                 AND h.terminal_reason='revision_drift')))
           OR (cutover_record AND
               (OLD.stage<>'verified' OR NEW.stage<>'verified' OR NEW.migration_id<>OLD.migration_id
                OR NEW.partition_version<>OLD.partition_version
                OR NEW.source_snapshot_revision<>OLD.source_snapshot_revision
                OR NEW.checkpoint<>OLD.checkpoint OR NEW.verified_at IS DISTINCT FROM OLD.verified_at
                OR NEW.started_at IS DISTINCT FROM OLD.started_at
                OR OLD.cutover_revision IS NOT NULL OR NEW.cutover_revision IS NULL
                OR NOT EXISTS (SELECT 1 FROM knowledge_engine.state_snapshots s
                               WHERE s.workspace_key=NEW.workspace_key AND s.revision=NEW.cutover_revision
                                 AND s.payload->'partition'->>'version'='2'
                                 AND s.payload->'partition'->>'state'='active')))
           OR (NOT restart_after_rollback AND NOT restart_after_drift AND NOT cutover_record AND
               (NEW.migration_id <> OLD.migration_id
                OR NEW.source_snapshot_revision <> OLD.source_snapshot_revision
                OR NEW.started_at IS DISTINCT FROM OLD.started_at OR OLD.stage <> 'preparing'
                OR NEW.cutover_revision IS NOT NULL
                OR (NEW.stage='preparing' AND NEW.verified_at IS NOT NULL)
                OR (NEW.stage='verified' AND NEW.verified_at IS NULL)))
        THEN RAISE EXCEPTION 'partition migration transition rejected' USING ERRCODE = '23514'; END IF;
    ELSIF NEW.revision <> 1 OR NEW.stage <> 'preparing' OR NEW.verified_at IS NOT NULL OR NEW.cutover_revision IS NOT NULL THEN
        RAISE EXCEPTION 'partition migration initialization rejected' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION knowledge_engine.guard_partition_record() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE fence knowledge_engine.partition_sources%ROWTYPE; backfill_insert boolean;
BEGIN
    -- Only a pinned preparing migration may INSERT historical job provenance.
    -- UPDATEs, runtime creation and assets always require the current live fence.
    backfill_insert := TG_TABLE_NAME = 'partition_jobs' AND TG_OP = 'INSERT'
        AND coalesce(knowledge_engine.phase2_backfill_allowed(NEW.workspace_key), false);
    SELECT * INTO fence FROM knowledge_engine.partition_sources
        WHERE workspace_key = NEW.workspace_key AND source_id = NEW.source_id FOR UPDATE;
    IF NOT FOUND OR fence.deleted OR NEW.generation > fence.generation
       OR (NEW.generation < fence.generation AND NOT backfill_insert) THEN
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
    IF backfill_insert THEN
        RETURN NEW;
    END IF;
    IF TG_TABLE_NAME = 'partition_jobs' AND TG_OP = 'UPDATE'
       AND NEW.status IN ('pending_ai','running','completed') AND EXISTS (
        SELECT 1 FROM knowledge_engine.partition_jobs j WHERE j.workspace_key=NEW.workspace_key
          AND j.source_id=NEW.source_id AND j.generation=NEW.generation AND j.chunk_id=NEW.chunk_id
          AND j.extraction_version>NEW.extraction_version
       ) THEN RAISE EXCEPTION 'partition extraction version is superseded' USING ERRCODE='23514'; END IF;
    IF TG_TABLE_NAME = 'partition_jobs' THEN
        IF TG_OP = 'INSERT' AND (NEW.status <> 'pending_ai' OR NEW.claim_token IS NOT NULL) THEN
            RAISE EXCEPTION 'partition initial job state rejected' USING ERRCODE = '23514';
        ELSIF TG_OP = 'INSERT' AND NEW.extraction_version <> (
            SELECT coalesce(max(extraction_version), 0) + 1 FROM knowledge_engine.partition_jobs
            WHERE workspace_key = NEW.workspace_key AND source_id = NEW.source_id
              AND generation = NEW.generation AND chunk_id = NEW.chunk_id
        ) THEN
            RAISE EXCEPTION 'partition extraction version rejected' USING ERRCODE = '23514';
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
        IF TG_OP = 'UPDATE' AND (NEW.asset_id <> OLD.asset_id OR NEW.job_id <> OLD.job_id) THEN
            RAISE EXCEPTION 'partition asset identity rejected' USING ERRCODE = '23514';
        END IF;
        IF TG_OP = 'INSERT' AND NOT EXISTS (
            SELECT 1 FROM knowledge_engine.partition_jobs j
            WHERE j.workspace_key = NEW.workspace_key AND j.job_id = NEW.job_id AND j.status = 'running'
        ) THEN RAISE EXCEPTION 'partition asset job is not running' USING ERRCODE = '23514'; END IF;
        IF TG_OP = 'UPDATE' AND NOT OLD.active AND NEW.active THEN
            RAISE EXCEPTION 'partition supersession is irreversible' USING ERRCODE = '23514';
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

-- API payloads are generated projections in the same row, never independent
-- status/token authorities. They preserve historical optional fields/spelling.
CREATE FUNCTION knowledge_engine.sync_phase2_job() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE data jsonb; k text; v jsonb;
BEGIN
 IF NEW.api_payload IS NULL THEN RETURN NEW; END IF;
 data := NEW.api_payload || jsonb_build_object('id', NEW.job_id, 'source_id', NEW.source_id,
   'chunk_id', NEW.chunk_id, 'status', NEW.status);
 data := data || NEW.metadata;
 FOREACH k IN ARRAY ARRAY['created_at','started_at','completed_at','recovered_at'] LOOP
   IF k='started_at' AND NOT data ? k AND NEW.metadata->>'provider' IS NULL THEN CONTINUE; END IF;
   v := to_jsonb(NEW)->k;
   IF data ? k AND (data->>k)::timestamptz IS NOT DISTINCT FROM (to_jsonb(NEW)->>k)::timestamptz THEN
     CONTINUE;
   END IF;
   IF v <> 'null'::jsonb OR data ? k THEN data := jsonb_set(data, ARRAY[k], v); END IF;
 END LOOP;
 IF data ? 'extraction_version' THEN data := jsonb_set(data, '{extraction_version}', to_jsonb(NEW.extraction_version)); END IF;
 data := data - 'claim_token' - '_partition';
 NEW.api_payload := data;
 RETURN NEW;
END $$;
CREATE TRIGGER sync_phase2_job BEFORE INSERT OR UPDATE ON knowledge_engine.partition_jobs
 FOR EACH ROW EXECUTE FUNCTION knowledge_engine.sync_phase2_job();

CREATE FUNCTION knowledge_engine.sync_phase2_source() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE data jsonb;
BEGIN
 IF NEW.api_payload IS NULL THEN RETURN NEW; END IF;
 data := NEW.api_payload;
 IF data ? 'processing_status' OR NEW.interpretation_status IS NOT NULL THEN
  data := data || jsonb_build_object('processing_status',NEW.interpretation_status);
 END IF;
 IF data ? 'stopped_reason' OR NEW.stopped_reason IS NOT NULL THEN
  data := data || jsonb_build_object('stopped_reason',NEW.stopped_reason);
 END IF;
 IF data ? 'generation' THEN data := data || jsonb_build_object('generation',NEW.generation); END IF;
 IF data ? 'deleted' THEN data := data || jsonb_build_object('deleted',NEW.deleted); END IF;
 NEW.api_payload := data;
 RETURN NEW;
END $$;
CREATE TRIGGER sync_phase2_source BEFORE INSERT OR UPDATE ON knowledge_engine.partition_sources
 FOR EACH ROW EXECUTE FUNCTION knowledge_engine.sync_phase2_source();

CREATE FUNCTION knowledge_engine.guard_phase2_core() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE active boolean;
BEGIN
 active := OLD.payload->'partition'->>'state' = 'active' AND OLD.payload->'partition'->>'version' = '2';
 IF active AND NEW.payload->'partition' IS DISTINCT FROM OLD.payload->'partition'
    AND current_setting('knowledge_engine.phase2_rollback',true) IS DISTINCT FROM 'on' THEN
  RAISE EXCEPTION 'phase2 authority marker cannot be removed' USING ERRCODE='23514';
 END IF;
 IF NEW.payload->'partition'->>'state' = 'active' AND NEW.payload->'partition'->>'version' = '2' THEN
  IF NEW.payload ? 'extraction_jobs' OR EXISTS (
    SELECT 1 FROM jsonb_array_elements(NEW.payload->'sources') s
    WHERE s ?| ARRAY['processing_status','stopped_reason','generation','deleted','interruption_reason']
  ) THEN RAISE EXCEPTION 'phase2 core contains narrow-owned fields' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_phase2_core BEFORE UPDATE ON knowledge_engine.state_snapshots
 FOR EACH ROW EXECUTE FUNCTION knowledge_engine.guard_phase2_core();
REVOKE ALL ON FUNCTION knowledge_engine.phase2_backfill_allowed(text), knowledge_engine.phase2_restart_after_rollback_allowed(text,bigint,text), knowledge_engine.phase2_restart_after_revision_drift_allowed(text,bigint,text), knowledge_engine.guard_partition_migration_attempt_history(), knowledge_engine.sync_phase2_job(),
 knowledge_engine.guard_phase2_core(), knowledge_engine.sync_phase2_source() FROM PUBLIC;
COMMIT;
