"""Durable storage for the single-owner research workspace."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def storage_root():
    return Path(os.environ.get("KNOWLEDGE_ENGINE_STORAGE", Path(__file__).resolve().parents[2] / "storage"))


def create_id(prefix):
    return f"{prefix}_{uuid4().hex}"


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    root = storage_root()
    root.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(root / "workspace.sqlite3", timeout=30) as db:
        db.execute("CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(kind,id))")
        yield db


def all_records(kind):
    with connect() as db:
        return [json.loads(r[0]) for r in db.execute("SELECT body FROM records WHERE kind=? ORDER BY rowid", (kind,))]


def get(kind, record_id):
    with connect() as db:
        row = db.execute("SELECT body FROM records WHERE kind=? AND id=?", (kind, record_id)).fetchone()
        return json.loads(row[0]) if row else None


def save(kind, record):
    save_many(kind, [record])
    return record


def save_many(kind, records):
    with connect() as db:
        db.executemany("INSERT INTO records VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body", [(kind, r["id"], json.dumps(r, ensure_ascii=False)) for r in records])


def delete(kind, record_id):
    with connect() as db:
        db.execute("DELETE FROM records WHERE kind=? AND id=?", (kind, record_id))
