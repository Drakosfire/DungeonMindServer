"""
Hard IP/day quotas for the short public demo allowlist.

In-memory only — suitable for a single VPS. Multi-instance deployments need a
shared store (Redis/Firestore) as a follow-up.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import date
from typing import Dict

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

DEFAULT_DAILY_LIMIT = 20
DEFAULT_CONCURRENCY = 2

FAMILY_STATBLOCK_GENERATE = "statblock_generate"
FAMILY_CARD_GENERATE_ITEM = "card_generate_item"
FAMILY_RULESLAWYER_QUERY = "ruleslawyer_query"
FAMILY_PCG_PREFERENCES = "pcg_preferences"


@dataclass
class _IpCounters:
    day: date
    counts: Dict[str, int] = field(default_factory=dict)
    in_flight: int = 0


class DemoQuotaStore:
    """Thread-safe in-memory IP quota tracker."""

    def __init__(
        self,
        daily_limit: int = DEFAULT_DAILY_LIMIT,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> None:
        self.daily_limit = daily_limit
        self.concurrency = concurrency
        self._lock = threading.Lock()
        self._by_ip: Dict[str, _IpCounters] = {}

    def reset(self) -> None:
        with self._lock:
            self._by_ip.clear()

    def _bucket(self, ip: str) -> _IpCounters:
        today = date.today()
        bucket = self._by_ip.get(ip)
        if bucket is None or bucket.day != today:
            bucket = _IpCounters(day=today)
            self._by_ip[ip] = bucket
        return bucket

    def admit(self, ip: str, family: str) -> None:
        """Increment daily count and in-flight; raise 429 if over limit."""
        with self._lock:
            bucket = self._bucket(ip)
            used = bucket.counts.get(family, 0)
            if used >= self.daily_limit:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Anonymous demo quota exceeded ({self.daily_limit}/day "
                        f"for {family}). Sign in for higher limits."
                    ),
                )
            if bucket.in_flight >= self.concurrency:
                raise HTTPException(
                    status_code=429,
                    detail="Too many concurrent anonymous demo requests. Try again shortly.",
                )
            bucket.counts[family] = used + 1
            bucket.in_flight += 1

    def release(self, ip: str) -> None:
        with self._lock:
            bucket = self._by_ip.get(ip)
            if bucket and bucket.in_flight > 0:
                bucket.in_flight -= 1


demo_quota_store = DemoQuotaStore()


def client_ip(request: Request) -> str:
    """Prefer first X-Forwarded-For hop (nginx), else direct client host."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


class DemoQuotaDependency:
    """FastAPI dependency: admit on entry, release in-flight after response."""

    def __init__(self, family: str) -> None:
        self.family = family

    async def __call__(self, request: Request) -> None:
        ip = client_ip(request)
        demo_quota_store.admit(ip, self.family)
        request.state.demo_quota_ip = ip


require_demo_quota_statblock = DemoQuotaDependency(FAMILY_STATBLOCK_GENERATE)
require_demo_quota_card_item = DemoQuotaDependency(FAMILY_CARD_GENERATE_ITEM)
require_demo_quota_ruleslawyer = DemoQuotaDependency(FAMILY_RULESLAWYER_QUERY)
require_demo_quota_pcg_preferences = DemoQuotaDependency(FAMILY_PCG_PREFERENCES)
