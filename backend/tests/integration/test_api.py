import copy

import httpx
import pytest
from conftest import METER


def test_liveness_does_not_login(client, portal):
    assert client.get("/health").json() == {"status": "ok"}
    assert portal[0]["logins"] == 0


def test_search_and_cache(client, portal):
    response = client.get("/api/v1/meters?q=se33962")
    assert response.status_code == 200
    assert response.json()["data"][0]["meter_id"] == "J100000"
    assert response.json()["data"][0]["location"]["latitude"] == METER["geo"]["lat"]
    assert client.get("/api/v1/meters?make=Other").json()["total"] == 0
    client.get("/api/v1/meters/J100000")
    assert portal[0]["exports"] == 1


def test_pagination(client, portal):
    other = copy.deepcopy(METER)
    other["meterId"] = "J100001"
    portal[0]["meters"].append(other)
    data = client.get("/api/v1/meters?page=2&page_size=1").json()
    assert data["total"] == 2
    assert data["data"][0]["meter_id"] == "J100001"


@pytest.mark.parametrize("query", ["page=0", "page_size=101", "page_size=bad"])
def test_validation(client, query):
    response = client.get("/api/v1/meters?" + query)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_missing_meter(client):
    assert client.get("/api/v1/meters/MISSING").status_code == 404


def test_consumption_normalizes_and_filters(client):
    response = client.get(
        "/api/v1/meters/J100000/consumption",
        params={"start": "2026-06-24T00:00:00+05:30", "end": "2026-06-24T00:00:00+05:30"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["kwh"] == "48439.16"
    assert data["data"][0]["timestamp"].endswith("+05:30")


@pytest.mark.parametrize(
    "params",
    [
        {"start": "2026-06-24"},
        {"start": "2026-06-25T00:00:00Z", "end": "2026-06-24T00:00:00Z"},
    ],
)
def test_invalid_dates(client, params):
    assert client.get("/api/v1/meters/J100000/consumption", params=params).status_code == 422


def test_bad_readings_preserve_zero_and_warn(client, portal):
    portal[0]["readings"] = [
        {"timestamp": "24/06/2026 00:00", "kwh": "0", "kvah": "NaN", "voltR": "bad"},
        {"timestamp": "broken"},
    ]
    data = client.get("/api/v1/meters/J100000/consumption").json()
    assert data["total"] == 1
    assert data["data"][0]["kwh"] == "0"
    assert data["data"][0]["kvah"] is None
    assert len(data["warnings"]) == 3


def test_invalid_coordinates_are_not_fabricated(client, portal):
    portal[0]["meters"][0]["geo"]["lat"] = 200
    data = client.get("/api/v1/meters/J100000").json()
    assert data["location"] is None
    assert data["warnings"]


def test_hierarchy_preserves_conflicting_parents(client, portal):
    second = copy.deepcopy(METER)
    second["meterId"] = "J100001"
    second["hierarchy"]["zone"]["code"] = "Z-02"
    portal[0]["meters"].append(second)
    data = client.get("/api/v1/network").json()
    assert len([n for n in data["data"] if n["level"] == "dt"]) == 2
    assert data["warnings"]
    node = data["data"][0]
    assert client.get("/api/v1/network/node", params={"node_id": node["id"]}).json() == node


def test_session_is_renewed_once(client, portal):
    portal[0]["expire"] = True
    assert client.get("/api/v1/meters").status_code == 200
    assert portal[0]["logins"] == 2


def test_bad_json_is_a_clean_error(client, portal):
    portal[0]["fail"] = lambda _: httpx.Response(200, text="<html>bad</html>")
    response = client.get("/api/v1/meters")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_upstream_response"


def test_transient_failures_have_bounded_retries(client, portal):
    calls = []

    def failure(request):
        calls.append(request)
        return httpx.Response(503)

    portal[0]["fail"] = failure
    assert client.get("/api/v1/meters").status_code == 503
    assert len(calls) == 2


def test_timeout_is_504(client, portal):
    def timeout(request):
        raise httpx.ReadTimeout("synthetic", request=request)

    portal[0]["fail"] = timeout
    assert client.get("/api/v1/meters").status_code == 504


def test_openapi(client):
    schema = client.get("/openapi.json").json()
    assert schema["openapi"].startswith("3.")
    assert "/api/v1/meters/{meter_id}/consumption" in schema["paths"]


def test_duplicate_export_fails_instead_of_losing_data(client, portal):
    portal[0]["meters"].append(copy.deepcopy(METER))
    response = client.get("/api/v1/meters")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_upstream_response"


def test_bad_signing_key_envelope(client, portal):
    portal[0]["fail"] = lambda _: httpx.Response(200, json={"data": []})
    assert client.get("/api/v1/meters").status_code == 502


def test_persistent_session_failure_is_bounded(client, portal):
    calls = []

    def unauthorized(request):
        calls.append(request)
        return httpx.Response(401, json={"error": "unauthorized"})

    portal[0]["fail"] = unauthorized
    assert client.get("/api/v1/meters").status_code == 503
    assert portal[0]["logins"] == 2
    assert len(calls) == 2


def test_filter_status_and_transformer(client):
    assert client.get("/api/v1/meters?status=Decommissioned&transformer=DT-001").json()["total"] == 1
    assert client.get("/api/v1/meters?status=Installed").json()["total"] == 0


def test_out_of_window_is_empty(client):
    response = client.get("/api/v1/meters/J100000/consumption?start=2027-01-01T00:00:00Z")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_malformed_reading_row_warns(client, portal):
    portal[0]["readings"] = ["broken"]
    response = client.get("/api/v1/meters/J100000/consumption")
    assert response.status_code == 200
    assert response.json()["warnings"]


def test_unknown_network_node(client):
    assert client.get("/api/v1/network/node?node_id=unknown").status_code == 404


def test_transformer_directory_and_detail(client):
    response = client.get("/api/v1/transformers")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    detail = client.get("/api/v1/transformers/DT-001")
    assert detail.json()["capacity_kva"] == "100"
    assert client.get("/api/v1/transformers/MISSING").status_code == 404


def test_delta_is_computed_after_chronological_sort(client, portal):
    portal[0]["readings"].reverse()
    rows = client.get("/api/v1/meters/J100000/consumption").json()["data"]
    assert rows[0]["consumption_kwh"] is None
    assert rows[1]["consumption_kwh"] == "0.42"


def test_invalid_register_breaks_delta_chain(client, portal):
    portal[0]["readings"] = [
        {"timestamp": "24/06/2026 00:00", "kwh": "10", "kvah": "10", "voltR": "230"},
        {"timestamp": "24/06/2026 00:30", "kwh": "bad", "kvah": "10", "voltR": "230"},
        {"timestamp": "24/06/2026 01:00", "kwh": "11", "kvah": "10", "voltR": "230"},
    ]
    data = client.get("/api/v1/meters/J100000/consumption").json()
    assert data["data"][1]["kwh"] is None
    assert all(row["consumption_kwh"] is None for row in data["data"])
    assert data["warnings"]


def test_register_reset_does_not_emit_negative_consumption(client, portal):
    portal[0]["readings"][1]["kwh"] = "1"
    data = client.get("/api/v1/meters/J100000/consumption").json()
    assert data["data"][1]["consumption_kwh"] is None
    assert "decreased" in data["warnings"][0]


def test_duplicate_timestamp_has_no_delta(client, portal):
    portal[0]["readings"][1]["timestamp"] = portal[0]["readings"][0]["timestamp"]
    data = client.get("/api/v1/meters/J100000/consumption").json()
    assert data["data"][1]["consumption_kwh"] is None
    assert data["warnings"]


def test_partial_export_is_rejected(client, portal):
    def partial(request):
        if request.url.path == "/portal/keys":
            return httpx.Response(200, json={"data": {"signingSecret": "test"}})
        return httpx.Response(200, json={"data": [METER], "total": 2})

    portal[0]["fail"] = partial
    assert client.get("/api/v1/meters").status_code == 502


def test_blank_meter_id_is_rejected(client, portal):
    portal[0]["meters"][0]["meterId"] = " "
    assert client.get("/api/v1/meters").status_code == 502


def test_missing_registers_are_null_with_warnings(client, portal):
    portal[0]["readings"] = [{"timestamp": "24/06/2026 00:00", "kwh": "0"}]
    data = client.get("/api/v1/meters/J100000/consumption").json()
    assert data["data"][0]["kwh"] == "0"
    assert data["data"][0]["kvah"] is None
    assert data["data"][0]["voltage_r"] is None
    assert len(data["warnings"]) == 2


@pytest.mark.parametrize("hierarchy", [[], False, "broken"])
def test_malformed_hierarchy_does_not_disappear_silently(client, portal, hierarchy):
    portal[0]["meters"][0]["hierarchy"] = hierarchy
    response = client.get("/api/v1/meters")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_upstream_response"


def test_malformed_coordinate_and_tier_shapes_are_reported(client, portal):
    portal[0]["meters"][0]["geo"] = []
    portal[0]["meters"][0]["hierarchy"]["zone"] = "broken"
    data = client.get("/api/v1/meters/J100000").json()
    assert data["location"] is None
    assert len(data["warnings"]) == 2
    assert all(entry["level"] != "zone" for entry in data["hierarchy"])
