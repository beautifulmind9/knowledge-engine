from typing import Any, Protocol
from pathlib import Path


class StateStore(Protocol):
    """Load and save a complete snapshot without interpreting domain records."""

    def load(self) -> dict[str, Any] | None: ...

    def save(self, state: dict[str, Any]) -> None: ...


class ArtifactStore(Protocol):
    """Filesystem operations needed by extracted-text and chunk artifacts."""

    def create_directory(self, path: Path) -> None: ...

    def write_text(self, path: Path, text: str) -> None: ...

    def read_text(self, path: Path) -> str: ...

    def exists(self, path: Path) -> bool: ...
