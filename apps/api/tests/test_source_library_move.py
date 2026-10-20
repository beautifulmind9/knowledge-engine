"""Moving a material changes library membership without touching its content."""
import pytest
from app.routers import sources as source_router


def test_move_preserves_uploaded_file_chunks_and_prepared_knowledge(client, source, knowledge):
    original, _ = source
    source_id = original["id"]
    destination = client.post("/libraries", json={"name": "New home"}).json()
    before = client.get(f"/sources/{source_id}").json()
    original_file = client.get(f"/sources/{source_id}/file")
    assert original_file.status_code == 200
    before_chunks = client.get(f"/sources/{source_id}/chunks").json()
    before_units = client.get(f"/sources/{source_id}/knowledge-units").json()
    before_jobs = [dict(job) for job in source_router.extraction_jobs]
    before_assets = [dict(asset) for asset in source_router.knowledge_assets]

    moved = client.put(f"/sources/{source_id}/library", json={"library_id": destination["id"]})
    assert moved.status_code == 200, moved.text
    assert moved.json() == {"id": source_id, "library_id": destination["id"], "changed": True}
    after = client.get(f"/sources/{source_id}").json()
    assert {k: v for k, v in after.items() if k != "library_id"} == {k: v for k, v in before.items() if k != "library_id"}
    assert after["library_id"] == destination["id"]
    assert client.get(f"/sources/{source_id}/file").content == original_file.content
    assert client.get(f"/sources/{source_id}/chunks").json() == before_chunks
    assert client.get(f"/sources/{source_id}/knowledge-units").json() == before_units
    assert source_router.extraction_jobs == before_jobs
    assert source_router.knowledge_assets == before_assets
    assert source_id not in [s["id"] for s in client.get("/sources", params={"library_id": original["library_id"]}).json()["items"]]
    assert source_id in [s["id"] for s in client.get("/sources", params={"library_id": destination["id"]}).json()["items"]]


def test_move_rejects_unknown_source_destination_and_blank_payload(client):
    a = client.post("/libraries", json={"name": "Original"}).json()
    b = client.post("/libraries", json={"name": "Destination"}).json()
    source = client.post("/sources", json={"library_id": a["id"], "title": "Sample"}).json()
    assert client.put("/sources/not-found/library", json={"library_id": b["id"]}).status_code == 404
    assert client.put(f"/sources/{source['id']}/library", json={"library_id": "unknown"}).status_code == 404
    assert client.put(f"/sources/{source['id']}/library", json={"library_id": ""}).status_code == 422
    assert client.get(f"/sources/{source['id']}").json()["library_id"] == a["id"]


def test_same_library_is_noop_and_does_not_write(client, monkeypatch):
    library = client.post("/libraries", json={"name": "Original"}).json()
    source = client.post("/sources", json={"library_id": library["id"], "title": "Sample"}).json()
    monkeypatch.setattr(source_router, "persist_state", lambda: pytest.fail("No save necessary"))
    response = client.put(f"/sources/{source['id']}/library", json={"library_id": library["id"]})
    assert response.status_code == 200
    assert response.json()["changed"] is False


def test_failed_write_restores_in_memory_membership(client, monkeypatch):
    original = client.post("/libraries", json={"name": "Original"}).json()
    destination = client.post("/libraries", json={"name": "Destination"}).json()
    source = client.post("/sources", json={"library_id": original["id"], "title": "Sample"}).json()
    def fail():
        raise RuntimeError("synthetic persistence failure")
    monkeypatch.setattr(source_router, "persist_state", fail)
    response = client.put(
        f"/sources/{source['id']}/library",
        json={"library_id": destination["id"]},
    )
    assert response.status_code == 500
    assert client.get(f"/sources/{source['id']}").json()["library_id"] == original["id"]
