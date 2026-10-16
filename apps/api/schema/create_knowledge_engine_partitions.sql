-- Phase 1 additive schema ONLY. Not applied automatically or to production.
-- No backfill, authority activation, or snapshot compaction.
BEGIN;
CREATE SCHEMA IF NOT EXISTS knowledge_engine;

CREATE TABLE knowledge_engine.partition_sources (
    workspace_key text NOT NULL,
    source_id text NOT NULL CHECK (source_id <> ''),
    generation bigint NOT NULL DEFAULT 1 CHECK (generation > 0),
    deleted boolean NOT NULL DEFAULT false,
    interpretation_status text,
    stopped_reason text,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, source_id)
);

CREATE TABLE knowledge_engine.partition_jobs (
    workspace_key text NOT NULL,
    job_id text NOT NULL CHECK (job_id <> ''),
    source_id text NOT NULL,
    chunk_id text NOT NULL CHECK (chunk_id <> ''),
    generation bigint NOT NULL CHECK (generation > 0),
    extraction_version bigint NOT NULL CHECK (extraction_version > 0),
    status text NOT NULL DEFAULT 'pending_ai'
        CHECK (status IN ('pending_ai', 'running', 'completed', 'failed')),
    claim_token text CHECK (claim_token <> ''),
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    metadata jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,
    recovered_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, job_id),
    FOREIGN KEY (workspace_key, source_id)
        REFERENCES knowledge_engine.partition_sources (workspace_key, source_id),
    UNIQUE (workspace_key, source_id, generation, chunk_id, extraction_version),
    UNIQUE (workspace_key, job_id, source_id, generation, chunk_id, extraction_version),
    CHECK (metadata - ARRAY['provider', 'model', 'model_response_id', 'asset_count', 'error'] = '{}'::jsonb),
    CHECK ((status = 'running') = (claim_token IS NOT NULL)),
    CHECK (status <> 'running' OR started_at IS NOT NULL),
    CHECK ((status = 'completed') = (completed_at IS NOT NULL))
);
-- Pending and running share one slot, so concurrent creation cannot bypass claim.
CREATE UNIQUE INDEX partition_jobs_live_chunk ON knowledge_engine.partition_jobs
    (workspace_key, source_id, generation, chunk_id)
    WHERE status IN ('pending_ai', 'running');
CREATE INDEX partition_jobs_source ON knowledge_engine.partition_jobs
    (workspace_key, source_id, generation, created_at, job_id);
CREATE INDEX partition_jobs_chunk ON knowledge_engine.partition_jobs
    (workspace_key, source_id, generation, chunk_id, created_at, job_id);

CREATE TABLE knowledge_engine.partition_assets (
    workspace_key text NOT NULL,
    asset_id text NOT NULL CHECK (asset_id <> ''),
    source_id text NOT NULL,
    chunk_id text NOT NULL,
    generation bigint NOT NULL CHECK (generation > 0),
    extraction_version bigint NOT NULL CHECK (extraction_version > 0),
    job_id text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    superseded_by_job_id text,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, asset_id),
    FOREIGN KEY (workspace_key, job_id, source_id, generation, chunk_id, extraction_version)
        REFERENCES knowledge_engine.partition_jobs
        (workspace_key, job_id, source_id, generation, chunk_id, extraction_version),
    FOREIGN KEY (workspace_key, superseded_by_job_id)
        REFERENCES knowledge_engine.partition_jobs (workspace_key, job_id),
    CHECK (NOT active OR superseded_by_job_id IS NULL),
    CHECK (payload->>'id' IS NOT DISTINCT FROM asset_id),
    CHECK (payload->>'source_id' IS NOT DISTINCT FROM source_id),
    CHECK (payload->>'chunk_id' IS NOT DISTINCT FROM chunk_id)
);
CREATE INDEX partition_assets_active_chunk ON knowledge_engine.partition_assets
    (workspace_key, source_id, generation, chunk_id, extraction_version, asset_id)
    WHERE active;
CREATE INDEX partition_assets_source ON knowledge_engine.partition_assets
    (workspace_key, source_id, generation, asset_id);

-- Operation identity binds the entire command; a changed command cannot reuse it.
CREATE TABLE knowledge_engine.partition_operations (
    workspace_key text NOT NULL,
    operation_id text NOT NULL CHECK (operation_id <> ''),
    request jsonb NOT NULL CHECK (jsonb_typeof(request) = 'object'),
    result jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, operation_id),
    CHECK (result IS NULL OR jsonb_typeof(result) = 'object')
);
-- Staging checkpoints only. The future core snapshot marker is the authority
-- switch; no active-state mutator exists in Phase 1.
CREATE TABLE knowledge_engine.partition_migrations (
    workspace_key text PRIMARY KEY,
    migration_id text NOT NULL CHECK (migration_id <> ''),
    partition_version integer NOT NULL CHECK (partition_version > 0),
    source_snapshot_revision bigint NOT NULL CHECK (source_snapshot_revision >= 0),
    stage text NOT NULL DEFAULT 'preparing' CHECK (stage IN ('preparing', 'verified')),
    checkpoint jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(checkpoint) = 'object'),
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Backend-only schema: no Data API policies or public execution rights added.
ALTER TABLE knowledge_engine.partition_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_engine.partition_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_engine.partition_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_engine.partition_operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_engine.partition_migrations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON knowledge_engine.partition_sources, knowledge_engine.partition_jobs,
    knowledge_engine.partition_assets, knowledge_engine.partition_operations,
    knowledge_engine.partition_migrations FROM PUBLIC;

CREATE FUNCTION knowledge_engine.guard_partition_source() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.workspace_key <> OLD.workspace_key OR NEW.source_id <> OLD.source_id
           OR NEW.revision <> OLD.revision + 1 OR NEW.created_at IS DISTINCT FROM OLD.created_at
           OR NEW.generation NOT IN (OLD.generation, OLD.generation + 1)
           OR (OLD.deleted AND NOT NEW.deleted)
           OR (NOT OLD.deleted AND NEW.deleted AND NEW.generation <> OLD.generation + 1)
        THEN RAISE EXCEPTION 'partition source transition rejected' USING ERRCODE = '23514'; END IF;
    ELSIF NEW.generation <> 1 OR NEW.revision <> 1 OR NEW.deleted THEN
        RAISE EXCEPTION 'partition source initialization rejected' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_partition_source BEFORE INSERT OR UPDATE
    ON knowledge_engine.partition_sources FOR EACH ROW
    EXECUTE FUNCTION knowledge_engine.guard_partition_source();

CREATE FUNCTION knowledge_engine.guard_partition_record() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE fence knowledge_engine.partition_sources%ROWTYPE;
BEGIN
    SELECT * INTO fence FROM knowledge_engine.partition_sources
        WHERE workspace_key = NEW.workspace_key AND source_id = NEW.source_id FOR UPDATE;
    IF NOT FOUND OR fence.deleted OR fence.generation <> NEW.generation THEN
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
CREATE TRIGGER guard_partition_job BEFORE INSERT OR UPDATE
    ON knowledge_engine.partition_jobs FOR EACH ROW
    EXECUTE FUNCTION knowledge_engine.guard_partition_record();
CREATE TRIGGER guard_partition_asset BEFORE INSERT OR UPDATE
    ON knowledge_engine.partition_assets FOR EACH ROW
    EXECUTE FUNCTION knowledge_engine.guard_partition_record();
CREATE FUNCTION knowledge_engine.guard_partition_migration() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.workspace_key <> OLD.workspace_key OR NEW.migration_id <> OLD.migration_id
           OR NEW.partition_version <> OLD.partition_version
           OR NEW.source_snapshot_revision <> OLD.source_snapshot_revision
           OR NEW.revision <> OLD.revision + 1 OR OLD.stage <> 'preparing'
        THEN RAISE EXCEPTION 'partition migration transition rejected' USING ERRCODE = '23514'; END IF;
    ELSIF NEW.revision <> 1 OR NEW.stage <> 'preparing' THEN
        RAISE EXCEPTION 'partition migration initialization rejected' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_partition_migration BEFORE INSERT OR UPDATE
    ON knowledge_engine.partition_migrations FOR EACH ROW
    EXECUTE FUNCTION knowledge_engine.guard_partition_migration();
REVOKE ALL ON FUNCTION knowledge_engine.guard_partition_migration() FROM PUBLIC;
REVOKE ALL ON FUNCTION knowledge_engine.guard_partition_source(),
    knowledge_engine.guard_partition_record() FROM PUBLIC;
COMMIT;
