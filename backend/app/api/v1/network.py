from fastapi import APIRouter, Query

from app.api.dependencies import Service
from app.core.exceptions import PortalError
from app.schemas.network import Network, NetworkNode

router = APIRouter()


@router.get("/network", response_model=Network, tags=["Network"])
async def network(svc: Service):
    return await svc.network()


@router.get("/network/node", response_model=NetworkNode, tags=["Network"])
async def network_node(svc: Service, node_id: str = Query(min_length=1, max_length=1000)):
    for node in (await svc.network()).data:
        if node.id == node_id:
            return node
    raise PortalError("not_found", "Network node does not exist.", 404)
