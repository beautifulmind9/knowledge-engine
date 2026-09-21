"""Characterize local text/chunk IO against the original pathlib operations."""
import json
from pathlib import Path

import pytest

from app.db.persistence import STORAGE_ROOT
from app.persistence.contracts import ArtifactStore
from app.persistence.local_artifacts import LocalArtifactStore
from app.services import text_chunking, text_extraction


@pytest.fixture
def artifact_folders(tmp_path, monkeypatch):
    monkeypatch.setattr(text_extraction, "TEXT_OUTPUT_FOLDER", tmp_path / "extracted_text")
    monkeypatch.setattr(text_chunking, "CHUNK_OUTPUT_FOLDER", tmp_path / "chunks")
    return tmp_path


def test_default_artifact_folders():
    assert text_extraction.TEXT_OUTPUT_FOLDER == STORAGE_ROOT / "extracted_text"
    assert text_chunking.CHUNK_OUTPUT_FOLDER == STORAGE_ROOT / "chunks"


@pytest.mark.parametrize("text", ["", "Café 学習 🌱\n", " first\r\nsecond\rthird\n\n\t", "a\x00b"])
def test_extracted_text_bytes_contents_and_path(artifact_folders, text):
    expected = artifact_folders / "reference.txt"
    expected.write_text(text, encoding="utf-8")
    result = text_extraction.save_extracted_text("source_one", text)
    assert result == str(artifact_folders / "extracted_text" / "source_one.txt")
    assert Path(result).read_bytes() == expected.read_bytes()
    store: ArtifactStore = LocalArtifactStore()
    # Preserve pathlib's universal-newline read semantics, including CRLF input.
    assert store.read_text(Path(result)) == expected.read_text(encoding="utf-8")
    assert text_extraction.extract_text_from_file(result, ".txt") == expected.read_text(encoding="utf-8")
    assert store.exists(Path(result))


def test_repeated_extracted_text_save_overwrites(artifact_folders):
    path = text_extraction.save_extracted_text("source_one", "long original content")
    assert text_extraction.save_extracted_text("source_one", "é") == path
    assert Path(path).read_bytes() == "é".encode("utf-8")


def test_chunk_structure_order_ids_serialization_and_repeated_io(artifact_folders):
    chunks = text_chunking.chunk_text("source_one", "# Café\none two three four five six", chunk_size=4, overlap=1)
    assert [chunk["id"] for chunk in chunks] == ["chunk_source_one_001", "chunk_source_one_002", "chunk_source_one_003"]
    expected = json.dumps(chunks, indent=2, ensure_ascii=False).encode("utf-8")
    path = text_chunking.save_chunks("source_one", chunks)
    assert path == str(artifact_folders / "chunks" / "source_one.json")
    assert Path(path).read_bytes() == expected
    for _ in range(3):
        loaded = text_chunking.load_chunks(path)
        assert loaded == chunks
        assert [list(chunk) for chunk in loaded] == [list(chunk) for chunk in chunks]
        assert text_chunking.save_chunks("source_one", loaded) == path
        assert Path(path).read_bytes() == expected
    loaded[0]["text"] = "changed in memory"
    assert text_chunking.load_chunks(path) == chunks
    assert text_chunking.save_chunks("source_one", []) == path
    assert Path(path).read_bytes() == b"[]"
    assert text_chunking.load_chunks(path) == []


def test_missing_chunks_preserves_error_and_does_not_create_directory(artifact_folders):
    path = artifact_folders / "chunks" / "missing.json"
    with pytest.raises(ValueError) as error:
        text_chunking.load_chunks(str(path))
    assert str(error.value) == "Chunks file not found on disk. Restore the source data before continuing."
    assert not path.parent.exists()


@pytest.mark.parametrize("content", [b"{bad JSON", b"", b"[\xff]"])
def test_malformed_chunks_preserves_read_and_json_errors(artifact_folders, content):
    path = artifact_folders / "malformed.json"
    path.write_bytes(content)
    with pytest.raises((json.JSONDecodeError, UnicodeDecodeError)) as original:
        json.loads(path.read_text(encoding="utf-8"))
    with pytest.raises(type(original.value)) as delegated:
        text_chunking.load_chunks(str(path))
    assert str(delegated.value) == str(original.value)
    assert path.read_bytes() == content


@pytest.mark.parametrize("value", [{"unexpected": [1, None]}, None])
def test_chunks_do_not_add_shape_validation(artifact_folders, value):
    path = text_chunking.save_chunks("source_one", value)
    assert text_chunking.load_chunks(path) == value


def test_failed_chunk_serialization_preserves_directory_and_prior_file(artifact_folders):
    with pytest.raises(TypeError):
        text_chunking.save_chunks("source_one", [object()])
    folder = artifact_folders / "chunks"
    assert folder.is_dir()
    assert not (folder / "source_one.json").exists()
    path = text_chunking.save_chunks("source_one", [{"text": "original"}])
    before = Path(path).read_bytes()
    with pytest.raises(TypeError):
        text_chunking.save_chunks("source_one", [object()])
    assert Path(path).read_bytes() == before


def test_directory_chunks_path_still_raises_is_a_directory(artifact_folders):
    with pytest.raises(IsADirectoryError):
        text_chunking.load_chunks(str(artifact_folders))
