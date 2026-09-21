from collections import defaultdict, deque
from time import time

from fastapi import HTTPException, Request, status

from app.config import settings

_hits: dict[str, deque[float]] = defaultdict(deque)


def check_auth_rate(request: Request, limit: int = 60, window_seconds: int = 60) -> None:
    if settings.environment.lower() == "test":
        return
    client = request.client.host if request.client else "unknown"
    now = time()
    bucket = _hits[client]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many authentication attempts")
    bucket.append(now)
