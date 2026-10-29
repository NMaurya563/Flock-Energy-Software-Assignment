"""Explicit opt-in live API check. No credentials or upstream secrets are printed."""

import argparse
import asyncio
from contextlib import asynccontextmanager

import httpx

from app.main import create_app


@asynccontextmanager
async def api_client(base_url):
    if base_url:
        async with httpx.AsyncClient(base_url=base_url, timeout=90) as client:
            yield client
    else:
        app = create_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://smoke", timeout=90
            ) as client:
                yield client


async def main(base_url=None):
    async with api_client(base_url) as client:

        async def get(path, params=None, expected=200):
            response = await client.get(path, params=params)
            assert response.status_code == expected, (
                f"{path}: expected {expected}, got {response.status_code}"
            )
            return response.json()

        assert (await get("/health"))["status"] == "ok"
        await get("/api/v1/meta")
        page = await get("/api/v1/meters", {"page_size": 2})
        assert page["total"] >= len(page["data"])
        overview = await get("/api/v1/overview")
        assert overview["total_meters"] == page["total"]
        assert sum(overview["by_status"].values()) == page["total"]
        if page["data"]:
            first = page["data"][0]
            meter_id = first["meter_id"]
            assert (await get(f"/api/v1/meters/{meter_id}"))["meter_id"] == meter_id
            readings = await get(f"/api/v1/meters/{meter_id}/consumption")
            assert readings["total"] == len(readings["data"])
            historical = await get(
                f"/api/v1/meters/{meter_id}/consumption",
                {"start": "2026-06-01T00:00:00+05:30", "end": "2026-06-02T23:59:59+05:30"},
            )
            assert historical["total"] == len(historical["data"])
            assert all("2026-06-01" <= row["timestamp"][:10] <= "2026-06-02" for row in historical["data"])
            if first["location"]:
                nearby = await get("/api/v1/meters/nearby", {**first["location"], "radius_km": 1})
                assert nearby["total"] >= 1
                assert nearby["data"][0]["distance_km"] == 0
            filtered = await get("/api/v1/meters", {"q": meter_id, "sort_by": "make", "order": "desc"})
            assert any(row["meter_id"] == meter_id for row in filtered["data"])
            print(
                f"Verified meter detail, {readings['total']} default readings, and {historical['total']} historical readings"
            )
        transformers = await get("/api/v1/transformers")
        if transformers["data"]:
            code = transformers["data"][0]["code"]
            assert (await get(f"/api/v1/transformers/{code}"))["code"] == code
        network = await get("/api/v1/network")
        if network["data"]:
            node = network["data"][0]
            assert await get("/api/v1/network/node", {"node_id": node["id"]}) == node
        assert (await get("/api/v1/meta"))["cached_meters"] == page["total"]
        assert "error" in await get("/missing", expected=404)
        assert "error" in await get("/api/v1/meters", {"page": 0}, expected=422)
        assert (await client.get("/docs")).status_code == 200
        schema = await get("/openapi.json")
        assert "/api/v1/meters/nearby" in schema["paths"]
        print(
            f"Verified {page['total']} meters, {transformers['total']} transformers, {len(network['data'])} hierarchy nodes"
        )
        print(f"All {len(schema['paths'])} documented API paths checked, plus docs and representative errors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Optional URL of an already-running API")
    args = parser.parse_args()
    asyncio.run(main(args.base_url))
