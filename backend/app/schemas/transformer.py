from decimal import Decimal

from pydantic import BaseModel, Field


class Transformer(BaseModel):
    code: str = Field(min_length=1)
    name: str
    feeder_code: str
    capacity_kva: Decimal = Field(ge=0, allow_inf_nan=False)


class TransformerList(BaseModel):
    data: list[Transformer]
    total: int
