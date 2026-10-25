from contextlib import AbstractContextManager
from typing import Any, BinaryIO, Literal, Mapping, Protocol
from pathlib import Path


class StateStore(Protocol):
    """Load and save a complete snapshot without interpreting domain records."""

    def load(self) -> dict[str, Any] | None: ...

    def save(self, state: dict[str, Any]) -> None: ...


class ArtifactStore(Protocol):
    """Artifact IO using logical Path locators; materialization provides filesystem paths."""

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

    def status_many(self, paths: list[Path]) -> Mapping[Path, Literal["artifact", "missing", "other"]]:
        """Check exact locators in one request scope; failures are never absence."""
        ...

    def size_many(self, paths: list[Path]) -> Mapping[Path, int | None]:
        """Return byte sizes for artifacts and None for absent/non-artifact locators.

        Storage failures and malformed or unavailable size metadata must raise.
        """
        ...

    def open_binary_read(self, path: Path) -> AbstractContextManager[BinaryIO]: ...

    def open_binary_write(self, path: Path) -> AbstractContextManager[BinaryIO]: ...

    def replace(self, temporary: Path, destination: Path) -> None: ...

    def remove(self, path: Path) -> None: ...

    def materialize(self, path: Path) -> AbstractContextManager[Path]:
        """Yield a local path guaranteed usable only while the context is active."""
        ...


class PartitionStore(Protocol):
    """Dormant hosted narrow records; reads do not imply snapshot authority.

    apply() groups mutations and an operation receipt in one transaction. A
    borrowed connection must already be in a transaction owned by the caller.
    Replayed receipts must never authorize a second provider dispatch.
    """

    def transaction(self, connection=None) -> AbstractContextManager: ...

    def apply(self, operation_id: str, request: dict, mutate, *, connection=None): ...

    def read_operation(self, operation_id: str) -> dict | None: ...

    def read_source(self, source_id: str) -> dict | None: ...

    def read_job(self, job_id: str) -> dict | None: ...

    def query_jobs(self, source_id: str, generation: int, *, chunk_id: str | None = None) -> list[dict]: ...

    def query_assets(self, source_id: str, generation: int, *,
                     chunk_id: str | None = None, active: bool | None = None) -> list[dict]: ...

    def assets_by_ids(self, asset_ids: list[str]) -> list[dict]: ...

    def read_migration(self) -> dict | None: ...
