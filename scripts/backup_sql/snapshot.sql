\pset tuples_only on
\pset format unaligned
\set ON_ERROR_STOP on

SELECT payload::text
FROM knowledge_engine.state_snapshots
WHERE workspace_key = :'workspace';
