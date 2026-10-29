from typing import Literal

from fastapi import APIRouter, Query

from app.api.dependencies import MeterId, Service
from app.core.exceptions import PortalError
from app.schemas.meter import Meter, MeterPage

router = APIRouter()


@router.get("/meters", response_model=MeterPage, tags=["Meters"])
async def meters(
    svc: Service,
    q: str = Query("", max_length=100),
    status: str | None = Query(None, max_length=80),
    make: str | None = Query(None, max_length=80),
    transformer: str | None = Query(None, max_length=80),
    phase: str | None = Query(None, max_length=80),
    installation_type: str | None = Query(None, max_length=80),
    hierarchy_level: Literal["zone", "circle", "division", "subdivision", "substation", "feeder", "dt"]
    | None = None,
    hierarchy_code: str | None = Query(None, min_length=1, max_length=80),
    sort_by: Literal["meter_id", "make", "status"] = "meter_id",
    order: Literal["asc", "desc"] = "asc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    if (hierarchy_level is None) != (hierarchy_code is None):
        raise PortalError("invalid_filter", "Supply hierarchy_level and hierarchy_code together.", 422)
    return await svc.list_meters(
        q=q,
        status=status,
        make=make,
        transformer=transformer,
        page=page,
        page_size=page_size,
        phase=phase,
        installation_type=installation_type,
        hierarchy_level=hierarchy_level,
        hierarchy_code=hierarchy_code,
        sort_by=sort_by,
        order=order,
    )


@router.get("/meters/{meter_id}", response_model=Meter, tags=["Meters"])
async def meter(meter_id: MeterId, svc: Service):
    return await svc.detail(meter_id)
