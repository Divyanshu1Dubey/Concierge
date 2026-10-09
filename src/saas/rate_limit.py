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
    """Check and record a rate limit hit using a sliding window counter.
    Returns (allowed, remaining).
    """
    now = time.time()
    cur_win = int(now // window) * window
    prev_win = cur_win - window
    cur_win_str = str(cur_win)
    prev_win_str = str(prev_win)
    pct = max(0.0, min(1.0, (now - cur_win) / float(window)))

    with connect() as c:
        # Cleanup expired entries for this key
        c.execute(
            "DELETE FROM rate_limit_entries WHERE key = ? AND window_start NOT IN (?, ?)",
            (key, cur_win_str, prev_win_str),
        )

        rows = c.execute(
            "SELECT window_start, count FROM rate_limit_entries WHERE key = ? AND window_start IN (?, ?)",
            (key, cur_win_str, prev_win_str),
        ).fetchall()

        counts = {r[0]: r[1] for r in rows}
        cur_count = counts.get(cur_win_str, 0)
        prev_count = counts.get(prev_win_str, 0)

        # Sliding window weighted rate estimate
        estimated = (prev_count * (1.0 - pct)) + cur_count

        if estimated >= limit or cur_count >= limit:
            return False, 0

        if cur_count > 0:
            c.execute(
                "UPDATE rate_limit_entries SET count = count + 1 WHERE key = ? AND window_start = ?",
                (key, cur_win_str),
            )
        else:
            c.execute(
                "INSERT INTO rate_limit_entries (key, window_start, count) VALUES (?, ?, 1)",
                (key, cur_win_str),
            )

    remaining = max(0, int(limit - estimated - 1))
    return True, remaining


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
