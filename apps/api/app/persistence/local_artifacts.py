"""Local artifact IO, containment paths, and legacy ZIP metadata."""
from contextlib import contextmanager
from pathlib import Path
from os import stat_result
from stat import S_ISREG
from typing import Literal
from zipfile import ZipInfo


class LocalArtifactStore:
    def create_directory(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def write_text(self, path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8")

    def read_text(self, path: Path, *, errors: str = "strict") -> str:
        return path.read_text(encoding="utf-8", errors=errors)

    def exists(self, path: Path) -> bool:
        return self.status(path) != "missing"

    def status(self, path: Path) -> Literal["artifact", "missing", "other"]:
        try:
            metadata = self.stat(path)
        except (FileNotFoundError, NotADirectoryError):
            return "missing"
        return "artifact" if S_ISREG(metadata.st_mode) else "other"

    def resolve(self, path: Path) -> Path:
        return path.resolve()

    def stat(self, path: Path) -> stat_result:
        return path.stat()

    def zip_info(self, path: Path, archive_name: str) -> ZipInfo:
        """Local-only metadata, matching ZipFile.write (including directory races)."""
        entry = ZipInfo.from_file(path, archive_name)
        if entry.is_dir():
            entry.file_size = 0
            entry.compress_size = 0
            entry.CRC = 0
        return entry

    def open_binary_read(self, path: Path):
        return path.open("rb")

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
