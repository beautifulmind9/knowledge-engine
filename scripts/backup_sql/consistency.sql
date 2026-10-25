\pset tuples_only on
\pset format unaligned
\set ON_ERROR_STOP on

SELECT jsonb_build_object(
    'revision', snapshot.revision,
    'snapshot_updated_at', snapshot.updated_at,
    'partition_marker', snapshot.payload->'partition',
    'source_count', jsonb_array_length(snapshot.payload->'sources'),
    'asset_count', jsonb_array_length(snapshot.payload->'knowledge_assets'),
    'job_count', jsonb_array_length(snapshot.payload->'extraction_jobs'),
    'output_count', jsonb_array_length(snapshot.payload->'outputs'),
    'allowance', to_jsonb(allowance),
    'reservation_count', (
        SELECT count(*)
        FROM knowledge_engine.allowance_reservations AS reservation
        WHERE reservation.workspace_key = snapshot.workspace_key
    )
)::text
FROM knowledge_engine.state_snapshots AS snapshot
LEFT JOIN knowledge_engine.allowance_state AS allowance
    ON allowance.workspace_key = snapshot.workspace_key
WHERE snapshot.workspace_key = :'workspace';
