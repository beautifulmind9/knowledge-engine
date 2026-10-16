"""Validated chunk content held only for one interpretation request."""
from dataclasses import dataclass
from pathlib import Path

from app.persistence.factory import get_artifact_store
from app.services.chunk_manifest import valid_manifest
from app.services.text_chunking import load_chunks


@dataclass(frozen=True)
class RequestChunkContext:
    source_id: str
    artifact_path: Path
    chunks: tuple[dict, ...]
    manifest_identity: tuple[str, ...] | None

    def ensure_identity(self, source_id: str, artifact_path: str | Path, manifest=None):
        path = Path(artifact_path)
        if source_id != self.source_id or path != self.artifact_path:
            raise ValueError("Chunk content does not belong to this source request.")
        recognized = valid_manifest(source_id, manifest)
        current_identity = tuple(manifest["chunk_ids"]) if recognized else None
        if current_identity != self.manifest_identity:
            raise ValueError("Chunk manifest changed during this source request.")

    def ensure_current_artifact(self, source_id: str, artifact_path: str | Path, manifest=None):
        path = Path(artifact_path)
        self.ensure_identity(source_id, path, manifest)
        if get_artifact_store().status(path) != "artifact":
            raise ValueError("Chunks file not found on disk. Restore the source data before continuing.")

    def get(self, source_id: str, artifact_path: str | Path, chunk_id: str, manifest=None):
        self.ensure_current_artifact(source_id, artifact_path, manifest)
        return next((chunk for chunk in self.chunks if chunk["id"] == chunk_id), None)


def load_request_chunk_context(source: dict) -> RequestChunkContext:
    """Read once, then validate chunk ownership and any recognized manifest."""
    source_id = source.get("id")
    artifact_path = source.get("chunks_path")
    if not artifact_path:
        raise ValueError("This source has not been chunked yet.")

    chunks = load_chunks(artifact_path)
    if not isinstance(chunks, list):
        raise ValueError("Invalid processing parts.")

    ids = []
    for chunk in chunks:
        if (not isinstance(chunk, dict) or not isinstance(chunk.get("id"), str)
                or not chunk["id"] or chunk.get("source_id") != source_id):
            raise ValueError("Chunk content does not match its source.")
        ids.append(chunk["id"])
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate processing parts.")

    manifest = source.get("chunk_manifest")
    manifest_identity = None
    if valid_manifest(source_id, manifest):
        manifest_identity = tuple(manifest["chunk_ids"])
        if tuple(ids) != manifest_identity or manifest["total_parts"] != len(chunks):
            raise ValueError("Chunk content does not match its manifest.")

    return RequestChunkContext(
        source_id=source_id,
        artifact_path=Path(artifact_path),
        chunks=tuple(chunks),
        manifest_identity=manifest_identity,
    )
