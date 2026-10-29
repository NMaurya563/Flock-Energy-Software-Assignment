from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class Reading(BaseModel):
    timestamp: datetime
    kwh: Decimal | None
    kvah: Decimal | None
    voltage_r: Decimal | None
    consumption_kwh: Decimal | None = None


class Consumption(BaseModel):
    meter_id: str
    data: list[Reading]
    total: int
    warnings: list[str]
    note: str = "Cumulative readings from the portal's default window; timestamps use assumed Asia/Kolkata."
