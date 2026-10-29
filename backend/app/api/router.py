"""Versioned HTTP route composition; register static meter paths before ID routes."""

from fastapi import APIRouter

from app.api.v1 import consumption, discovery, meters, network, transformers
from app.schemas.common import ErrorResponse

router = APIRouter(
    prefix="/api/v1",
    responses={code: {"model": ErrorResponse} for code in (404, 422, 502, 503, 504)},
)
for resource in (discovery, meters, consumption, network, transformers):
    router.include_router(resource.router)
