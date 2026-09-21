"""Local artifact IO with the existing pathlib behavior."""
from contextlib import contextmanager
from pathlib import Path


class LocalArtifactStore:
    def create_directory(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def write_text(self, path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8")

    def read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def exists(self, path: Path) -> bool:
        return path.exists()

    def open_binary_write(self, path: Path):
        return path.open("wb")

    def replace(self, temporary: Path, destination: Path) -> None:
        temporary.replace(destination)

    def remove(self, path: Path) -> None:
        path.unlink(missing_ok=True)

    @contextmanager
    def materialize(self, path: Path):
        """Yield the original path; local artifacts persist after context exit."""
        yield path
