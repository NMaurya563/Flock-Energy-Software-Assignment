import asyncio
import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.core.exceptions import PortalError

COOKIE = "__Secure-better-auth.session_token"


class UrjaClient:
    """One connection pool and cookie jar per application; never logs payloads."""

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.http = httpx.AsyncClient(
            base_url=settings.portal_url.rstrip("/"),
            timeout=settings.request_timeout,
            follow_redirects=False,
            transport=transport,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        self.auth_lock = asyncio.Lock()
        self.generation = 0
        self.request_slots = asyncio.Semaphore(4)

    async def close(self) -> None:
        await self.http.aclose()

    async def login(self, generation: int) -> None:
        async with self.auth_lock:
            if self.generation != generation:
                return
            if not self.settings.portal_username or not self.settings.portal_password.get_secret_value():
                raise PortalError("not_configured", "Configure portal credentials in backend/.env.", 503)
            self.http.cookies.clear()
            try:
                response = await self.http.post(
                    "/login",
                    headers={"Origin": self.settings.portal_url.rstrip("/")},
                    data={
                        "email": self.settings.portal_username,
                        "password": self.settings.portal_password.get_secret_value(),
                    },
                )
            except httpx.HTTPError:
                raise PortalError(
                    "authentication_unavailable", "Portal sign-in is unavailable.", 503
                ) from None
            # SvelteKit can return either an HTTP redirect or a serialized action redirect.
            if response.status_code not in (200, 303) or not any(
                c.name == COOKIE for c in self.http.cookies.jar
            ):
                raise PortalError("authentication_failed", "Portal rejected the configured credentials.", 503)
            self.generation += 1

    async def get(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if self.generation == 0:
            await self.login(0)
        refreshed = False
        failures = 0
        while failures < self.settings.upstream_attempts:
            try:
                # Release the slot before authentication or retry: no recursive acquisition.
                async with self.request_slots:
                    generation = self.generation
                    response = await self.http.get(path, params=params, headers=headers)
            except httpx.TimeoutException:
                error = PortalError("upstream_timeout", "Portal request timed out.", 504)
            except httpx.RequestError:
                error = PortalError("upstream_unavailable", "Portal could not be reached.", 503)
            else:
                if response.status_code == 401 or (
                    response.status_code in (302, 303, 307, 308)
                    and response.headers.get("location", "").split("?")[0] == "/login"
                ):
                    if refreshed:
                        raise PortalError(
                            "authentication_failed", "Portal session could not be renewed.", 503
                        )
                    await self.login(generation)
                    refreshed = True
                    continue
                if response.status_code == 403:
                    raise PortalError("upstream_forbidden", "Portal denied access to the requested resource.")
                if response.status_code == 404:
                    raise PortalError("not_found", "Requested resource does not exist.", 404)
                if response.status_code not in (429, 502, 503, 504):
                    if not response.is_success:
                        raise PortalError("upstream_error", "Portal returned an unexpected status.")
                    try:
                        result = response.json()
                        if not isinstance(result, dict) or "data" not in result:
                            raise ValueError()
                        return result
                    except ValueError:
                        raise PortalError(
                            "invalid_upstream_response", "Portal returned an invalid response."
                        ) from None
                error = PortalError("upstream_unavailable", "Portal is temporarily unavailable.", 503)
            failures += 1
            if failures >= self.settings.upstream_attempts:
                raise error
            await asyncio.sleep(min(0.2 * 2 ** (failures - 1), 1))
        raise PortalError("upstream_unavailable", "Portal retry budget exhausted.", 503)

    async def export(self) -> dict[str, Any]:
        key_data = (await self.get("/portal/keys"))["data"]
        secret = key_data.get("signingSecret") if isinstance(key_data, dict) else None
        if not isinstance(secret, str) or not secret:
            raise PortalError("invalid_upstream_response", "Portal signing key is missing.")
        timestamp = str(int(time.time()))
        query = urlencode({"page": 1})
        canonical = "\n".join(("GET", "/portal/export", query, timestamp))
        signature = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        return await self.get(
            "/portal/export", params={"page": 1}, headers={"x-timestamp": timestamp, "x-signature": signature}
        )

    async def transformers(self) -> list[dict[str, Any]]:
        """Follow observed page metadata; reject missing, repeated, or inconsistent pages."""
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        total: int | None = None
        page_size: int | None = None
        for page in range(1, 1001):
            envelope = await self.get("/portal/dts", params={"page": page})
            try:
                count, size = envelope["total"], envelope["pageSize"]
                batch = envelope["data"]
                if (
                    type(count) is not int
                    or count < 0
                    or type(size) is not int
                    or size < 1
                    or type(envelope["page"]) is not int
                    or envelope["page"] != page
                    or not isinstance(batch, list)
                ):
                    raise ValueError()
                if total is None:
                    total = count
                    page_size = size
                if total != count or page_size != size or len(batch) != min(size, max(0, total - len(rows))):
                    raise ValueError()
                for row in batch:
                    code = row["code"]
                    if not isinstance(code, str) or not code.strip() or code in seen:
                        raise ValueError()
                    seen.add(code)
                rows.extend(batch)
                if len(rows) == total:
                    return rows
            except (KeyError, TypeError, ValueError):
                raise PortalError(
                    "invalid_upstream_response", "Transformer pagination was incomplete or malformed."
                ) from None
        raise PortalError("invalid_upstream_response", "Transformer pagination exceeded its safety limit.")
