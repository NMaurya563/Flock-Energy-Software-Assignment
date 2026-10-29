"""Read-only fleet queries over a verified meter snapshot; no additional portal calls."""

from collections import Counter
from datetime import datetime
from math import asin, cos, radians, sin, sqrt

from app.domain.constants import LEVELS
from app.schemas.discovery import FleetOverview, NearbyMeter, NearbyMeters
from app.schemas.meter import Location, Meter


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat_delta, lon_delta = radians(lat2 - lat1), radians(lon2 - lon1)
    haversine = sin(lat_delta / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(lon_delta / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(min(1.0, max(0.0, haversine))))


def nearby(
    meters: list[Meter], fetched_at: datetime, latitude: float, longitude: float, radius_km: float, limit: int
) -> NearbyMeters:
    matches: list[tuple[float, Meter]] = []
    excluded = 0
    for meter in meters:
        if meter.location is None:
            excluded += 1
            continue
        distance = distance_km(latitude, longitude, meter.location.latitude, meter.location.longitude)
        if distance <= radius_km:
            matches.append((distance, meter))
    matches.sort(key=lambda pair: (pair[0], pair[1].meter_id))
    rows = [
        NearbyMeter(**meter.model_dump(), distance_km=round(distance, 6))
        for distance, meter in matches[:limit]
    ]
    return NearbyMeters(
        data=rows,
        total=len(matches),
        returned=len(rows),
        center=Location(latitude=latitude, longitude=longitude),
        radius_km=radius_km,
        excluded_without_location=excluded,
        fetched_at=fetched_at,
    )


def overview(meters: list[Meter], fetched_at: datetime) -> FleetOverview:
    def counts(field: str) -> dict[str, int]:
        return dict(sorted(Counter(getattr(m, field) or "Unknown" for m in meters).items()))

    located = sum(m.location is not None for m in meters)
    expected_levels = set(LEVELS)
    incomplete = sum(
        {entry.level for entry in m.hierarchy if entry.code and entry.name} != expected_levels for m in meters
    )
    return FleetOverview(
        total_meters=len(meters),
        by_status=counts("status"),
        by_make=counts("make"),
        by_phase=counts("phase"),
        distinct_transformer_codes=len({m.transformer_code for m in meters if m.transformer_code}),
        meters_with_location=located,
        meters_without_location=len(meters) - located,
        meters_with_warnings=sum(bool(m.warnings) for m in meters),
        meters_with_incomplete_hierarchy=incomplete,
        fetched_at=fetched_at,
    )
