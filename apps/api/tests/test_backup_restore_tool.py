import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from verify_hosted_backup import load_and_verify, restore_local


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def backup_package(tmp_path):
    package = tmp_path / "backup"
    (package / "objects").mkdir(parents=True)
    artifacts = []
    paths = ("uploads/source.pdf", "text/source.txt", "chunks/source.json")
    for index, locator in enumerate(paths):
        path = package / "objects" / locator
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("artifact-" + str(index)).encode())
        artifacts.append({"locator": locator, "object_key": "workspace-a/" + locator,
                          "file": str(path.relative_to(package)), "size": path.stat().st_size,
                          "sha256": digest(path)})
    snapshot = {"schema_version": 2, "libraries": [], "sources": [{
        "id": "source-a", "file_path": paths[0], "extracted_text_path": paths[1],
        "chunks_path": paths[2]}], "extraction_jobs": [], "knowledge_assets": [],
        "outputs": [], "usage": {"calls": 1}}
    snapshot_path = package / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot))
    dump = package / "database.dump"
    dump.write_bytes(b"synthetic pg_dump fixture")
    manifest = {"format_version": 1, "authority": "snapshot",
                "snapshot": {"file": "snapshot.json", "sha256": digest(snapshot_path)},
                "database_dump": {"file": "database.dump", "sha256": digest(dump)},
                "allowance_ledger": {"included_in_database_dump": True}, "artifacts": artifacts}
    (package / "manifest.json").write_text(json.dumps(manifest))
    return package


def test_backup_verification_and_isolated_local_restore(tmp_path):
    package = backup_package(tmp_path)
    manifest, snapshot = load_and_verify(package)
    assert len(manifest["artifacts"]) == 3 and "partition" not in snapshot

    destination = tmp_path / "isolated"
    assert restore_local(package, destination) == {"sources": 1, "artifacts": 3}
    restored = json.loads((destination / "storage/state.json").read_text())
    assert restored["sources"][0]["file_path"] == "storage/uploads/source.pdf"
    assert (destination / restored["sources"][0]["file_path"]).read_bytes() == b"artifact-0"
    assert (destination / "storage/knowledge.sqlite3").is_file()


def test_backup_verification_rejects_missing_artifact_and_nonempty_restore(tmp_path):
    package = backup_package(tmp_path)
    (package / "objects/uploads/source.pdf").unlink()
    try:
        load_and_verify(package)
    except RuntimeError as error:
        assert "missing or has the wrong" in str(error)
    else:
        raise AssertionError("missing artifact accepted")

    package = backup_package(tmp_path / "second")
    destination = tmp_path / "occupied"
    destination.mkdir()
    (destination / "keep").write_text("existing")
    try:
        restore_local(package, destination)
    except RuntimeError as error:
        assert "new or empty" in str(error)
    else:
        raise AssertionError("nonempty restore destination accepted")


def test_backup_verification_rejects_paths_outside_package(tmp_path):
    package = backup_package(tmp_path)
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"][0]["file"] = "../private"
    manifest_path.write_text(json.dumps(manifest))
    try:
        load_and_verify(package)
    except RuntimeError as error:
        assert "outside the package" in str(error)
    else:
        raise AssertionError("out-of-package artifact accepted")
