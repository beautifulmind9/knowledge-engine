-- Repository definition of the already-applied migration. Do not reapply remotely.
CREATE SCHEMA IF NOT EXISTS knowledge_engine;
CREATE TABLE knowledge_engine.state_snapshots (
    workspace_key text PRIMARY KEY,
    payload jsonb NOT NULL,
    revision bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
