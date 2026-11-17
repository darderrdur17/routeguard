"""Shared timezone-aware "today" helpers.

The retrospective date bound must use the origin airport's local calendar
date, and that logic is needed both at Pydantic validation time (models.py)
and during service orchestration (service.py), so it lives here once.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def airport_local_today(timezone_name: str) -> date:
    """Return the local calendar date right now for one IANA timezone name.

    Unknown or invalid zone names fall back to the UTC calendar date so the
    date bound stays conservative instead of raising.
    """
    instant = datetime.now(timezone.utc)
    try:
        return instant.astimezone(ZoneInfo(timezone_name)).date()
    except (ZoneInfoNotFoundError, ValueError):
        return instant.date()
