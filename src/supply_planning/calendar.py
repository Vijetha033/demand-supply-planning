"""ISO-week planning calendar helpers.

Week index 0 is ISO week 01 of the plan year.  The planning *as-of* date is the
Monday of week 01: everything strictly before it is history, everything on or
after it is the planning horizon.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd


def week_start(plan_year: int, index: int) -> date:
    return date.fromisocalendar(plan_year, 1, 1) + timedelta(weeks=int(index))


def as_of_date(plan_year: int) -> date:
    return week_start(plan_year, 0)


def week_id_for_date(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}W{w:02d}"


def week_id(plan_year: int, index: int) -> str:
    return week_id_for_date(week_start(plan_year, index))


def week_ids(plan_year: int, n_weeks: int) -> list[str]:
    return [week_id(plan_year, i) for i in range(n_weeks)]


def week_index_of(dates: pd.Series | list, plan_year: int) -> np.ndarray:
    """Vectorised: ISO date strings/dates -> integer week index (may be negative)."""
    d = pd.to_datetime(pd.Series(dates))
    base = pd.Timestamp(as_of_date(plan_year))
    return ((d - base).dt.days // 7).to_numpy()


def iso(d: date) -> str:
    return d.isoformat()


def add_days(d: str | date, n: int) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return (d + timedelta(days=int(n))).isoformat()
