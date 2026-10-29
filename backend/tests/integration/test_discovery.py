import copy
from decimal import Decimal

import pytest
from conftest import METER


def test_nearby_sorts_and_reports_total_before_limit(client, portal):
    far = copy.deepcopy(METER)
    far["meterId"] = "J100001"
    far["geo"]["lat"] += 0.01
    missing = copy.deepcopy(METER)
    missing["meterId"] = "J100002"
    missing["geo"] = None
    portal[0]["meters"] = [far, missing, copy.deepcopy(METER)]
    result = client.get(
        "/api/v1/meters/nearby",
        params={
            "latitude": METER["geo"]["lat"],
            "longitude": METER["geo"]["lng"],
            "radius_km": 5,
            "limit": 1,
        },
    )
    assert result.status_code == 200  # Static path must precede /meters/{meter_id}.
    data = result.json()
    assert data["total"] == 2
    assert data["returned"] == 1
    assert data["excluded_without_location"] == 1
    assert data["data"][0]["meter_id"] == "J100000"
    assert data["data"][0]["distance_km"] == 0


def test_nearby_excludes_outside_radius(client):
    data = client.get("/api/v1/meters/nearby?latitude=0&longitude=0&radius_km=1").json()
    assert data["total"] == 0
    assert data["data"] == []


def test_zero_coordinates_are_valid(client, portal):
    portal[0]["meters"][0]["geo"] = {"lat": 0, "lng": 0}
    data = client.get("/api/v1/meters/nearby?latitude=0&longitude=0&radius_km=1").json()
    assert data["total"] == 1


@pytest.mark.parametrize(
    "query",
    [
        "latitude=91&longitude=0",
        "latitude=0&longitude=181",
        "latitude=nan&longitude=0",
        "latitude=0&longitude=inf",
        "latitude=0&longitude=0&radius_km=nan",
        "latitude=0&longitude=0&radius_km=0",
        "latitude=0&longitude=0&limit=101",
    ],
)
def test_nearby_validation_precedes_upstream(client, portal, query):
    assert client.get("/api/v1/meters/nearby?" + query).status_code == 422
    assert portal[0]["logins"] == 0


def test_overview_counts_and_quality(client, portal):
    other = copy.deepcopy(METER)
    other.update(meterId="J100001", make=None, installStatus="Faulty", phaseType="three")
    other["geo"] = {"lat": 200, "lng": 0}
    portal[0]["meters"].append(other)
    data = client.get("/api/v1/overview").json()
    assert data["total_meters"] == 2
    assert data["by_status"] == {"Decommissioned": 1, "Faulty": 1}
    assert data["by_make"] == {"HPL": 1, "Unknown": 1}
    assert data["meters_with_location"] == 1
    assert data["meters_without_location"] == 1
    assert data["meters_with_warnings"] == 1
    assert data["meters_with_incomplete_hierarchy"] == 2
    assert data["distinct_transformer_codes"] == 1
    assert portal[0]["exports"] == 1


def test_empty_fleet(client, portal):
    portal[0]["meters"] = []
    data = client.get("/api/v1/overview").json()
    assert data["total_meters"] == 0
    assert data["by_status"] == {}
    assert data["meters_with_location"] == 0


def test_metadata_is_passive_and_distinguishes_expiry(client, portal):
    data = client.get("/api/v1/meta").json()
    assert data["state"] == "not_loaded"
    assert data["age_seconds"] is None
    assert portal[0]["logins"] == 0
    client.get("/api/v1/meters")
    fresh = client.get("/api/v1/meta").json()
    assert fresh["state"] == "fresh"
    assert fresh["cached_meters"] == 1
    client.app.state.meters.expires = 0
    expired = client.get("/api/v1/meta").json()
    assert expired["state"] == "expired"
    assert portal[0]["exports"] == 1


def test_extended_filters_and_order(client, portal):
    second = copy.deepcopy(METER)
    second["meterId"] = "J100001"
    portal[0]["meters"].append(second)
    query = (
        "phase=single&installation_type=Whole%20Current&hierarchy_level=zone&hierarchy_code=Z-01&order=desc"
    )
    data = client.get("/api/v1/meters?" + query).json()
    assert data["total"] == 2
    assert data["data"][0]["meter_id"] == "J100001"
    assert client.get("/api/v1/meters?phase=three").json()["total"] == 0
    assert client.get("/api/v1/meters?hierarchy_level=zone&hierarchy_code=missing").json()["total"] == 0


@pytest.mark.parametrize(
    "query", ["hierarchy_level=zone", "hierarchy_code=Z-01", "sort_by=other", "order=other"]
)
def test_bad_filters_rejected(client, query):
    assert client.get("/api/v1/meters?" + query).status_code == 422


def test_historical_query_uses_ist_dates_and_exact_bounds(client, portal):
    portal[0]["readings"] = [
        {"timestamp": "02/06/2026 01:00", "kwh": "10", "kvah": "10", "voltR": "230"},
        {"timestamp": "02/06/2026 01:30", "kwh": "11", "kvah": "11", "voltR": "230"},
    ]
    response = client.get(
        "/api/v1/meters/J100000/consumption",
        params={"start": "2026-06-01T20:00:00Z", "end": "2026-06-02T20:00:00Z"},
    )
    assert response.status_code == 200
    assert portal[0]["energy_queries"] == [{"from": "2026-06-02", "to": "2026-06-03"}]
    assert response.json()["total"] == 1
    assert "Historical" in response.json()["note"]


def test_large_history_range_is_rejected_before_portal(client, portal):
    response = client.get(
        "/api/v1/meters/J100000/consumption",
        params={"start": "2026-01-01T00:00:00Z", "end": "2026-06-01T00:00:00Z"},
    )
    assert response.status_code == 422
    assert portal[0]["logins"] == 0


def test_one_sided_range_preserves_default_window_behavior(client, portal):
    response = client.get("/api/v1/meters/J100000/consumption?start=2026-06-24T00:00:00Z")
    assert response.status_code == 200
    assert portal[0]["energy_queries"] == [{}]
    assert "default window" in response.json()["note"]


def test_ambiguous_duplicates_do_not_create_adjacent_deltas(client, portal):
    portal[0]["readings"] = [
        {"timestamp": ts, "kwh": value, "kvah": value, "voltR": "230"}
        for ts, value in [
            ("24/06/2026 00:00", "10"),
            ("24/06/2026 00:30", "11"),
            ("24/06/2026 00:30", "12"),
            ("24/06/2026 01:00", "13"),
            ("24/06/2026 01:30", "14"),
        ]
    ]
    data = client.get("/api/v1/meters/J100000/consumption").json()
    assert all(row["consumption_kwh"] is None for row in data["data"][:4])
    assert Decimal(data["data"][4]["consumption_kwh"]) == 1


def test_unknown_path_and_method_have_standard_errors(client):
    assert client.get("/missing").json()["error"]["code"] == "not_found"
    response = client.post("/api/v1/meters")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_new_routes_are_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/api/v1/meters/nearby", "/api/v1/overview", "/api/v1/meta"} <= paths.keys()
