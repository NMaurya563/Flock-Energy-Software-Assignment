from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.meter import Location, Meter


class NearbyMeter(Meter):
    distance_km: float = Field(ge=0, allow_inf_nan=False)


class NearbyMeters(BaseModel):
    data: list[NearbyMeter]
    total: int = Field(description="All matching meters before the result limit.")
    returned: int
    center: Location
    radius_km: float
    excluded_without_location: int
    fetched_at: datetime


class FleetOverview(BaseModel):
    total_meters: int
    by_status: dict[str, int]
    by_make: dict[str, int]
    by_phase: dict[str, int]
    distinct_transformer_codes: int
    meters_with_location: int
    meters_without_location: int
    meters_with_warnings: int
    meters_with_incomplete_hierarchy: int
    fetched_at: datetime


class CacheMetadata(BaseModel):
    state: Literal["not_loaded", "fresh", "expired"]
    cached_meters: int
    fetched_at: datetime | None
    age_seconds: float | None
    ttl_seconds: int
    refresh_in_progress: bool
