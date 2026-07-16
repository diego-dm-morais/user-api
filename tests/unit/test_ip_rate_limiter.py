"""SC-006/FR-014: exercises SlidingWindowIpRateLimiter directly (no HTTP
layer, no shared state across test files — see tests/db_conftest.py)."""

from time import monotonic
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from user_api.adapters.inbound.http.ip_rate_limiter import SlidingWindowIpRateLimiter


def test_requests_under_limit_are_allowed() -> None:
    limiter = SlidingWindowIpRateLimiter(max_requests=3, window_seconds=60)

    for _ in range(3):
        limiter.check("1.2.3.4")  # must not raise


def test_requests_over_limit_raise_429() -> None:
    limiter = SlidingWindowIpRateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        limiter.check("1.2.3.4")

    with pytest.raises(HTTPException) as exc_info:
        limiter.check("1.2.3.4")

    assert exc_info.value.status_code == 429


def test_limit_is_tracked_independently_per_ip() -> None:
    limiter = SlidingWindowIpRateLimiter(max_requests=1, window_seconds=60)

    limiter.check("1.1.1.1")  # must not raise
    limiter.check("2.2.2.2")  # different IP, must not raise

    with pytest.raises(HTTPException):
        limiter.check("1.1.1.1")


def test_expired_ip_entries_are_pruned_from_memory() -> None:
    """Regression: stale per-IP entries must not accumulate forever. A
    single check() call opportunistically sweeps every IP's entry, not just
    the caller's, so IPs that were checked once and never returned don't
    keep their dict entry alive indefinitely (unbounded memory growth)."""
    limiter = SlidingWindowIpRateLimiter(max_requests=5, window_seconds=60)
    start = monotonic()

    with patch("user_api.adapters.inbound.http.ip_rate_limiter.monotonic", return_value=start):
        for i in range(50):
            limiter.check(f"10.0.0.{i}")
    assert len(limiter._hits) == 50

    with patch(
        "user_api.adapters.inbound.http.ip_rate_limiter.monotonic",
        return_value=start + 61,
    ):
        limiter.check("10.0.0.200")  # any single check() sweeps all stale entries

    assert len(limiter._hits) == 1  # only the freshly-touched IP remains
