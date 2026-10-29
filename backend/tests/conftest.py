import copy

import httpx
import pytest
from fastapi.testclient import TestClient

from app.clients.urja_client import COOKIE
from app.core.config import Settings
from app.main import create_app

# Representative observed record, with synthetic variants supplied by individual tests.
METER = {
    "meterId": "J100000",
    "serialNo": "SE33962",
    "make": "HPL",
    "phaseType": "single",
    "installStatus": "Decommissioned",
    "installType": "Whole Current",
    "dtCode": "DT-001",
    "geo": {"lat": 26.938961002479868, "lng": 75.83095696146852},
    "hierarchy": {
        "zone": {"name": "Jaipur Zone 1", "code": "Z-01"},
        "dt": {"name": "Malviya Nagar DT 1", "code": "DT-001"},
    },
}
READINGS = [
    {"timestamp": "23/06/2026 23:30", "kwh": "48438.74", "kvah": "52313.84", "voltR": "226"},
    {"timestamp": "24/06/2026 00:00", "kwh": "48439.16", "kvah": "52314.29", "voltR": "229"},
]


@pytest.fixture
def portal():
    state = {
        "logins": 0,
        "exports": 0,
        "meters": [copy.deepcopy(METER)],
        "readings": copy.deepcopy(READINGS),
        "energy_queries": [],
        "fail": None,
        "expire": False,
    }

    def handler(request):
        path = request.url.path
        if path == "/login":
            state["logins"] += 1
            assert request.headers["origin"] == "https://urja-ops.flockenergy.tech"
            return httpx.Response(
                200,
                json={"type": "redirect", "status": 303, "location": "/meters"},
                headers={"set-cookie": f"{COOKIE}=test-session; Path=/; Secure; HttpOnly"},
            )
        if state["expire"]:
            state["expire"] = False
            return httpx.Response(401, json={"error": "unauthorized"})
        if state["fail"]:
            return state["fail"](request)
        if path == "/portal/dts":
            page = int(request.url.params["page"])
            rows = [
                {"code": "DT-001", "name": "Malviya Nagar DT 1", "feederCode": "F-001", "capacityKva": 100}
            ]
            return httpx.Response(
                200, json={"data": rows if page == 1 else [], "total": 1, "page": page, "pageSize": 20}
            )
        if path == "/portal/keys":
            return httpx.Response(200, json={"data": {"signingSecret": "synthetic-test-key"}})
        if path == "/portal/export":
            import hashlib
            import hmac

            state["exports"] += 1
            timestamp = request.headers["x-timestamp"]
            message = "\n".join(("GET", "/portal/export", "page=1", timestamp))
            expected = hmac.new(b"synthetic-test-key", message.encode(), hashlib.sha256).hexdigest()
            assert request.headers["x-signature"] == expected
            return httpx.Response(200, json={"data": state["meters"], "total": len(state["meters"])})
        if path.endswith("/energy"):
            state["energy_queries"].append(dict(request.url.params))
            return httpx.Response(200, json={"data": state["readings"]})
        return httpx.Response(404, json={"error": "not_found"})

    return state, httpx.MockTransport(handler)


@pytest.fixture
def client(portal):
    _, transport = portal
    settings = Settings(
        portal_username="test@example.com",
        portal_password="synthetic-password",
        upstream_attempts=2,
        _env_file=None,
    )
    with TestClient(create_app(settings, transport)) as client:
        yield client
