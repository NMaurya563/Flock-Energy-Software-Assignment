import json
import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.router import router
from app.clients.urja_client import UrjaClient
from app.core.config import Settings
from app.core.exceptions import PortalError
from app.services.meter_service import MeterService

logger = logging.getLogger("urja")
logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


def create_app(
    settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        client = UrjaClient(settings, transport=transport)
        app.state.meters = MeterService(client, settings.export_ttl_seconds)
        try:
            yield
        finally:
            await client.close()

    app = FastAPI(
        title="Flock Energy Meter API",
        version="1.0.0",
        lifespan=lifespan,
        description="Read-only API over Urja Meter Ops. See PROTOCOL.md for verified upstream behavior.",
    )

    @app.exception_handler(PortalError)
    async def portal_error(request: Request, exc: PortalError):
        return JSONResponse(
            status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_error", "message": "Invalid path or query parameters."}},
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content={"error": {"code": code, "message": str(exc.detail)}},
        )

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        started = time.monotonic()
        response = await call_next(request)
        logger.info(
            json.dumps(
                {
                    "event": "request",
                    "method": request.method,
                    "status": response.status_code,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
            )
        )
        return response

    @app.get("/health", tags=["Health"])
    async def health():
        """Process liveness; does not authenticate or probe the upstream portal."""
        return {"status": "ok"}

    app.include_router(router)
    return app


app = create_app()
