"""In-memory per-IP sliding-window rate limiter for POST /auth/register
(FR-014, SC-006, ADR-005).

ponytail: process-local dict, single-instance only — correct for a single
deployed instance; if the app scales to multiple replicas, each instance
counts its own IPs and the effective limit multiplies by replica count.
Upgrade path: move the counter to a shared store (Redis, INCR+EXPIRE) behind
the same dependency signature.
"""

from collections import defaultdict
from functools import lru_cache
from time import monotonic

from fastapi import Depends, HTTPException, Request, status

from user_api.config import Settings, get_settings


class SlidingWindowIpRateLimiter:
    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, client_ip: str) -> None:
        now = monotonic()
        window_start = now - self._window_seconds
        # Opportunistic full sweep on every call, not just this IP's entry:
        # pruning only the current key would still leave one dict entry per
        # distinct IP forever (an IP checked once and never seen again keeps
        # its stale list around, since nothing else ever touches that key).
        # A cheap sweep across all entries each call bounds total memory to
        # "distinct IPs active within the last window", not "distinct IPs
        # ever seen" — acceptable cost for a small in-memory limiter used
        # only on POST /auth/register (not a hot path).
        self._prune_stale(window_start)
        hits = self._hits[client_ip]
        if len(hits) >= self._max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many registration attempts, please try again later",
            )
        hits.append(now)

    def _prune_stale(self, window_start: float) -> None:
        empty_ips = []
        for ip, hits in self._hits.items():
            hits[:] = [t for t in hits if t > window_start]
            if not hits:
                empty_ips.append(ip)
        for ip in empty_ips:
            del self._hits[ip]


@lru_cache
def _limiter(max_requests: int, window_seconds: float) -> SlidingWindowIpRateLimiter:
    return SlidingWindowIpRateLimiter(max_requests, window_seconds)


def enforce_register_rate_limit(
    request: Request, settings: Settings = Depends(get_settings)
) -> None:
    max_requests, window_seconds = settings.auth_register_rate_limit_parsed
    client_ip = request.client.host if request.client else "unknown"
    _limiter(max_requests, window_seconds).check(client_ip)
