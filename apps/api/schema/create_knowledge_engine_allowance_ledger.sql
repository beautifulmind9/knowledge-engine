-- Additive migration for independently durable hosted provider-attempt admission.
-- Apply before deploying code that uses the allowance ledger.
CREATE SCHEMA IF NOT EXISTS knowledge_engine;

CREATE TABLE knowledge_engine.allowance_state (
    workspace_key text PRIMARY KEY,
    accounting_day date,
    admitted_attempts integer NOT NULL DEFAULT 0 CHECK (admitted_attempts >= 0),
    paused boolean NOT NULL DEFAULT false,
    pause_reason text,
    last_attempt_at timestamptz,
    last_reservation_id text,
    migration_version integer NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE knowledge_engine.allowance_reservations (
    workspace_key text NOT NULL,
    reservation_id text NOT NULL,
    accounting_day date NOT NULL,
    admitted_attempt_number integer NOT NULL CHECK (admitted_attempt_number > 0),
    admitted_at timestamptz NOT NULL,
    PRIMARY KEY (workspace_key, reservation_id)
);
