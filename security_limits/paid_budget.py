"""
Per-user daily budgets for authenticated paid generation.

Debit by cost units (e.g. number of images), not merely request count.

In-memory only — document Redis follow-up for multi-instance.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date
from typing import Dict

from fastapi import HTTPException

DEFAULT_USER_DAILY_LIMIT = 100


@dataclass
class _UserCounters:
    day: date
    count: int = 0


class PaidBudgetStore:
    def __init__(self, daily_limit: int = DEFAULT_USER_DAILY_LIMIT) -> None:
        self.daily_limit = daily_limit
        self._lock = threading.Lock()
        self._by_user: Dict[str, _UserCounters] = {}

    def reset(self) -> None:
        with self._lock:
            self._by_user.clear()

    def consume(self, user_id: str, units: int = 1) -> None:
        if units < 1:
            units = 1
        with self._lock:
            today = date.today()
            bucket = self._by_user.get(user_id)
            if bucket is None or bucket.day != today:
                bucket = _UserCounters(day=today)
                self._by_user[user_id] = bucket
            if bucket.count + units > self.daily_limit:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Daily generation budget exceeded ({self.daily_limit} units/day). "
                        "Try again tomorrow."
                    ),
                )
            bucket.count += units


paid_budget_store = PaidBudgetStore()


async def require_paid_budget(user_id: str, units: int = 1) -> None:
    paid_budget_store.consume(user_id, units=units)
