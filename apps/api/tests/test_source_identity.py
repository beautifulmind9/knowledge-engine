from app.routers import sources as source_router
from app.services import source_identity


def create_text_source(client, filename, body, *, title_origin="filename", author_origin="unconfirmed"):
    library = client.post("/libraries", json={"name": "Reading"}).json()
    record = client.post("/sources", json={
        "library_id": library["id"], "title": "Download 1837", "author": None,
        "title_origin": title_origin, "author_origin": author_origin,
    }).json()
    uploaded = client.post(f"/sources/{record['id']}/upload", files={"file": (filename, body, "text/plain")})
    assert uploaded.status_code == 200, uploaded.text
    return record


def test_material_title_and_explicit_byline_replace_meaningless_filename(client):
    record = create_text_source(client, "download_1837.txt", b"Triggers\nBy Marshall Goldsmith\nA practical book.")
    assert client.post(f"/sources/{record['id']}/process").status_code == 200
    result = client.get(f"/sources/{record['id']}").json()
    assert (result["title"], result["author"]) == ("Triggers", "Marshall Goldsmith")
    assert (result["title_origin"], result["author_origin"]) == ("material_text", "material_text")


def test_title_page_name_is_persisted_as_uncertain_not_asserted_authorship(client):
    record = create_text_source(client, "download_1837.txt", b"Triggers\nMarshall Goldsmith\nA practical guide")
    assert client.post(f"/sources/{record['id']}/process").status_code == 200
    result = client.get(f"/sources/{record['id']}").json()
    assert result["title"] == "Triggers" and result["author"] == "Marshall Goldsmith"
    assert result["title_origin"] == "material_text"
    assert result["author_origin"] == "material_text_suggested"


def test_clear_title_page_wins_conflicting_filename_and_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(source_identity, "embedded_identity", lambda *_: ("Book package title", "Packaged Author"))
    result = source_identity.resolve_identity(tmp_path / "unused.txt", ".txt", "# Actual Title Page\nBy Visible Author\nBody text")
    assert result == {
        "title": "Actual Title Page", "title_origin": "material_text",
        "author": "Visible Author", "author_origin": "material_text",
        "author_review_required": False,
        "title_conflict": True,
    }


def test_embedded_metadata_is_supported_and_explicit_visible_evidence_takes_precedence(monkeypatch, tmp_path):
    monkeypatch.setattr(source_identity, "embedded_identity", lambda *_: ("Triggers", "Marshall Goldsmith"))
    agrees = source_identity.resolve_identity(tmp_path / "book.pdf", ".pdf", "# Triggers\nBy Marshall Goldsmith\nText")
    assert agrees["title"] == "Triggers" and agrees["author"] == "Marshall Goldsmith"
    assert agrees["title_conflict"] is False
    metadata_only = source_identity.resolve_identity(tmp_path / "book.pdf", ".pdf", "A paragraph with several people named Alex and Morgan.")
    assert metadata_only["title_origin"] == "document_metadata"
    assert metadata_only["author_origin"] == "document_metadata"


def test_docx_embedded_title_and_author_are_read_locally(tmp_path):
    from docx import Document
    document = Document()
    document.core_properties.title = "Embedded report title"
    document.core_properties.author = "Report author"
    path = tmp_path / "report.docx"
    document.save(path)
    assert source_identity.embedded_identity(path, ".docx") == ("Embedded report title", "Report author")


def test_missing_or_ambiguous_authorship_is_not_inferred(monkeypatch, tmp_path):
    monkeypatch.setattr(source_identity, "embedded_identity", lambda *_: ("", ""))
    missing = source_identity.resolve_identity(tmp_path / "notes.txt", ".txt", "# Workshop Notes\nAlex, Morgan, and Casey attended.")
    assert missing["title"] == "Workshop Notes"
    assert missing["author"] == "" and missing["author_origin"] is None


def test_plain_title_page_name_is_only_a_reviewable_author_suggestion(monkeypatch, tmp_path):
    monkeypatch.setattr(source_identity, "embedded_identity", lambda *_: ("", ""))
    candidate = source_identity.resolve_identity(tmp_path / "download.pdf", ".pdf", "Triggers\nMarshall Goldsmith\nA practical guide")
    assert candidate["title"] == "Triggers"
    assert candidate["author"] == "Marshall Goldsmith"
    assert candidate["author_origin"] == "material_text_suggested"
    assert candidate["author_review_required"] is True
    ambiguous = source_identity.resolve_identity(tmp_path / "download.pdf", ".pdf", "Triggers\nMarshall Goldsmith\nJane Example\nA practical guide")
    assert ambiguous["author"] == "" and ambiguous["author_origin"] is None


def test_user_confirmed_title_and_author_survive_later_read(client):
    library = client.post("/libraries", json={"name": "Reading"}).json()
    record = client.post("/sources", json={"library_id": library["id"], "title": "My title", "author": "My author",
        "title_origin": "user_confirmed", "author_origin": "user_confirmed"}).json()
    client.post(f"/sources/{record['id']}/upload", files={"file": ("download.txt", b"# Different title\nBy Different author", "text/plain")})
    assert client.post(f"/sources/{record['id']}/process").status_code == 200
    result = client.get(f"/sources/{record['id']}").json()
    assert result["title"] == "My title" and result["author"] == "My author"
    assert result["title_origin"] == result["author_origin"] == "user_confirmed"


def test_user_title_is_kept_while_unknown_author_can_be_filled(client):
    record = create_text_source(client, "download.txt", b"# Document title\nBy Material author", title_origin="user_confirmed")
    current = next(item for item in source_router.sources if item["id"] == record["id"])
    current["title"] = "My edited title"
    assert client.post(f"/sources/{record['id']}/process").status_code == 200
    result = client.get(f"/sources/{record['id']}").json()
    assert result["title"] == "My edited title" and result["author"] == "Material author"


def test_user_author_is_kept_while_filename_title_can_be_resolved(client):
    record = create_text_source(client, "download.txt", b"# Document title\nBy Document author", author_origin="user_confirmed")
    current = next(item for item in source_router.sources if item["id"] == record["id"])
    current["author"] = "My edited author"
    assert client.post(f"/sources/{record['id']}/process").status_code == 200
    result = client.get(f"/sources/{record['id']}").json()
    assert result["title"] == "Document title" and result["author"] == "My edited author"


def test_identity_edit_is_persisted_as_user_confirmed_and_blocks_resolution(client):
    record = create_text_source(client, "download.txt", b"# Found title\nBy Found author")
    response = client.put(f"/sources/{record['id']}/identity", json={"title": "Chosen title", "author": "Chosen author"})
    assert response.status_code == 200
    assert client.post(f"/sources/{record['id']}/process").status_code == 200
    result = client.get(f"/sources/{record['id']}").json()
    assert (result["title"], result["author"]) == ("Chosen title", "Chosen author")
    assert result["title_origin"] == result["author_origin"] == "user_confirmed"


def test_explicitly_clearing_author_is_preserved(client):
    record = create_text_source(client, "download.txt", b"# Document title\nBy Material author")
    response = client.put(f"/sources/{record['id']}/identity", json={"title": "Chosen title", "author": ""})
    assert response.status_code == 200 and response.json()["author_origin"] == "user_confirmed"
    assert client.post(f"/sources/{record['id']}/process").status_code == 200
    result = client.get(f"/sources/{record['id']}").json()
    assert result["author"] == "" and result["author_origin"] == "user_confirmed"


def test_read_failure_retains_provisional_filename_identity(client, monkeypatch):
    record = create_text_source(client, "random-file-name.txt", b"content")
    monkeypatch.setattr(source_router, "extract_text_from_file", lambda **_: (_ for _ in ()).throw(ValueError("synthetic read failure")))
    response = client.post(f"/sources/{record['id']}/process")
    assert response.status_code == 400
    result = client.get(f"/sources/{record['id']}").json()
    assert result["title"] == "Download 1837"
    assert result["title_origin"] == "filename"
    assert result["author"] == "" and result["author_origin"] == "unconfirmed"


def test_legacy_identity_without_provenance_is_preserved(client):
    record = create_text_source(client, "download.txt", b"# Different title\nBy New author")
    current = next(item for item in source_router.sources if item["id"] == record["id"])
    current.pop("title_origin")
    current.pop("author_origin")
    assert client.post(f"/sources/{record['id']}/process").status_code == 200
    result = client.get(f"/sources/{record['id']}").json()
    assert result["title"] == "Download 1837" and result["author"] == ""
