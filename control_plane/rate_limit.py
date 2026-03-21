import time
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from collections import defaultdict
from threading import Lock

CALLS_PER_MINUTE = 60


class RateLimiter:
    def __init__(self, calls_per_minute: int = CALLS_PER_MINUTE):
        self.calls_per_minute = calls_per_minute
        self.allowance_per_second = calls_per_minute / 60.0
        self.clients: dict = defaultdict(lambda: {
            "tokens": float(calls_per_minute),
            "last_update": time.time(),
        })
        self.lock = Lock()

    def is_allowed(self, client_id: str) -> bool:
        with self.lock:
            now = time.time()
            client = self.clients[client_id]
            time_passed = now - client["last_update"]
            client["tokens"] = min(
                float(self.calls_per_minute),
                client["tokens"] + time_passed * self.allowance_per_second,
            )
            client["last_update"] = now
            if client["tokens"] >= 1.0:
                client["tokens"] -= 1.0
                return True
            return False


# Two separate limiters so that API-key clients get a higher quota than
# anonymous IP-based clients. This way developers are not penalised by
# background UI traffic from the dashboard.
_ip_limiter  = RateLimiter(calls_per_minute=60)
_key_limiter = RateLimiter(calls_per_minute=300)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only limit /v1 API traffic; skip health checks / static files
        if request.url.path.startswith("/v1"):
            api_key = request.headers.get("X-API-Key")

            if api_key:
                # Per-API-key limiting: higher quota, scoped to the key
                client_id = f"apikey:{api_key}"
                limiter = _key_limiter
            else:
                # Per-IP fallback for unauthenticated requests
                forwarded = request.headers.get("X-Forwarded-For")
                if forwarded:
                    client_id = forwarded.split(",")[0].strip()
                else:
                    client_id = request.client.host if request.client else "unknown"
                limiter = _ip_limiter

            if not limiter.is_allowed(client_id):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too Many Requests. Please slow down."},
                    headers={"Retry-After": "1"},
                )

        return await call_next(request)
