from contextlib import AbstractContextManager
from typing import Any, BinaryIO, Literal, Protocol
from pathlib import Path


class StateStore(Protocol):
    """Load and save a complete snapshot without interpreting domain records."""

    def load(self) -> dict[str, Any] | None: ...

    def save(self, state: dict[str, Any]) -> None: ...


class ArtifactStore(Protocol):
    """Artifact IO; the active local implementation retains legacy Path locators."""

    def create_directory(self, path: Path) -> None: ...

    def write_text(self, path: Path, text: str) -> None: ...

    def read_text(self, path: Path, *, errors: str = "strict") -> str: ...

    def exists(self, path: Path) -> bool:
        """Whether the locator exists (including containers); storage failures raise."""
        ...

    def status(self, path: Path) -> Literal["artifact", "missing", "other"]:
        """Distinguish a byte artifact, absence, and a non-artifact/container.

        Only genuine absence is missing; permission and storage failures raise.
        """
        ...

    def open_binary_read(self, path: Path) -> AbstractContextManager[BinaryIO]: ...

    def open_binary_write(self, path: Path) -> AbstractContextManager[BinaryIO]: ...

    def replace(self, temporary: Path, destination: Path) -> None: ...

    def remove(self, path: Path) -> None: ...

    def materialize(self, path: Path) -> AbstractContextManager[Path]:
        """Yield a local path guaranteed usable only while the context is active."""
        ...
