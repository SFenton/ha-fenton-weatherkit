"""Monthly call counting, so a short interval or a bug can't run past the allowance.

Apple bills per calendar month of the membership; this counts by UTC calendar month, which is close enough
to keep well clear of the 500,000 included calls when the budget is left at its default of 400,000.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

# When the budget is spent, keep a trickle of updates rather than going dark.
SPENT_INTERVAL = 3600


def month_key(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m")


def month_bounds(now: datetime) -> tuple[datetime, datetime]:
    utc = now.astimezone(timezone.utc)
    start = utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, end


class CallBudget:
    """Counts calls this month and stretches the polling interval to stay under ``budget``."""

    def __init__(self, budget: int, stored: dict[str, Any] | None = None) -> None:
        self.budget = budget
        self.month = str((stored or {}).get("month") or "")
        self.count = int((stored or {}).get("count") or 0)

    def _roll(self, now: datetime) -> None:
        if self.month != month_key(now):
            self.month, self.count = month_key(now), 0

    def record(self, now: datetime) -> None:
        self._roll(now)
        self.count += 1

    def interval(self, configured: float, now: datetime) -> float:
        """Seconds to wait before the next call: the configured interval, or longer if the budget needs it."""
        self._roll(now)
        remaining = self.budget - self.count
        if remaining <= 0:
            return max(configured, SPENT_INTERVAL)
        _, end = month_bounds(now)
        return max(configured, math.ceil((end - now).total_seconds() / remaining))

    def projected(self, now: datetime) -> int:
        """Calls by month end at this month's pace so far."""
        self._roll(now)
        start, end = month_bounds(now)
        elapsed = max((now - start).total_seconds(), 60.0)
        return round(self.count * (end - start).total_seconds() / elapsed)

    def as_dict(self) -> dict[str, Any]:
        return {"month": self.month, "count": self.count}
