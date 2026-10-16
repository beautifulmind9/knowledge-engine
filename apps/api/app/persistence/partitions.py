"""Dormant hosted partition primitives. No routes, snapshot loads or cutover.

Use apply() for a short atomic group of operations. It returns replayed=True
when an operation was already committed: replay is NEVER dispatch permission.
An uncertain commit raises; read_operation() can confirm the durable result.
Callers may supply an existing connection to share a core-state transaction.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import TypeAdapter

from app.models.knowledge_asset import KnowledgeAsset
from app.persistence.postgres import HostedStateStoreError

PARTITION_VERSION = 1
_ASSET = TypeAdapter(KnowledgeAsset)


class PartitionConflict(RuntimeError):
    """A revision, generation, claim, identity or operation conflicted."""


class PartitionVersionError(RuntimeError):
    """An unsupported or malformed partition marker must fail closed."""


@dataclass(frozen=True)
class PartitionMutation:
    value: dict[str, Any]
    replayed: bool


def snapshot_authority(snapshot: dict[str, Any]) -> str:
    """Pure future-reader compatibility check; never called by live loaders yet."""
    if "partition" not in snapshot:
        return "legacy"
    marker = snapshot["partition"]
    if (not isinstance(marker, dict) or type(marker.get("version")) is not int
            or marker["version"] != PARTITION_VERSION
            or marker.get("state") not in {"preparing", "active"}):
        raise PartitionVersionError("Unsupported or malformed partition marker.")
    return "partitioned" if marker["state"] == "active" else "legacy"


def _required(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A nonempty partition identifier is required.")
    return value


class PostgresPartitionStore:
    def __init__(self, database_url: str, workspace_key: str):
        for name, value in (("KNOWLEDGE_ENGINE_DATABASE_URL", database_url),
                            ("KNOWLEDGE_ENGINE_WORKSPACE_KEY", workspace_key)):
            if not value or not value.strip():
                raise RuntimeError(f"Hosted partition storage requires {name}.")
        self._database_url = database_url
        self._workspace_key = workspace_key

    @contextmanager
    def transaction(self, connection=None):
        """Borrowed connections use a savepoint; the owner commits core + narrow.

        The connection must already be in a transaction when borrowed. It is not
        retained on the store. No automatic transaction/provider retries occur.
        """
        try:
            if connection is None:
                with psycopg.connect(self._database_url, connect_timeout=10) as owned:
                    yield PartitionTransaction(owned, self._workspace_key)
            else:
                if connection.info.transaction_status != psycopg.pq.TransactionStatus.INTRANS:
                    raise ValueError("A borrowed partition connection requires an outer transaction.")
                with connection.transaction():
                    yield PartitionTransaction(connection, self._workspace_key)
        except psycopg.IntegrityError:
            raise PartitionConflict("Partition constraint or concurrent mutation rejected.") from None
        except psycopg.Error:
            raise HostedStateStoreError("Hosted partition operation failed; commit may be uncertain.") from None

    def apply(self, operation_id: str, request: dict, mutate: Callable, *, connection=None) -> PartitionMutation:
        """Bind ID to the full immutable command, commit result with mutations.

        request must describe ALL inputs (including expected revisions/tokens).
        A replay returns the original result, not a fresh view.
        """
        _required(operation_id)
        if not isinstance(request, dict):
            raise ValueError("A partition operation requires an object command.")
        with self.transaction(connection) as tx:
            inserted = tx._one(
                "INSERT INTO knowledge_engine.partition_operations (workspace_key, operation_id, request) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING RETURNING operation_id",
                (tx.workspace, operation_id, Jsonb(request)),
            )
            operation = tx._one(
                "SELECT request, result FROM knowledge_engine.partition_operations "
                "WHERE workspace_key = %s AND operation_id = %s FOR UPDATE",
                (tx.workspace, operation_id),
            )
            if operation["request"] != request:
                raise PartitionConflict("Partition operation ID was reused with different inputs.")
            if inserted is None:
                if not isinstance(operation["result"], dict):
                    raise PartitionConflict("Partition operation has no confirmed result.")
                result = PartitionMutation(operation["result"], True)
            else:
                value = mutate(tx)
                if not isinstance(value, dict):
                    raise ValueError("A partition mutation must return an object result.")
                tx._one(
                    "UPDATE knowledge_engine.partition_operations SET result = %s "
                    "WHERE workspace_key = %s AND operation_id = %s RETURNING operation_id",
                    (Jsonb(value), tx.workspace, operation_id),
                )
                result = PartitionMutation(value, False)
        return result

    def read_operation(self, operation_id):
        with self.transaction() as tx:
            return tx._one("SELECT request, result FROM knowledge_engine.partition_operations "
                           "WHERE workspace_key = %s AND operation_id = %s", (tx.workspace, operation_id))

    def read_source(self, source_id):
        with self.transaction() as tx:
            return tx.read_source(source_id)

    def read_job(self, job_id):
        with self.transaction() as tx:
            return tx.read_job(job_id)

    def query_jobs(self, source_id, generation, *, chunk_id=None):
        with self.transaction() as tx:
            return tx.query_jobs(source_id, generation, chunk_id=chunk_id)

    def query_assets(self, source_id, generation, *, chunk_id=None, active=None):
        with self.transaction() as tx:
            return tx.query_assets(source_id, generation, chunk_id=chunk_id, active=active)

    def assets_by_ids(self, asset_ids):
        if not asset_ids:
            return []
        with self.transaction() as tx:
            return tx.assets_by_ids(asset_ids)

    def read_migration(self):
        with self.transaction() as tx:
            return tx.read_migration()


class PartitionTransaction:
    """Workspace-scoped relational operations on one transaction/connection.

    Intended for apply() or a shared transaction, not a live interpretation API.
    Returned records contain relational envelope + metadata/payload; reconstruct
    existing DTOs at a future cutover, never use JSON as another status authority.
    """
    def __init__(self, connection, workspace):
        self.connection = connection
        self.workspace = workspace

    def _all(self, sql, params=()):
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    def _one(self, sql, params=()):
        rows = self._all(sql, params)
        return rows[0] if rows else None

    @staticmethod
    def _expect(row):
        if row is None:
            raise PartitionConflict("Partition revision, generation or claim is stale.")
        return row

    @staticmethod
    def _json_record(row):
        # row_to_json yields JSON-safe timestamps, usable for operation receipts.
        return row["record"] if row else None

    def read_source(self, source_id):
        return self._json_record(self._one(
            "SELECT row_to_json(s) AS record FROM knowledge_engine.partition_sources s "
            "WHERE workspace_key = %s AND source_id = %s", (self.workspace, source_id)))

    def create_source(self, source_id):
        return self._json_record(self._one(
            "INSERT INTO knowledge_engine.partition_sources AS s (workspace_key, source_id) "
            "VALUES (%s, %s) RETURNING row_to_json(s) AS record", (self.workspace, _required(source_id))))

    def _fence(self, source_id, generation):
        return self._expect(self._one(
            "SELECT revision FROM knowledge_engine.partition_sources "
            "WHERE workspace_key = %s AND source_id = %s AND generation = %s AND NOT deleted FOR UPDATE",
            (self.workspace, source_id, generation)))

    def advance_generation(self, source_id, generation, revision, *, deleted=False):
        return self._json_record(self._expect(self._one(
            "UPDATE knowledge_engine.partition_sources AS s SET generation = generation + 1, "
            "deleted = %s, interpretation_status = NULL, stopped_reason = NULL, "
            "revision = revision + 1, updated_at = now() "
            "WHERE workspace_key = %s AND source_id = %s AND generation = %s AND revision = %s "
            "AND NOT deleted RETURNING row_to_json(s) AS record",
            (deleted, self.workspace, source_id, generation, revision))))

    def update_source(self, source_id, generation, revision, *, status, stopped_reason=None):
        return self._json_record(self._expect(self._one(
            "UPDATE knowledge_engine.partition_sources AS s SET interpretation_status = %s, stopped_reason = %s, "
            "revision = revision + 1, updated_at = now() WHERE workspace_key = %s AND source_id = %s "
            "AND generation = %s AND revision = %s AND NOT deleted RETURNING row_to_json(s) AS record",
            (status, stopped_reason, self.workspace, source_id, generation, revision))))

    def read_job(self, job_id):
        return self._json_record(self._one(
            "SELECT row_to_json(j) AS record FROM knowledge_engine.partition_jobs j "
            "WHERE workspace_key = %s AND job_id = %s", (self.workspace, job_id)))

    def query_jobs(self, source_id, generation, *, chunk_id=None):
        return [r["record"] for r in self._all(
            "SELECT row_to_json(j) AS record FROM knowledge_engine.partition_jobs j "
            "WHERE workspace_key = %s AND source_id = %s AND generation = %s "
            + ("AND chunk_id = %s " if chunk_id is not None else "")
            + "ORDER BY created_at, job_id",
            (self.workspace, source_id, generation) + ((chunk_id,) if chunk_id is not None else ()))]

    def create_job(self, job_id, source_id, chunk_id, generation, extraction_version, *, metadata=None):
        self._fence(source_id, generation)
        return self._json_record(self._one(
            "INSERT INTO knowledge_engine.partition_jobs AS j "
            "(workspace_key, job_id, source_id, chunk_id, generation, extraction_version, metadata) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING row_to_json(j) AS record",
            (self.workspace, _required(job_id), source_id, _required(chunk_id), generation,
             extraction_version, Jsonb(self._metadata(metadata)))))

    @staticmethod
    def _metadata(metadata):
        metadata = {} if metadata is None else metadata
        if not isinstance(metadata, dict) or set(metadata) - {
            "provider", "model", "model_response_id", "asset_count", "error",
        }:
            raise ValueError("Job metadata contains unsupported or authoritative fields.")
        return metadata

    def _job_fence(self, job_id, generation):
        # Read identity before taking source lock; identity is immutable and the
        # subsequent guarded UPDATE verifies revision/status after the lock.
        job = self._expect(self.read_job(job_id))
        self._fence(job["source_id"], generation)
        if job["generation"] != generation:
            raise PartitionConflict("Partition job generation is stale.")
        return job

    def claim_job(self, job_id, generation, revision, claim_token, *, provider, model):
        self._job_fence(job_id, generation)
        return self._json_record(self._expect(self._one(
            "UPDATE knowledge_engine.partition_jobs AS j SET status = 'running', claim_token = %s, "
            "started_at = now(), metadata = metadata || %s, revision = revision + 1, updated_at = now() "
            "WHERE workspace_key = %s AND job_id = %s AND generation = %s AND revision = %s "
            "AND status = 'pending_ai' RETURNING row_to_json(j) AS record",
            (_required(claim_token), Jsonb({"provider": provider, "model": model, "error": None}),
             self.workspace, job_id, generation, revision))))

    def finish_job(self, job_id, generation, revision, claim_token, *, status, metadata=None):
        """Guarded terminal transition only; caller composes assets in same tx.

        No provider dispatch, application checkpoint, or live completion cutover.
        """
        if status not in {"completed", "failed"}:
            raise ValueError("A terminal job transition requires completed or failed.")
        self._job_fence(job_id, generation)
        return self._json_record(self._expect(self._one(
            "UPDATE knowledge_engine.partition_jobs AS j SET status = %s, claim_token = NULL, "
            "completed_at = CASE WHEN %s = 'completed' THEN now() ELSE NULL END, "
            "metadata = metadata || %s, revision = revision + 1, updated_at = now() "
            "WHERE workspace_key = %s AND job_id = %s AND generation = %s AND revision = %s "
            "AND status = 'running' AND claim_token = %s RETURNING row_to_json(j) AS record",
            (status, status, Jsonb(self._metadata(metadata)), self.workspace, job_id, generation,
             revision, claim_token))))

    def recover_job(self, job_id, generation, revision):
        """Explicit recovery only; DB clock enforces existing ten-minute rule."""
        self._job_fence(job_id, generation)
        return self._json_record(self._expect(self._one(
            "UPDATE knowledge_engine.partition_jobs AS j SET status = 'pending_ai', claim_token = NULL, "
            "completed_at = NULL, recovered_at = now(), metadata = metadata || '{\"error\":null}'::jsonb, "
            "revision = revision + 1, updated_at = now() "
            "WHERE workspace_key = %s AND job_id = %s AND generation = %s AND revision = %s "
            "AND (status = 'failed' OR (status = 'running' AND started_at <= now() - interval '10 minutes')) "
            "RETURNING row_to_json(j) AS record", (self.workspace, job_id, generation, revision))))

    def _running(self, job_id, generation, revision, claim_token):
        self._job_fence(job_id, generation)
        return self._expect(self._one(
            "SELECT * FROM knowledge_engine.partition_jobs WHERE workspace_key = %s AND job_id = %s "
            "AND generation = %s AND revision = %s AND status = 'running' AND claim_token = %s FOR UPDATE",
            (self.workspace, job_id, generation, revision, claim_token)))

    def insert_assets(self, job_id, generation, revision, claim_token, assets):
        """Validate the full batch, then one set-based INSERT; never per-asset IO."""
        job = self._running(job_id, generation, revision, claim_token)
        values = []
        for value in assets:
            asset = _ASSET.validate_python(value).model_dump(mode="json")
            if (not asset["id"] or asset["source_id"] != job["source_id"]
                    or asset["chunk_id"] != job["chunk_id"]):
                raise ValueError("Asset identity and provenance must match its job.")
            values.append({"asset_id": asset["id"], "payload": asset})
        if not values:
            return {"inserted": 0}
        rows = self._all(
            "INSERT INTO knowledge_engine.partition_assets "
            "(workspace_key, asset_id, source_id, chunk_id, generation, extraction_version, job_id, payload) "
            "SELECT %s, v.asset_id, %s, %s, %s, %s, %s, v.payload "
            "FROM jsonb_to_recordset(%s) AS v(asset_id text, payload jsonb) RETURNING asset_id",
            (self.workspace, job["source_id"], job["chunk_id"], generation,
             job["extraction_version"], job_id, Jsonb(values)))
        return {"inserted": len(rows)}

    def supersede_assets(self, job_id, generation, revision, claim_token, *, expected_active_version):
        """CAS the active batch, including empty replacements, inside caller tx."""
        job = self._running(job_id, generation, revision, claim_token)
        versions = self._all(
            "SELECT DISTINCT extraction_version FROM knowledge_engine.partition_assets "
            "WHERE workspace_key = %s AND source_id = %s AND generation = %s AND chunk_id = %s AND active",
            (self.workspace, job["source_id"], generation, job["chunk_id"]))
        # A completed empty replacement still has an extraction version. Derive
        # the winner from completed jobs, never a second active-batch counter.
        completed = self._one(
            "SELECT max(extraction_version) AS version FROM knowledge_engine.partition_jobs "
            "WHERE workspace_key = %s AND source_id = %s AND generation = %s AND chunk_id = %s "
            "AND status = 'completed'",
            (self.workspace, job["source_id"], generation, job["chunk_id"]))
        actual = sorted({v["extraction_version"] for v in versions}
                        | ({completed["version"]} if completed["version"] is not None else set()))
        expected = [] if expected_active_version is None else [expected_active_version]
        if actual != expected or any(v >= job["extraction_version"] for v in actual):
            raise PartitionConflict("Partition active extraction version changed.")
        rows = self._all(
            "UPDATE knowledge_engine.partition_assets SET active = false, superseded_by_job_id = %s, "
            "revision = revision + 1, updated_at = now() WHERE workspace_key = %s AND source_id = %s "
            "AND generation = %s AND chunk_id = %s AND active RETURNING asset_id",
            (job_id, self.workspace, job["source_id"], generation, job["chunk_id"]))
        return {"superseded": len(rows)}

    def query_assets(self, source_id, generation, *, chunk_id=None, active=None):
        clauses = ["workspace_key = %s", "source_id = %s", "generation = %s"]
        params = [self.workspace, source_id, generation]
        for column, value in (("chunk_id", chunk_id), ("active", active)):
            if value is not None:
                clauses.append(column + " = %s")
                params.append(value)
        if active is True:
            clauses.append("EXISTS (SELECT 1 FROM knowledge_engine.partition_sources s "
                           "WHERE s.workspace_key = a.workspace_key AND s.source_id = a.source_id "
                           "AND s.generation = a.generation AND NOT s.deleted)")
        return [r["record"] for r in self._all(
            "SELECT row_to_json(a) AS record FROM knowledge_engine.partition_assets a WHERE "
            + " AND ".join(clauses) + " ORDER BY asset_id", tuple(params))]

    def assets_by_ids(self, asset_ids):
        if not asset_ids:
            return []
        return [r["record"] for r in self._all(
            "SELECT row_to_json(a) AS record FROM knowledge_engine.partition_assets a "
            "WHERE workspace_key = %s AND asset_id = ANY(%s) ORDER BY asset_id",
            (self.workspace, list(asset_ids)))]

    def read_migration(self):
        row = self._json_record(self._one(
            "SELECT row_to_json(m) AS record FROM knowledge_engine.partition_migrations m "
            "WHERE workspace_key = %s", (self.workspace,)))
        if row and row["partition_version"] != PARTITION_VERSION:
            raise PartitionVersionError("Unsupported partition staging version.")
        return row

    def prepare_migration(self, migration_id, source_snapshot_revision):
        """Staging only: never reads/changes a snapshot or activates authority."""
        return self._json_record(self._one(
            "INSERT INTO knowledge_engine.partition_migrations AS m "
            "(workspace_key, migration_id, partition_version, source_snapshot_revision) "
            "VALUES (%s, %s, %s, %s) RETURNING row_to_json(m) AS record",
            (self.workspace, _required(migration_id), PARTITION_VERSION, source_snapshot_revision)))

    def checkpoint_migration(self, migration_id, revision, source_snapshot_revision, checkpoint, *, verified=False):
        self.read_migration()  # Fail closed on unsupported version before any update.
        if not isinstance(checkpoint, dict):
            raise ValueError("Migration checkpoints must be objects.")
        return self._json_record(self._expect(self._one(
            "UPDATE knowledge_engine.partition_migrations AS m SET checkpoint = %s, stage = %s, "
            "revision = revision + 1, updated_at = now() WHERE workspace_key = %s AND migration_id = %s "
            "AND partition_version = %s AND revision = %s AND source_snapshot_revision = %s "
            "AND stage = 'preparing' RETURNING row_to_json(m) AS record",
            (Jsonb(checkpoint), "verified" if verified else "preparing", self.workspace,
             migration_id, PARTITION_VERSION, revision, source_snapshot_revision))))
