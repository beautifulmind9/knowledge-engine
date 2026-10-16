"""Atomic hosted provider-attempt allowance ledger.

Legacy usage remains in workspace snapshots for backup and rollback. After the
versioned migration succeeds, this record is authoritative for hosted admission.
"""
from datetime import date, datetime
from typing import Any

import psycopg


ALLOWANCE_MIGRATION_VERSION = 1


class AllowancePersistenceError(RuntimeError):
    """A hosted allowance operation failed or could not be confirmed safely."""


class AllowanceMigrationError(AllowancePersistenceError):
    """The hosted allowance ledger is not migrated to the expected version."""


class PostgresAllowanceStore:
    def __init__(self, database_url: str, workspace_key: str):
        if not database_url or not database_url.strip():
            raise RuntimeError("Hosted allowance storage requires KNOWLEDGE_ENGINE_DATABASE_URL.")
        if not workspace_key or not workspace_key.strip():
            raise RuntimeError("Hosted allowance storage requires KNOWLEDGE_ENGINE_WORKSPACE_KEY.")
        self._database_url = database_url
        self._workspace_key = workspace_key

    def _connect(self):
        return psycopg.connect(self._database_url, connect_timeout=10)

    @staticmethod
    def _legacy_value(legacy: dict[str, Any]) -> dict[str, Any]:
        raw_day = legacy.get("day")
        day = date.fromisoformat(raw_day) if isinstance(raw_day, str) and raw_day else None
        raw_last = legacy.get("last_attempt_at")
        last_attempt = datetime.fromisoformat(raw_last) if isinstance(raw_last, str) and raw_last else raw_last
        return {
            "accounting_day": day,
            "admitted_attempts": max(0, int(legacy.get("calls", 0) or 0)),
            "paused": bool(legacy.get("paused", False)),
            "pause_reason": legacy.get("reason"),
            "last_attempt_at": last_attempt,
            "last_reservation_id": legacy.get("last_reservation_id"),
        }

    @staticmethod
    def _as_state(row) -> dict[str, Any]:
        if row is None:
            raise AllowanceMigrationError("Hosted allowance ledger is not initialized.")
        day, calls, paused, reason, last_attempt, last_reservation, version = row
        if version != ALLOWANCE_MIGRATION_VERSION:
            raise AllowanceMigrationError("Hosted allowance ledger migration version is unsupported.")
        return {
            "day": day.isoformat() if day else None,
            "calls": int(calls),
            "paused": bool(paused),
            "reason": reason,
            "last_attempt_at": last_attempt.isoformat() if last_attempt else None,
            "last_reservation_id": str(last_reservation) if last_reservation else None,
            "migration_version": version,
        }

    def ensure_migrated(self, legacy_usage: dict[str, Any]) -> dict[str, Any]:
        """Seed once from the legacy snapshot and verify the inserted values."""
        seed = self._legacy_value(legacy_usage)
        inserted = False
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT accounting_day, admitted_attempts, paused, pause_reason, "
                    "last_attempt_at, last_reservation_id, migration_version "
                    "FROM knowledge_engine.allowance_state WHERE workspace_key = %s FOR UPDATE",
                    (self._workspace_key,),
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO knowledge_engine.allowance_state "
                        "(workspace_key, accounting_day, admitted_attempts, paused, pause_reason, "
                        "last_attempt_at, last_reservation_id, migration_version) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (workspace_key) DO NOTHING",
                        (self._workspace_key, seed["accounting_day"], seed["admitted_attempts"],
                         seed["paused"], seed["pause_reason"], seed["last_attempt_at"],
                         seed["last_reservation_id"], ALLOWANCE_MIGRATION_VERSION),
                    )
                    row = connection.execute(
                        "SELECT accounting_day, admitted_attempts, paused, pause_reason, "
                        "last_attempt_at, last_reservation_id, migration_version "
                        "FROM knowledge_engine.allowance_state WHERE workspace_key = %s FOR UPDATE",
                        (self._workspace_key,),
                    ).fetchone()
                    inserted = row is not None
                state = self._as_state(row)
                if inserted:
                    expected = {
                        "day": seed["accounting_day"].isoformat() if seed["accounting_day"] else None,
                        "calls": seed["admitted_attempts"],
                        "paused": seed["paused"],
                        "reason": seed["pause_reason"],
                        "last_attempt_at": seed["last_attempt_at"].isoformat()
                        if seed["last_attempt_at"] else None,
                    }
                    observed = {key: state[key] for key in expected}
                    if observed != expected:
                        raise AllowanceMigrationError("Hosted allowance migration verification failed.")
                return state
        except AllowancePersistenceError:
            raise
        except Exception:
            raise AllowancePersistenceError("Hosted allowance migration could not be verified.") from None

    def read(self, legacy_usage: dict[str, Any]) -> dict[str, Any]:
        return self.ensure_migrated(legacy_usage)

    def _lookup_reservation(self, reservation_id: str):
        with self._connect() as connection:
            return connection.execute(
                "SELECT accounting_day, admitted_attempt_number FROM "
                "knowledge_engine.allowance_reservations "
                "WHERE workspace_key = %s AND reservation_id = %s",
                (self._workspace_key, reservation_id),
            ).fetchone()

    def reserve_attempt(self, *, reservation_id: str, day: str, limit: int,
                        attempted_at: datetime) -> dict[str, Any]:
        """Atomically count one attempt; never dispatch on a duplicate ID.

        If commit acknowledgement is lost, the same process may confirm its
        reservation by ID: the caller has not yet dispatched the provider. A
        later/repeated call with that ID receives `duplicate` and must not run.
        """
        accounting_day = date.fromisoformat(day)
        commit_may_have_succeeded = False
        result = None
        try:
            with self._connect() as connection:
                existing = connection.execute(
                    "SELECT accounting_day, admitted_attempt_number "
                    "FROM knowledge_engine.allowance_reservations "
                    "WHERE workspace_key = %s AND reservation_id = %s",
                    (self._workspace_key, reservation_id),
                ).fetchone()
                if existing is not None:
                    return {"admitted": True, "duplicate": True, "dispatch_allowed": False,
                            "day": existing[0].isoformat(), "attempt_number": existing[1]}

                row = connection.execute(
                    "SELECT accounting_day, admitted_attempts, paused, pause_reason, "
                    "last_attempt_at, last_reservation_id, migration_version "
                    "FROM knowledge_engine.allowance_state WHERE workspace_key = %s FOR UPDATE",
                    (self._workspace_key,),
                ).fetchone()
                state = self._as_state(row)
                # A concurrent call with the same reservation ID may have
                # committed while this transaction waited for the state row.
                existing = connection.execute(
                    "SELECT accounting_day, admitted_attempt_number FROM "
                    "knowledge_engine.allowance_reservations "
                    "WHERE workspace_key = %s AND reservation_id = %s",
                    (self._workspace_key, reservation_id),
                ).fetchone()
                if existing is not None:
                    return {"admitted": True, "duplicate": True, "dispatch_allowed": False,
                            "day": existing[0].isoformat(), "attempt_number": existing[1]}
                if state["paused"]:
                    return {"admitted": False, "reason": state["reason"] or "paused"}
                current_calls = state["calls"] if state["day"] == day else 0
                if current_calls >= limit:
                    return {"admitted": False, "reason": "daily_limit"}
                attempt_number = current_calls + 1
                connection.execute(
                    "UPDATE knowledge_engine.allowance_state SET accounting_day = %s, "
                    "admitted_attempts = %s, last_attempt_at = %s, last_reservation_id = %s, "
                    "updated_at = now() WHERE workspace_key = %s",
                    (accounting_day, attempt_number, attempted_at, reservation_id, self._workspace_key),
                )
                connection.execute(
                    "INSERT INTO knowledge_engine.allowance_reservations "
                    "(workspace_key, reservation_id, accounting_day, admitted_attempt_number, admitted_at) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (self._workspace_key, reservation_id, accounting_day, attempt_number, attempted_at),
                )
                result = {"admitted": True, "duplicate": False, "dispatch_allowed": True,
                          "day": day, "attempt_number": attempt_number}
                commit_may_have_succeeded = True
            return result
        except Exception:
            if commit_may_have_succeeded:
                try:
                    existing = self._lookup_reservation(reservation_id)
                    if existing is not None:
                        return {"admitted": True, "duplicate": False, "dispatch_allowed": True,
                                "acknowledgement_recovered": True,
                                "day": existing[0].isoformat(), "attempt_number": existing[1]}
                except Exception:
                    pass
            raise AllowancePersistenceError("Provider attempt reservation could not be confirmed.") from None

    def set_paused(self, paused: bool, reason: str | None = None) -> dict[str, Any]:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "UPDATE knowledge_engine.allowance_state SET paused = %s, pause_reason = %s, "
                    "updated_at = now() WHERE workspace_key = %s AND migration_version = %s "
                    "RETURNING accounting_day, admitted_attempts, paused, pause_reason, "
                    "last_attempt_at, last_reservation_id, migration_version",
                    (paused, reason if paused else None, self._workspace_key, ALLOWANCE_MIGRATION_VERSION),
                ).fetchone()
                return self._as_state(row)
        except AllowancePersistenceError:
            raise
        except Exception:
            raise AllowancePersistenceError("Hosted allowance state could not be updated.") from None


def legacy_usage_from_state(state: dict[str, Any]) -> dict[str, Any]:
    """Portable copy-back shape for a controlled rollback to snapshot authority."""
    return {
        "day": state.get("day"),
        "calls": state.get("calls", 0),
        "paused": state.get("paused", False),
        "reason": state.get("reason"),
        "last_attempt_at": state.get("last_attempt_at"),
        "last_reservation_id": state.get("last_reservation_id"),
    }
