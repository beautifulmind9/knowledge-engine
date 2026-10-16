"""Complete JSONB snapshots with optimistic concurrency and short transactions."""
from copy import deepcopy
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
        self._loaded_snapshot: dict[str, Any] | None = None
        # Serialize operations on the shared adapter; independent adapters use SQL CAS.
        self._lock = RLock()

    def load(self) -> dict[str, Any] | None:
        with self._lock:
            self._loaded = False
            try:
                with psycopg.connect(self._database_url, connect_timeout=10) as connection:
                    connection.isolation_level=psycopg.IsolationLevel.REPEATABLE_READ
                    row = connection.execute(
                        "SELECT payload, revision FROM knowledge_engine.state_snapshots "
                        "WHERE workspace_key = %s", (self._workspace_key,)
                    ).fetchone()
                    if row is not None and not isinstance(row[0], dict):
                        raise HostedStateIntegrityError(
                            "Hosted state load failed: stored payload must be a dictionary JSON snapshot."
                        )
                    if row is not None and row[0].get('partition') is not None:
                        from app.persistence.phase2 import active, Phase2Coordinator
                        from app.persistence.partitions import PartitionTransaction
                        active(row[0])
                        row = (Phase2Coordinator(self._database_url,self._workspace_key).compose(
                            PartitionTransaction(connection,self._workspace_key),row[0]),row[1])
            except (psycopg.Error, ValueError):
                # Never expose DSNs, workspace keys, payloads, or driver diagnostics.
                raise HostedStateStoreError("Hosted state load failed: database operation failed.") from None
            self._revision = row[1] if row is not None else None
            self._loaded = True
            self._loaded_snapshot = deepcopy(row[0]) if row is not None else None
            from app.db.request_state import view
            current=view.get()
            if current is not None:
                current['baseline']=deepcopy(self._loaded_snapshot)
                current['revision']=self._revision
            return row[0] if row is not None else None

    @property
    def phase2(self):
        from app.persistence.phase2 import active
        return active(self._loaded_snapshot)

    def accept_committed(self,state,revision):
        """Publish only a confirmed shared commit; never regress the process cache."""
        from app.db.request_state import view
        current=view.get()
        with self._lock:
            if self._revision is None or revision>=self._revision:
                self._revision=revision;self._loaded_snapshot=deepcopy(state)
                import sys
                db=sys.modules.get('app.db.mock_data')
                for name in ('libraries','sources','knowledge_assets','outputs'):
                    if db is not None:
                        list.__setitem__(getattr(db,name),slice(None),deepcopy(list(state.get(name,[]))))
        if current is not None:
            current['revision']=revision;current['baseline']=deepcopy(state)
            mapping={s['id']:s for s in state.get('sources',[])}
            for source in current['sources']:
                if source['id'] in mapping:
                    updated=deepcopy(mapping[source['id']]);source.clear();source.update(updated)


    def save(self, state: dict[str, Any]) -> None:
        if self.phase2:
            from app.persistence.phase2 import Phase2Coordinator
            from app.db.request_state import view
            current=view.get()
            baseline=current['baseline'] if current else self.loaded_snapshot
            revision=current['revision'] if current else self._revision
            coordinator=Phase2Coordinator(self._database_url,self._workspace_key)
            new_revision,core=coordinator.save_core(baseline,state,revision)
            # Only advance adapter/projection revision after the shared commit.
            composed=core
            self.accept_committed(composed,new_revision)
            return
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
            self._loaded_snapshot = deepcopy(state)

    @property
    def loaded_snapshot(self) -> dict[str, Any] | None:
        """Copy of the snapshot used for the current optimistic revision."""
        from app.db.request_state import view
        current=view.get()
        if current is not None and current.get('baseline') is not None:
            return deepcopy(current['baseline'])
        with self._lock:
            return deepcopy(self._loaded_snapshot)
