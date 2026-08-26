"""Small deployment-security middleware with no external state dependency."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from starlette.responses import JSONResponse


class SecurityHeadersMiddleware:
    """Attach conservative headers to every API response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"cross-origin-resource-policy", b"same-site"),
                    (b"cache-control", b"no-store"),
                ])
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RateLimitMiddleware:
    """Bound expensive POST endpoints by client address and time window.

    Suitable for a single hosted process. A multi-instance deployment should
    replace it with a shared Redis/API-gateway limiter.
    """

    LIMITED_PATHS = frozenset({"/api/v1/chat", "/api/v1/documents/upload"})

    def __init__(self, app, max_requests: int, window_seconds: int):
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] not in self.LIMITED_PATHS:
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_host = client[0] if client else "unknown"
        key = f"{client_host}:{scope['path']}"
        now = time.monotonic()
        with self._lock:
            bucket = self._requests[key]
            cutoff = now - self.window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                retry_after = max(1, int(self.window_seconds - (now - bucket[0])))
                response = JSONResponse(
                    {"detail": "Too many requests. Try again shortly."},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
                await response(scope, receive, send)
                return
            bucket.append(now)

        await self.app(scope, receive, send)
