"""Local one-row SQLite snapshots with the original legacy JSON migration."""
import json
import sqlite3
from pathlib import Path
from typing import Any


class SQLiteStateStore:
    def __init__(self, storage_root: Path, state_path: Path, db_path: Path, api_root: Path):
        self.storage_root = storage_root
        self.state_path = state_path
        self.db_path = db_path
        self.api_root = api_root

    def _connect(self):
        self.storage_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
        return conn

    def load(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM state WHERE id=1").fetchone()
            if row:
                return json.loads(row[0])
            if self.state_path.exists():
                state = json.loads(self.state_path.read_text(encoding="utf-8"))
                for key in ("libraries", "sources", "extraction_jobs", "knowledge_assets"):
                    if not isinstance(state.get(key), list):
                        raise RuntimeError(f"Invalid legacy state: {key} must be a list. Original file preserved.")
                for source in state["sources"]:
                    for key in ("file_path", "extracted_text_path", "chunks_path"):
                        value = source.get(key)
                        if value and not Path(value).is_absolute():
                            path = Path(value)
                            source[key] = str(self.storage_root.joinpath(*path.parts[1:])) if path.parts[0] == "storage" else str(self.api_root / path)
                conn.execute("INSERT INTO state VALUES (1, ?)", (json.dumps(state),))
                return state
        return None

    def save(self, state: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO state VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                         (json.dumps(state, ensure_ascii=False),))
