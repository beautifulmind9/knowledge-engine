"""Synthetic held interpretation: health is live, ordinary state stays serialized."""
import asyncio
from threading import Event

import httpx
import pytest
import app.main as main


def test_health_does_not_wait_for_interpretation_but_usage_does(monkeypatch):
    entered, release, usage_entered = Event(), Event(), Event()

    def held_interpretation(**kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return {"processed_this_run": 1}

    def usage_status():
        usage_entered.set()
        return {"daily_call_limit": 450, "calls_today": 0}

    monkeypatch.setattr("app.routers.knowledge.interpret_source", held_interpretation)
    monkeypatch.setattr("app.routers.control.status", usage_status)

    async def exercise():
        monkeypatch.setattr(main, "request_lock", asyncio.Lock())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://testserver") as client:
            building = asyncio.create_task(client.post("/sources/synthetic/interpret?max_chunks=1"))
            usage_request = None
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                health = await asyncio.wait_for(client.get("/health"), timeout=1)
                assert health.status_code == 200
                assert health.json() == {"status": "ok"}
                assert health.headers["cache-control"] == "no-store"
                assert health.headers["x-content-type-options"] == "nosniff"
                assert "frame-ancestors 'none'" in health.headers["content-security-policy"]
                usage_request = asyncio.create_task(client.get("/usage"))
                await asyncio.sleep(0.05)
                assert not usage_request.done()
                assert not usage_entered.is_set()
            finally:
                release.set()
                assert (await building).status_code == 200
                if usage_request is not None:
                    assert (await usage_request).status_code == 200
            assert usage_entered.is_set()

    asyncio.run(exercise())


@pytest.mark.parametrize("headers,expected", [({"Host": "untrusted.example"}, 400), ({"Origin": "https://untrusted.example"}, 403)])
def test_health_lock_exception_retains_host_and_origin_checks(client, headers, expected):
    assert client.get("/health", headers=headers).status_code == expected
