"""Stub session calendar for tests that must run without ``exchange_calendars``.

Mon-Fri are sessions except the injected holidays; the close is a fixed UTC hour that
lives only here (test files are not covered by the clock-literal guard, which checks
``scripts/ibkr_*.py`` only).
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone

_FIRST = date(2000, 1, 1)
_LAST = date(2100, 12, 31)


def _range_error(message: str) -> Exception:
    # The error class comes from the loaded domain module, which the test registers
    # in sys.modules under "ibkr_decision".
    return sys.modules["ibkr_decision"].CalendarRangeError(message)


class WeekdayCalendar:
    def __init__(self, holidays=frozenset(), close_utc_hour=20, zone_name="America/New_York"):
        self.holidays = frozenset(holidays)
        self.close_utc_hour = close_utc_hour
        self.zone_name = zone_name

    def _check(self, day: date) -> None:
        if not _FIRST <= day <= _LAST:
            raise _range_error(f"{day} outside the calendar range")

    def is_session(self, day: date) -> bool:
        self._check(day)
        return day.weekday() < 5 and day not in self.holidays

    def sessions_between(self, start: date, end: date) -> tuple[date, ...]:
        if start > end:
            return ()
        self._check(start)
        self._check(end)
        days = (start + timedelta(days=i) for i in range((end - start).days + 1))
        return tuple(d for d in days if self.is_session(d))

    def next_session_after(self, day: date) -> date:
        self._check(day)
        nxt = day + timedelta(days=1)
        while not self.is_session(nxt):
            nxt += timedelta(days=1)
        return nxt

    def session_close_utc(self, day: date) -> datetime:
        if not self.is_session(day):
            raise _range_error(f"{day} is not a session")
        return datetime(day.year, day.month, day.day, self.close_utc_hour, tzinfo=timezone.utc)
