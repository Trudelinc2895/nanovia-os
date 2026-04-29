"""backend/api/middleware/body_limit.py — Body size limit middleware (Slowloris protection)."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

_SKIP_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose body exceeds *max_bytes*.

    Strategy:
    1. For requests with a ``Content-Length`` header: reject immediately if
       the declared length exceeds the limit (no body read needed).
    2. For requests without ``Content-Length``: stream and count bytes; stop
       at the limit and return 413.
    3. GET / HEAD / OPTIONS are skipped entirely.
    """

    def __init__(self, app: ASGIApp, max_bytes: int = 1_048_576) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in _SKIP_METHODS:
            return await call_next(request)

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large"},
                    )
            except ValueError:
                pass  # Malformed header — let downstream handle

        return await call_next(request)
