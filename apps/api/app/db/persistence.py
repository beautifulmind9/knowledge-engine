"""Single-owner SQLite snapshots. Run one server process; requests are serialized.

The first launch migrates existing state.json without changing the source file.
Corruption fails loudly; it must never silently replace the owner's data.
"""
import json
import os
import sqlite3
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = Path(os.environ.get("KNOWLEDGE_ENGINE_STORAGE", API_ROOT / "storage")).expanduser().resolve()
STATE_PATH = STORAGE_ROOT / "state.json"
DB_PATH = STORAGE_ROOT / "knowledge.sqlite3"


def _connect():
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
    return conn


def load_state():
    with _connect() as conn:
        row = conn.execute("SELECT payload FROM state WHERE id=1").fetchone()
        if row:
            return json.loads(row[0])
        if STATE_PATH.exists():
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            for key in ("libraries", "sources", "extraction_jobs", "knowledge_assets"):
                if not isinstance(state.get(key), list):
                    raise RuntimeError(f"Invalid legacy state: {key} must be a list. Original file preserved.")
            for source in state["sources"]:
                for key in ("file_path", "extracted_text_path", "chunks_path"):
                    value = source.get(key)
                    if value and not Path(value).is_absolute():
                        path = Path(value)
                        source[key] = str(STORAGE_ROOT.joinpath(*path.parts[1:])) if path.parts[0] == "storage" else str(API_ROOT / path)
            conn.execute("INSERT INTO state VALUES (1, ?)", (json.dumps(state),))
            return state
    return None


def save_state(libraries, sources, extraction_jobs, knowledge_assets):
    from app.db.mock_data import outputs, usage
    state = dict(libraries=libraries, sources=sources, extraction_jobs=extraction_jobs,
                 knowledge_assets=knowledge_assets, outputs=outputs, usage=usage, schema_version=2)
    with _connect() as conn:
        conn.execute("INSERT INTO state VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                     (json.dumps(state, ensure_ascii=False),))
