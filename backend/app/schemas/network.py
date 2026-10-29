from datetime import datetime

from pydantic import BaseModel


class NetworkNode(BaseModel):
    id: str
    level: str
    code: str | None
    name: str | None
    parent_id: str | None
    meter_count: int


class Network(BaseModel):
    data: list[NetworkNode]
    warnings: list[str]
    fetched_at: datetime
