from datetime import datetime

from pydantic import BaseModel, Field


class HierarchyEntry(BaseModel):
    level: str
    code: str | None
    name: str | None


class Location(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class Meter(BaseModel):
    meter_id: str
    serial_number: str | None = None
    make: str | None = None
    phase: str | None = None
    status: str | None = None
    installation_type: str | None = None
    transformer_code: str | None = None
    location: Location | None = None
    hierarchy: list[HierarchyEntry] = []
    warnings: list[str] = []


class MeterPage(BaseModel):
    data: list[Meter]
    total: int
    page: int
    page_size: int
    fetched_at: datetime
