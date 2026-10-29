from typing import Annotated

from fastapi import Depends, Path, Request

from app.services.meter_service import MeterService


def service(request: Request) -> MeterService:
    return request.app.state.meters


Service = Annotated[MeterService, Depends(service)]

MeterId = Annotated[str, Path(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")]
