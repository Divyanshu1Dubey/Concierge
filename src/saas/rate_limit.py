"""Rate limiting for public API endpoints."""

from __future__ import annotations

import time
from functools import wraps
from typing import Callable

from fastapi import HTTPException, status

from saas.database import connect

# Default: 60 requests per minute per key
DEFAULT_LIMIT = 60
DEFAULT_WINDOW = 60  # seconds


def _rate_limit_key(prefix: str, identifier: str) -> str:
    return f"rl:{prefix}:{identifier}"


def check_rate_limit(key: str, limit: int = DEFAULT_LIMIT, window: int = DEFAULT_WINDOW) -> tuple[bool, int]:
    """Check and record a rate limit hit.
    Returns (allowed, remaining).
    """
    now = time.time()
    window_start = str(int(now // window) * window)

    with connect() as c:
        row = c.execute(
            "SELECT count FROM rate_limit_entries WHERE key = ? AND window_start = ?",
            (key, window_start),
        ).fetchone()

        if row and row[0] >= limit:
            return False, 0

        if row:
            c.execute(
                "UPDATE rate_limit_entries SET count = count + 1 WHERE key = ? AND window_start = ?",
                (key, window_start),
            )
        else:
            c.execute(
                "INSERT INTO rate_limit_entries (key, window_start, count) VALUES (?, ?, 1)",
                (key, window_start),
            )

    return True, max(0, limit - (row[0] + 1 if row else 0))


def rate_limit(prefix: str, limit: int = DEFAULT_LIMIT, window: int = DEFAULT_WINDOW):
    """Decorator for FastAPI endpoints."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract identifier from kwargs or use IP-like fallback
            identifier = kwargs.get("client_key") or kwargs.get("authorization") or "anon"
            key = _rate_limit_key(prefix, str(identifier))
            allowed, remaining = check_rate_limit(key, limit, window)
            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later.",
                    headers={"Retry-After": str(window)},
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator
