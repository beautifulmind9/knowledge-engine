from types import SimpleNamespace

import app.main as main


def test_admission_is_fail_fast_at_four_and_recovers_without_queueing():
    gate=main.RequestAdmission(4)
    assert [gate.try_enter() for _ in range(4)] == [True, True, True, True]
    assert gate.try_enter() is False
    gate.leave()
    assert gate.try_enter() is True
    for _ in range(4):
        gate.leave()


def test_health_auth_and_static_paths_remain_available_at_capacity():
    request=lambda path: SimpleNamespace(url=SimpleNamespace(path=path))
    for path in ("/", "/health", "/login", "/logout", "/static/app.js"):
        assert main._requires_resource_admission(request(path)) is False
    for path in ("/knowledge-assets/search", "/workshops/prepare", "/workshops/generate",
                 "/data/export", "/libraries"):
        assert main._requires_resource_admission(request(path)) is True


def test_hosted_fifth_api_request_gets_explicit_overload_response(client, monkeypatch):
    gate=main.RequestAdmission(4)
    for _ in range(4):
        assert gate.try_enter()
    monkeypatch.setattr(main, "resource_admission", gate)
    monkeypatch.setattr(main, "hosted_public_host", "testserver")
    try:
        response=client.get("/knowledge-assets/search", params={"q":"bounded retrieval"})
    finally:
        for _ in range(4):
            gate.leave()
    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    assert response.json() == {
        "detail":"Knowledge Engine is handling the maximum of four active requests. Retry shortly.",
        "code":"request_capacity_exceeded",
    }


def test_local_requests_do_not_consume_hosted_admission(client, monkeypatch):
    gate=main.RequestAdmission(1)
    assert gate.try_enter()
    monkeypatch.setattr(main, "resource_admission", gate)
    monkeypatch.setattr(main, "hosted_public_host", None)
    try:
        assert client.get("/libraries").status_code == 200
    finally:
        gate.leave()
