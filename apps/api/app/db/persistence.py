import json
from pathlib import Path


STATE_PATH = Path("storage/state.json")


def load_state():
    """Load development API state from disk if it exists."""
    if not STATE_PATH.exists():
        return None

    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_state(libraries, sources, extraction_jobs, knowledge_assets):
    """Persist development API state so server reloads do not erase it."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    state = {
        "libraries": libraries,
        "sources": sources,
        "extraction_jobs": extraction_jobs,
        "knowledge_assets": knowledge_assets,
    }

    temporary_path = STATE_PATH.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary_path.replace(STATE_PATH)
