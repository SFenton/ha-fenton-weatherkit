"""Monthly call counting and the interval it allows."""

from __future__ import annotations

from datetime import datetime, timezone

from fenton_weatherkit.budget import SPENT_INTERVAL, CallBudget, month_bounds


def at(day: int, hour: int = 0, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=timezone.utc)


def test_plenty_of_budget_keeps_the_configured_interval() -> None:
    budget = CallBudget(400_000)
    budget.record(at(1))
    assert budget.interval(60, at(1)) == 60


def test_a_tight_budget_stretches_the_interval() -> None:
    budget = CallBudget(400_000, {"month": "2026-10", "count": 399_000})
    # 1,000 calls left for 17 days: about one every 24.5 minutes.
    assert budget.interval(60, at(15)) == 1469


def test_a_spent_budget_trickles() -> None:
    budget = CallBudget(1000, {"month": "2026-10", "count": 1000})
    assert budget.interval(60, at(20)) == SPENT_INTERVAL


def test_a_new_month_resets_the_count() -> None:
    budget = CallBudget(400_000, {"month": "2026-09", "count": 400_000})
    assert budget.interval(60, at(1)) == 60
    budget.record(at(1))
    assert budget.as_dict() == {"month": "2026-10", "count": 1}


def test_projection_and_december() -> None:
    budget = CallBudget(400_000, {"month": "2026-10", "count": 14_400})
    assert budget.projected(at(11)) == 44_640  # ten days at once a minute -> 31 days
    start, end = month_bounds(at(5, month=12))
    assert (start.month, end.year, end.month) == (12, 2027, 1)
