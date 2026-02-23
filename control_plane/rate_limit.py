import time
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from collections import defaultdict
from threading import Lock

# Simple in-memory rate limiter
# In a real distributed system, use Redis (e.g., redis-py with Lua scripts)
class RateLimiter:
    def __init__(self, calls_per_minute: int = 60):
        self.calls_per_minute = calls_per_minute
        self.allowance_per_second = calls_per_minute / 60.0
        self.clients = defaultdict(lambda: {"tokens": self.calls_per_minute, "last_update": time.time()})
        self.lock = Lock()

    def is_allowed(self, client_id: str) -> bool:
        with self.lock:
            now = time.time()
            client = self.clients[client_id]
            
            # Replenish tokens based on time passed
            time_passed = now - client["last_update"]
            client["tokens"] = min(self.calls_per_minute, client["tokens"] + time_passed * self.allowance_per_second)
            client["last_update"] = now

            if client["tokens"] >= 1.0:
                client["tokens"] -= 1.0
                return True
            return False


# Global instance: 60 requests per minute by default
limiter = RateLimiter(calls_per_minute=60)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        
        # Don't limit the demo or HLS files, only the API
        if request.url.path.startswith("/v1") and request.url.path != "/v1/metrics":
            # Use X-Forwarded-For if available, fallback to client host
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                client_id = forwarded.split(',')[0].strip()
            else:
                client_id = request.client.host if request.client else "unknown"

            # Check if this specific API key has a different rate limit (optional expansion)
            # api_key = request.headers.get("X-API-Key")
            # if api_key:
            #    client_id = f"apikey:{api_key}"

            if not limiter.is_allowed(client_id):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too Many Requests. Please slow down."},
                    headers={"Retry-After": "1"}
                )

        response = await call_next(request)
        return response
