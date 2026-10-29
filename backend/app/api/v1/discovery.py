from fastapi import APIRouter, Query

from app.api.dependencies import Service
from app.domain.discovery import nearby, overview
from app.schemas.discovery import CacheMetadata, FleetOverview, NearbyMeters

router = APIRouter()


@router.get("/meters/nearby", response_model=NearbyMeters, tags=["Discovery"])
async def nearby_meters(
    svc: Service,
    latitude: float = Query(ge=-90, le=90, allow_inf_nan=False),
    longitude: float = Query(ge=-180, le=180, allow_inf_nan=False),
    radius_km: float = Query(5, gt=0, le=20000, allow_inf_nan=False),
    limit: int = Query(20, ge=1, le=100),
):
    """Meters within a radius, ordered by great-circle distance; total is before limiting."""
    meters = await svc.snapshot()
    return nearby(meters, svc.fetched_at, latitude, longitude, radius_km, limit)


@router.get("/overview", response_model=FleetOverview, tags=["Discovery"])
async def fleet_overview(svc: Service):
    """Fleet counts and data completeness from one snapshot; no inferred operational alarms."""
    meters = await svc.snapshot()
    return overview(meters, svc.fetched_at)


@router.get("/meta", response_model=CacheMetadata, tags=["Health"])
async def cache_metadata(svc: Service):
    """Cache state only. Does not contact the portal or trigger refresh."""
    return svc.metadata()
