"""Complete JSONB snapshots with optimistic concurrency and short transactions."""
from threading import RLock
from typing import Any

import psycopg
from psycopg.types.json import Jsonb


class StaleStateWriteError(RuntimeError):
    """The workspace changed since this adapter last loaded or saved it."""


class HostedStateStoreError(RuntimeError):
    """A hosted database operation failed; driver details may contain secrets."""


class HostedStateIntegrityError(HostedStateStoreError):
    """An existing row does not contain a dictionary snapshot."""


STALE_WRITE_MESSAGE = "Hosted state save rejected: stale revision or concurrent writer. Reload before saving."


class PostgresStateStore:
    def __init__(self, database_url: str, workspace_key: str):
        for name, value in (("KNOWLEDGE_ENGINE_DATABASE_URL", database_url),
                            ("KNOWLEDGE_ENGINE_WORKSPACE_KEY", workspace_key)):
            if not value or not value.strip():
                raise RuntimeError(f"Hosted StateStore requires {name}.")
        self._database_url = database_url
        self._workspace_key = workspace_key
        self._revision: int | None = None
        self._loaded = False
        # Serialize operations on the shared adapter; independent adapters use SQL CAS.
        self._lock = RLock()

    def load(self) -> dict[str, Any] | None:
        with self._lock:
            self._loaded = False
            try:
                with psycopg.connect(self._database_url, connect_timeout=10) as connection:
                    row = connection.execute(
                        "SELECT payload, revision FROM knowledge_engine.state_snapshots "
                        "WHERE workspace_key = %s", (self._workspace_key,)
                    ).fetchone()
                    if row is not None and not isinstance(row[0], dict):
                        raise HostedStateIntegrityError(
                            "Hosted state load failed: stored payload must be a dictionary JSON snapshot."
                        )
            except (psycopg.Error, ValueError):
                # Never expose DSNs, workspace keys, payloads, or driver diagnostics.
                raise HostedStateStoreError("Hosted state load failed: database operation failed.") from None
            self._revision = row[1] if row is not None else None
            self._loaded = True
            return row[0] if row is not None else None

    def save(self, state: dict[str, Any]) -> None:
        with self._lock:
            if not self._loaded:
                raise RuntimeError("Hosted StateStore requires load() before save().")
            try:
                with psycopg.connect(self._database_url, connect_timeout=10) as connection:
                    if self._revision is None:
                        row = connection.execute(
                            "INSERT INTO knowledge_engine.state_snapshots "
                            "(workspace_key, payload, revision) VALUES (%s, %s, 1) "
                            "ON CONFLICT (workspace_key) DO NOTHING RETURNING revision",
                            (self._workspace_key, Jsonb(state)),
                        ).fetchone()
                    else:
                        row = connection.execute(
                            "UPDATE knowledge_engine.state_snapshots "
                            "SET payload = %s, revision = revision + 1, updated_at = now() "
                            "WHERE workspace_key = %s AND revision = %s RETURNING revision",
                            (Jsonb(state), self._workspace_key, self._revision),
                        ).fetchone()
                    if row is None:
                        raise StaleStateWriteError(STALE_WRITE_MESSAGE)
                # Advance only after the connection context successfully commits.
            except (psycopg.Error, ValueError):
                raise HostedStateStoreError("Hosted state save failed: database operation failed.") from None
            self._revision = row[0]
