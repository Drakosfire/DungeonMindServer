"""
Hard quotas for the short public demo allowlist.

Trusted client identity:
- Prefer X-Real-IP (set by nginx from $remote_addr after stripping client
  X-Forwarded-For). Never trust the first X-Forwarded-For hop.
- When TRUST_PROXY is false (local tests), use request.client.host only.

Global limit: 20 demo requests / identity / calendar day across ALL demo
families combined (not 20 per family).

Authenticated callers on demo routes are keyed by user_id when present in
the OAuth session, not by IP.

In-memory only — Redis/Cloudflare rate limiting is required for multi-instance.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from datetime import date
from typing import Dict, Optional

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

DEFAULT_DAILY_LIMIT = 20
DEFAULT_CONCURRENCY = 2

FAMILY_STATBLOCK_GENERATE = "statblock_generate"
FAMILY_CARD_GENERATE_ITEM = "card_generate_item"
FAMILY_RULESLAWYER_QUERY = "ruleslawyer_query"
FAMILY_PCG_PREFERENCES = "pcg_preferences"

# Single global family key — all demo routes share one daily bucket
GLOBAL_DEMO_FAMILY = "demo_global"


@dataclass
class _IdentityCounters:
    day: date
    count: int = 0
    in_flight: int = 0


class DemoQuotaStore:
    """Thread-safe in-memory identity quota tracker (global daily limit)."""

    def __init__(
        self,
        daily_limit: int = DEFAULT_DAILY_LIMIT,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> None:
        self.daily_limit = daily_limit
        self.concurrency = concurrency
        self._lock = threading.Lock()
        self._by_id: Dict[str, _IdentityCounters] = {}

    def reset(self) -> None:
        with self._lock:
            self._by_id.clear()

    def _bucket(self, identity: str) -> _IdentityCounters:
        today = date.today()
        bucket = self._by_id.get(identity)
        if bucket is None or bucket.day != today:
            bucket = _IdentityCounters(day=today)
            self._by_id[identity] = bucket
        return bucket

    def admit(self, identity: str, family: str = GLOBAL_DEMO_FAMILY) -> None:
        """Increment global daily count; family is logged only."""
        with self._lock:
            bucket = self._bucket(identity)
            if bucket.count >= self.daily_limit:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Anonymous demo quota exceeded ({self.daily_limit}/day "
                        "across all demo endpoints). Sign in for higher limits."
                    ),
                )
            if bucket.in_flight >= self.concurrency:
                raise HTTPException(
                    status_code=429,
                    detail="Too many concurrent anonymous demo requests. Try again shortly.",
                )
            bucket.count += 1
            bucket.in_flight += 1
            logger.debug("Demo quota admit identity=%s family=%s used=%s", identity, family, bucket.count)

    def release(self, identity: str) -> None:
        with self._lock:
            bucket = self._by_id.get(identity)
            if bucket and bucket.in_flight > 0:
                bucket.in_flight -= 1


demo_quota_store = DemoQuotaStore()


def trust_proxy_enabled() -> bool:
    return os.getenv("TRUST_PROXY", "true").lower() == "true"


def client_ip(request: Request) -> str:
    """
    Canonical client address for quota keys.

    When TRUST_PROXY=true (production behind nginx): use X-Real-IP only.
    Nginx must set `proxy_set_header X-Real-IP $remote_addr` and must NOT
    forward client-supplied X-Real-IP / must reset X-Forwarded-For.

    When TRUST_PROXY=false: use the direct TCP peer only.
    Never use the first X-Forwarded-For hop (spoofable).
    """
    if trust_proxy_enabled():
        real_ip = (request.headers.get("x-real-ip") or "").strip()
        if real_ip:
            return real_ip
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def demo_quota_identity(request: Request) -> str:
    """Prefer authenticated user id from OAuth session; else trusted IP."""
    try:
        user = request.session.get("user") if hasattr(request, "session") else None
        if isinstance(user, dict) and user.get("sub"):
            return f"user:{user['sub']}"
    except Exception:
        pass
    return f"ip:{client_ip(request)}"


class DemoQuotaDependency:
    """FastAPI dependency: admit on entry; middleware releases in-flight."""

    def __init__(self, family: str) -> None:
        self.family = family

    async def __call__(self, request: Request) -> None:
        identity = demo_quota_identity(request)
        demo_quota_store.admit(identity, self.family)
        request.state.demo_quota_ip = identity  # middleware release key


def _make_demo_quota_dep(family: str):
    """
    Plain async function dependencies (not class __call__).

    FastAPI 0.115+ can mis-parse class-based __call__(self, request) and treat
    ``request`` as a required query parameter (HTTP 422).
    """

    async def _dep(request: Request) -> None:
        identity = demo_quota_identity(request)
        demo_quota_store.admit(identity, family)
        request.state.demo_quota_ip = identity

    return _dep


require_demo_quota_statblock = _make_demo_quota_dep(FAMILY_STATBLOCK_GENERATE)
require_demo_quota_card_item = _make_demo_quota_dep(FAMILY_CARD_GENERATE_ITEM)
require_demo_quota_ruleslawyer = _make_demo_quota_dep(FAMILY_RULESLAWYER_QUERY)
require_demo_quota_pcg_preferences = _make_demo_quota_dep(FAMILY_PCG_PREFERENCES)
