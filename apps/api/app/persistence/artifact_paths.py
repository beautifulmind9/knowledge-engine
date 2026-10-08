"""Backend-neutral containment and backup metadata at the application boundary."""
from pathlib import Path
from zipfile import ZipInfo
from uuid import uuid4

from app.persistence.contracts import ArtifactStore
from app.persistence.local_artifacts import LocalArtifactStore


def contained_locator(store: ArtifactStore, path: Path, root: Path) -> Path:
    if isinstance(store, LocalArtifactStore):
        path = store.resolve(path)
        if not path.is_relative_to(root):
            raise ValueError("Artifact locator is outside private storage.")
        return path
    # Hosted locators are lexical, with no filesystem resolve/stat/symlink IO.
    from app.persistence.supabase_artifacts import SupabaseArtifactStore
    if isinstance(store, SupabaseArtifactStore):
        return root / store.relative_locator(path)
    raise TypeError("Unsupported artifact locator backend.")


def archive_entry(store: ArtifactStore, path: Path, name: str) -> ZipInfo:
    if isinstance(store, LocalArtifactStore):
        return store.zip_info(path, name)
    return ZipInfo(name)  # Portable deterministic metadata, no invented inode data.


def upload_locator(store: ArtifactStore, stable_path: Path) -> Path:
    """Keep legacy local names; remote publication must not overwrite live bytes."""
    if isinstance(store, LocalArtifactStore):
        return stable_path
    return stable_path.with_name(f"{stable_path.stem}-{uuid4().hex}{stable_path.suffix}")


def cleanup_unpublished_or_superseded(store: ArtifactStore, paths: list[Path]) -> None:
    """Best effort only, after containment validation; never log IO diagnostics.

    Failures may leave private orphan objects. Publication must not be rolled back
    or reported as failed merely because an unreferenced artifact cannot be removed.
    """
    for path in paths:
        try:
            store.remove(path)
        except (OSError, RuntimeError):
            pass
