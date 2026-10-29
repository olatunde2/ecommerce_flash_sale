import time
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError


SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_start = now - tonumber(ARGV[2])
local request_limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)
local request_count = redis.call('ZCARD', key)
if request_count >= request_limit then
    return 0
end

redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, math.ceil(tonumber(ARGV[2]) / 1000))
return 1
"""


async def enforce_rate_limit(request: Request) -> JSONResponse | None:
    if not request.url.path.startswith("/api/"):
        return None

    client = request.client
    client_id = client.host if client is not None else "unknown"
    settings = request.app.state.settings
    now_ms = int(time.time() * 1000)
    member = f"{now_ms}:{uuid4().hex}"

    try:
        allowed = await request.app.state.redis.eval(
            SLIDING_WINDOW_SCRIPT,
            1,
            f"rate-limit:{client_id}",
            now_ms,
            settings.rate_limit_window_seconds * 1000,
            settings.rate_limit_requests,
            member,
        )
    except RedisError:
        return JSONResponse(
            status_code=503,
            content={"detail": "Rate limiting service is unavailable"},
        )

    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(settings.rate_limit_window_seconds)},
        )
    return None
