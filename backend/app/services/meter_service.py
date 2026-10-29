"""Coordinate portal reads, snapshot freshness, and application queries."""

import asyncio
import time
from datetime import UTC, datetime
from typing import Literal

from app.clients.urja_client import UrjaClient
from app.core.exceptions import PortalError
from app.domain.constants import INDIA
from app.domain.consumption import normalize_readings
from app.domain.network import build_network
from app.domain.normalization import normalize_meter
from app.schemas.consumption import Consumption
from app.schemas.discovery import CacheMetadata
from app.schemas.meter import Meter, MeterPage
from app.schemas.network import Network
from app.schemas.transformer import Transformer, TransformerList


class MeterService:
    def __init__(self, client: UrjaClient, ttl: int) -> None:
        self.client = client
        self.ttl = ttl
        self.lock = asyncio.Lock()
        self.cached: list[Meter] | None = None
        self.expires = 0.0
        self.fetched_at: datetime | None = None

    async def snapshot(self) -> list[Meter]:
        async with self.lock:
            if self.cached is not None and time.monotonic() < self.expires:
                return self.cached
            raw = await self.client.export()
            try:
                rows = raw["data"]
                if (
                    not isinstance(rows, list)
                    or type(raw["total"]) is not int
                    or raw["total"] < 0
                    or len(rows) != raw["total"]
                ):
                    raise ValueError("Incomplete export")
                meters = [normalize_meter(row) for row in rows]
                if any(not m.meter_id.strip() for m in meters):
                    raise ValueError("Empty identifier")
                if len({m.meter_id for m in meters}) != len(meters):
                    raise ValueError("Duplicate identifiers")
            except (KeyError, TypeError, ValueError):
                raise PortalError(
                    "invalid_upstream_response", "Portal export was incomplete or malformed."
                ) from None
            self.cached = meters
            self.fetched_at = datetime.now(UTC)
            self.expires = time.monotonic() + self.ttl
            return meters

    async def list_meters(
        self,
        *,
        q: str = "",
        status: str | None = None,
        make: str | None = None,
        transformer: str | None = None,
        page: int = 1,
        page_size: int = 20,
        phase: str | None = None,
        installation_type: str | None = None,
        hierarchy_level: str | None = None,
        hierarchy_code: str | None = None,
        sort_by: Literal["meter_id", "make", "status"] = "meter_id",
        order: Literal["asc", "desc"] = "asc",
    ) -> MeterPage:
        meters = await self.snapshot()
        search = q.casefold()
        filters = {
            "status": status,
            "make": make,
            "transformer_code": transformer,
            "phase": phase,
            "installation_type": installation_type,
        }
        selected = []
        for meter in meters:
            searchable = f"{meter.meter_id} {meter.serial_number or ''}".casefold()
            if search and search not in searchable:
                continue
            if any(value and getattr(meter, field) != value for field, value in filters.items()):
                continue
            if hierarchy_level and not any(
                entry.level == hierarchy_level and entry.code == hierarchy_code for entry in meter.hierarchy
            ):
                continue
            selected.append(meter)
        selected.sort(
            key=lambda meter: ((getattr(meter, sort_by) or "").casefold(), meter.meter_id),
            reverse=order == "desc",
        )
        start = (page - 1) * page_size
        return MeterPage(
            data=selected[start : start + page_size],
            total=len(selected),
            page=page,
            page_size=page_size,
            fetched_at=self.fetched_at,
        )

    async def detail(self, meter_id: str) -> Meter:
        for meter in await self.snapshot():
            if meter.meter_id == meter_id:
                return meter
        raise PortalError("not_found", "Meter does not exist.", 404)

    async def consumption(self, meter_id: str, start: datetime | None, end: datetime | None) -> Consumption:
        params = None
        # The portal accepts inclusive local calendar dates. Preserve exact public boundaries below.
        if start is not None and end is not None:
            first_day, last_day = start.astimezone(INDIA).date(), end.astimezone(INDIA).date()
            if (last_day - first_day).days >= 93:
                raise PortalError(
                    "invalid_date_range", "Historical queries support at most 93 calendar days.", 422
                )
            params = {"from": first_day.isoformat(), "to": last_day.isoformat()}
        await self.detail(meter_id)
        raw = await self.client.get(f"/portal/meters/{meter_id}/energy", params=params)
        return normalize_readings(raw["data"], meter_id, start, end, historical=params is not None)

    async def network(self) -> Network:
        meters = await self.snapshot()
        return build_network(meters, self.fetched_at)

    async def transformers(self) -> TransformerList:
        rows = await self.client.transformers()
        try:
            data = [
                Transformer(
                    code=row["code"],
                    name=row["name"],
                    feeder_code=row["feederCode"],
                    capacity_kva=row["capacityKva"],
                )
                for row in rows
            ]
        except (KeyError, TypeError, ValueError):
            raise PortalError("invalid_upstream_response", "Transformer records were malformed.") from None
        return TransformerList(data=data, total=len(data))

    def metadata(self) -> CacheMetadata:
        if self.fetched_at is None:
            state = "not_loaded"
            age_seconds = None
        else:
            state = "fresh" if time.monotonic() < self.expires else "expired"
            age_seconds = max(0.0, (datetime.now(UTC) - self.fetched_at).total_seconds())
        return CacheMetadata(
            state=state,
            cached_meters=len(self.cached) if self.cached is not None else 0,
            fetched_at=self.fetched_at,
            age_seconds=age_seconds,
            ttl_seconds=self.ttl,
            refresh_in_progress=self.lock.locked(),
        )
