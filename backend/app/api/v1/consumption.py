from datetime import datetime

from fastapi import APIRouter

from app.api.dependencies import MeterId, Service
from app.core.exceptions import PortalError
from app.schemas.consumption import Consumption

router = APIRouter()


@router.get("/meters/{meter_id}/consumption", response_model=Consumption, tags=["Consumption"])
async def consumption(
    meter_id: MeterId, svc: Service, start: datetime | None = None, end: datetime | None = None
):
    """Both bounds fetch historical data (up to 93 local days); one bound filters the default window."""
    if any(value is not None and value.utcoffset() is None for value in (start, end)):
        raise PortalError("invalid_date_range", "Dates must include a timezone offset.", 422)
    if start and end and start > end:
        raise PortalError("invalid_date_range", "start must be before or equal to end.", 422)
    return await svc.consumption(meter_id, start, end)
