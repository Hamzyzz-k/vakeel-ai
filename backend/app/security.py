"""Small deployment-security middleware with no external state dependency."""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from starlette.responses import JSONResponse

logger = logging.getLogger("uvicorn.error")


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


def client_ip(scope, trusted_proxy_hops: int) -> str:
    """The address to rate-limit on.

    Behind a hosting platform's proxy the socket peer is the proxy itself,
    so every user would share one bucket. Each trusted proxy appends the
    address it received the connection from to X-Forwarded-For, so the
    entry `trusted_proxy_hops` from the right is the client as seen by the
    outermost trusted proxy. Entries further left were written by the
    client and are never trusted -- uvicorn's FORWARDED_ALLOW_IPS="*" takes
    the leftmost one, which lets a client pick its own bucket.
    """
    client = scope.get("client")
    peer = client[0] if client else "unknown"
    if trusted_proxy_hops <= 0:
        return peer
    forwarded = ",".join(
        value.decode("latin-1") for name, value in scope.get("headers", []) if name == b"x-forwarded-for"
    )
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    if len(hops) < trusted_proxy_hops:
        return peer
    return hops[-trusted_proxy_hops]


class RateLimitMiddleware:
    """Bound expensive POST endpoints by client address and time window.

    Suitable for a single hosted process. A multi-instance deployment should
    replace it with a shared Redis/API-gateway limiter.
    """

    LIMITED_PATHS = frozenset({"/api/v1/chat", "/api/v1/chat/stream", "/api/v1/documents/upload"})
    _SWEEP_ABOVE = 1024

    def __init__(self, app, max_requests: int, window_seconds: int, trusted_proxy_hops: int = 0):
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.trusted_proxy_hops = trusted_proxy_hops
        self._logged_forwarding = False
        self._last_sweep = float("-inf")
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] not in self.LIMITED_PATHS:
            await self.app(scope, receive, send)
            return

        if not self._logged_forwarding:
            # One line, no addresses: lets the operator read the platform's
            # real proxy hop count from logs to set TRUSTED_PROXY_HOPS.
            self._logged_forwarding = True
            forwarded = b",".join(v for k, v in scope.get("headers", []) if k == b"x-forwarded-for")
            entries = len([hop for hop in forwarded.split(b",") if hop.strip()]) if forwarded else 0
            logger.info(
                "First rate-limited request: X-Forwarded-For has %d entr%s; TRUSTED_PROXY_HOPS=%d",
                entries, "y" if entries == 1 else "ies", self.trusted_proxy_hops,
            )

        key = f"{client_ip(scope, self.trusted_proxy_hops)}:{scope['path']}"
        now = time.monotonic()
        with self._lock:
            cutoff = now - self.window_seconds
            # Now that buckets are per real client, drop idle ones so a
            # long-running process doesn't keep every address it ever saw.
            # At most once per window: sweeping on every request would make
            # each POST an O(clients) scan under the lock during a flood.
            if len(self._requests) > self._SWEEP_ABOVE and now - self._last_sweep >= self.window_seconds:
                self._last_sweep = now
                for stale in [k for k, b in self._requests.items() if not b or b[-1] <= cutoff]:
                    del self._requests[stale]
            bucket = self._requests[key]
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


class DailyQuotaMiddleware:
    """Cap chat requests per client and in total per UTC day.

    The per-minute limiter alone still lets one address send ~1,200 chats an
    hour, and the free LLM tiers behind /chat run out after roughly 50
    answers a day (Groq caps gpt-oss-120b at 200K tokens/day). Without a
    daily cap one script can use up everyone's quota in minutes; with one,
    users get a clear "limit reached" message instead of failed answers.
    A limit of 0 disables that cap.
    """

    LIMITED_PATHS = frozenset({"/api/v1/chat", "/api/v1/chat/stream"})

    def __init__(self, app, per_client: int, total: int, trusted_proxy_hops: int = 0, clock=None):
        self.app = app
        self.per_client = per_client
        self.total = total
        self.trusted_proxy_hops = trusted_proxy_hops
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._day = None
        self._total_used = 0
        self._client_used: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http" or scope["method"] != "POST" or scope["path"] not in self.LIMITED_PATHS
            or (self.per_client <= 0 and self.total <= 0)
        ):
            await self.app(scope, receive, send)
            return

        now = self._clock()
        client = client_ip(scope, self.trusted_proxy_hops)
        with self._lock:
            if now.date() != self._day:
                self._day = now.date()
                self._total_used = 0
                self._client_used.clear()
            if self.total > 0 and self._total_used >= self.total:
                detail = "Vakeel AI has reached today's free usage limit. It resets at midnight UTC."
            elif self.per_client > 0 and self._client_used[client] >= self.per_client:
                detail = f"You've reached today's limit of {self.per_client} questions. It resets at midnight UTC."
            else:
                detail = None
                self._total_used += 1
                self._client_used[client] += 1

        if detail is not None:
            midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=now.tzinfo)
            response = JSONResponse(
                {"detail": detail},
                status_code=429,
                headers={"Retry-After": str(max(1, int((midnight - now).total_seconds())))},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
