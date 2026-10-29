from fastapi import APIRouter

from app.api.dependencies import Service
from app.core.exceptions import PortalError
from app.schemas.transformer import Transformer, TransformerList

router = APIRouter()


@router.get("/transformers", response_model=TransformerList, tags=["Transformers"])
async def transformers(svc: Service):
    return await svc.transformers()


@router.get("/transformers/{transformer_code}", response_model=Transformer, tags=["Transformers"])
async def transformer(transformer_code: str, svc: Service):
    for item in (await svc.transformers()).data:
        if item.code == transformer_code:
            return item
    raise PortalError("not_found", "Transformer does not exist.", 404)
