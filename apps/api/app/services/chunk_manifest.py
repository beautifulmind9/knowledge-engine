"""Versioned, content-free chunk identity metadata for read-path calculations."""

CHUNK_MANIFEST_VERSION = 1


def manifest_from_chunks(source_id: str, chunks):
    ids = []
    for chunk in chunks:
        if not isinstance(chunk, dict) or chunk.get("source_id") != source_id:
            raise ValueError("Chunk source identity is invalid.")
        chunk_id = chunk.get("id")
        if not isinstance(chunk_id, str) or not chunk_id.startswith(f"chunk_{source_id}_"):
            raise ValueError("Chunk identity is invalid.")
        ids.append(chunk_id)
    if len(ids) != len(set(ids)):
        raise ValueError("Chunk identities must be unique.")
    return {"version": CHUNK_MANIFEST_VERSION, "total_parts": len(ids), "chunk_ids": ids}


def valid_manifest(source_id: str, manifest):
    if (not isinstance(manifest, dict) or isinstance(manifest.get("version"), bool)
            or not isinstance(manifest.get("version"), int)
            or manifest.get("version") != CHUNK_MANIFEST_VERSION):
        return False
    ids = manifest.get("chunk_ids")
    total = manifest.get("total_parts")
    if (not isinstance(ids, list) or isinstance(total, bool) or not isinstance(total, int)
            or total != len(ids) or any(not isinstance(value, str) or not value.startswith(f"chunk_{source_id}_") for value in ids)
            or len(ids) != len(set(ids))):
        return False
    return True
