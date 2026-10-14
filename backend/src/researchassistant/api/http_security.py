"""Central desktop authentication, host and browser-origin boundary."""

from __future__ import annotations

import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp


class LoopbackGuardMiddleware(BaseHTTPMiddleware):
    """Reject non-loopback hosts and unexpected browser origins."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_hosts: tuple[str, ...],
        allowed_origins: tuple[str, ...],
        session_token: str | None = None,
    ) -> None:
        super().__init__(app)
        self._session_token = session_token
        self._allowed_hosts = frozenset(allowed_hosts)
        self._allowed_origins = frozenset(allowed_origins)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if self._session_token is not None and not secrets.compare_digest(
            request.headers.get("authorization", "").encode("utf-8"),
            f"Bearer {self._session_token}".encode(),
        ):
            return JSONResponse(status_code=401, content={"detail": "Desktop session required."})
        if request.url.hostname not in self._allowed_hosts:
            return JSONResponse(status_code=403, content={"detail": "Loopback host required."})
        origin = request.headers.get("origin")
        if origin is not None and origin not in self._allowed_origins:
            return JSONResponse(status_code=403, content={"detail": "Local origin required."})
        return await call_next(request)
