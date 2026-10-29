import asyncio

import httpx
import pytest

from app.clients.urja_client import UrjaClient
from app.core.config import Settings
from app.core.exceptions import PortalError


async def test_concurrent_login_is_single_flight(portal):
    state, transport = portal
    client = UrjaClient(Settings(portal_username="test", portal_password="test", _env_file=None), transport)
    try:
        await asyncio.gather(*(client.get("/portal/keys") for _ in range(10)))
        assert state["logins"] == 1
    finally:
        await client.close()


async def test_missing_credentials_does_not_contact_portal():
    def handler(request):
        pytest.fail("Should not contact portal")

    client = UrjaClient(
        Settings(portal_username="", portal_password="", _env_file=None), httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(PortalError) as exc:
            await client.get("/portal/keys")
        assert exc.value.code == "not_configured"
    finally:
        await client.close()


async def test_rejected_credentials():
    transport = httpx.MockTransport(lambda _: httpx.Response(400, json={"message": "bad login"}))
    client = UrjaClient(Settings(portal_username="test", portal_password="test", _env_file=None), transport)
    try:
        with pytest.raises(PortalError) as exc:
            await client.get("/portal/keys")
        assert exc.value.status == 503
    finally:
        await client.close()


async def test_four_simultaneous_expired_requests_complete():
    arrivals = 0
    all_expired = asyncio.Event()
    login_count = 0

    async def handler(request):
        nonlocal arrivals, login_count
        if request.url.path == "/login":
            login_count += 1
            return httpx.Response(
                200,
                headers={
                    "set-cookie": f"__Secure-better-auth.session_token=session-{login_count}; Path=/; Secure"
                },
            )
        if "session-1" in request.headers.get("cookie", ""):
            arrivals += 1
            if arrivals == 4:
                all_expired.set()
            await all_expired.wait()
            return httpx.Response(401)
        return httpx.Response(200, json={"data": {"ok": True}})

    client = UrjaClient(
        Settings(portal_username="test", portal_password="test", _env_file=None), httpx.MockTransport(handler)
    )
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(client.get("/portal/keys") for _ in range(4))), timeout=2
        )
        assert len(results) == 4
        assert login_count == 2
    finally:
        await client.close()


async def test_auth_replay_does_not_consume_transient_budget():
    calls = 0

    def handler(request):
        nonlocal calls
        if request.url.path == "/login":
            return httpx.Response(
                200, headers={"set-cookie": "__Secure-better-auth.session_token=test; Path=/; Secure"}
            )
        calls += 1
        if calls == 1:
            return httpx.Response(401)
        if calls == 2:
            return httpx.Response(503)
        return httpx.Response(200, json={"data": []})

    client = UrjaClient(
        Settings(portal_username="test", portal_password="test", upstream_attempts=2, _env_file=None),
        httpx.MockTransport(handler),
    )
    try:
        assert await client.get("/portal/dts") == {"data": []}
        assert calls == 3
    finally:
        await client.close()


@pytest.mark.parametrize(
    "fault", [None, "duplicate", "missing", "changed_total", "wrong_page", "invalid_size", "changed_size"]
)
async def test_transformer_pagination_follows_metadata(fault):
    pages = []

    def handler(request):
        if request.url.path == "/login":
            return httpx.Response(
                200, headers={"set-cookie": "__Secure-better-auth.session_token=test; Path=/; Secure"}
            )
        page = int(request.url.params["page"])
        pages.append(page)
        rows = [{"code": f"DT-{page}"}]
        payload = {"data": rows, "total": 3, "page": page, "pageSize": 1}
        if page == 2:
            if fault == "duplicate":
                rows[0]["code"] = "DT-1"
            elif fault == "missing":
                payload["data"] = []
            elif fault == "changed_total":
                payload["total"] = 4
            elif fault == "wrong_page":
                payload["page"] = 1
            elif fault == "invalid_size":
                payload["pageSize"] = 0
            elif fault == "changed_size":
                payload["pageSize"] = 2
                payload["data"] = [{"code": "DT-2"}, {"code": "DT-3"}]
        return httpx.Response(200, json=payload)

    client = UrjaClient(
        Settings(portal_username="test", portal_password="test", _env_file=None), httpx.MockTransport(handler)
    )
    try:
        if fault:
            with pytest.raises(PortalError) as exc:
                await client.transformers()
            assert exc.value.status == 502
        else:
            assert len(await client.transformers()) == 3
            assert pages == [1, 2, 3]
    finally:
        await client.close()


async def test_forbidden_resource_does_not_trigger_login_loop(portal):
    state, transport = portal
    state["fail"] = lambda request: httpx.Response(403, json={"error": "invalid_signature"})
    client = UrjaClient(Settings(portal_username="test", portal_password="test", _env_file=None), transport)
    try:
        with pytest.raises(PortalError) as error:
            await client.get("/portal/export")
        assert error.value.code == "upstream_forbidden"
        assert error.value.status == 502
        assert state["logins"] == 1
    finally:
        await client.close()
