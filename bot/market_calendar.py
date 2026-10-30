"""Market calendar: US (NYSE / Nasdaq) holidays and session helpers for US and UK symbols.

Holidays and early closes are computed from the exchanges' published rules,
so no yearly maintenance is needed:

* New Year's Day, Juneteenth (from 2022), Independence Day, Christmas:
  Saturday -> observed the previous Friday, Sunday -> observed the next Monday.
  (Exception: when New Year's Day falls on a Saturday, the exchanges do NOT
  close on the preceding Friday.)
* Martin Luther King Jr. Day: 3rd Monday of January.
* Presidents' Day: 3rd Monday of February.
* Good Friday: two days before Easter Sunday.
* Memorial Day: last Monday of May.
* Labor Day: 1st Monday of September.
* Thanksgiving: 4th Thursday of November.

Early closes (13:00 ET): the day after Thanksgiving, December 24 and
July 3 when they fall on a regular trading weekday.

Ad-hoc closures (e.g. national days of mourning, severe weather) cannot be
predicted and are not modelled.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import FrozenSet, Optional, Tuple

REGULAR_OPEN_MIN = 9 * 60 + 30
REGULAR_CLOSE_MIN = 16 * 60
EARLY_CLOSE_MIN = 13 * 60


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the n-th given weekday (Mon=0) of a month."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    nxt = date(year + (month == 12), (month % 12) + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _easter(year: int) -> date:
    """Western (Gregorian) Easter Sunday via the anonymous algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month = (h + el - 7 * m + 114) // 31
    day = ((h + el - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _observed(d: date, allow_friday: bool = True) -> date | None:
    if d.weekday() == 5:  # Saturday
        return d - timedelta(days=1) if allow_friday else None
    if d.weekday() == 6:  # Sunday
        return d + timedelta(days=1)
    return d


@lru_cache(maxsize=32)
def us_market_holidays(year: int) -> FrozenSet[date]:
    """Full-day US market closures that fall inside `year`."""
    days: list[date | None] = [
        # New Year's Day: not observed on the prior Friday if Jan 1 is a Saturday
        _observed(date(year, 1, 1), allow_friday=False),
        _nth_weekday(year, 1, 0, 3),  # MLK Day
        _nth_weekday(year, 2, 0, 3),  # Presidents' Day
        _easter(year) - timedelta(days=2),  # Good Friday
        _last_weekday(year, 5, 0),  # Memorial Day
        _observed(date(year, 7, 4)),  # Independence Day
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed(date(year, 12, 25)),  # Christmas
    ]
    if year >= 2022:
        days.append(_observed(date(year, 6, 19)))  # Juneteenth
    return frozenset(d for d in days if d is not None and d.year == year)


def is_market_holiday(d: date) -> bool:
    """True if `d` is a full-day US market closure (weekends excluded)."""
    # A Jan 1 observed holiday can land in the previous year's calendar
    # (e.g. Dec 31) only for Fri-observed rules, which we deliberately skip.
    return d in us_market_holidays(d.year)


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and not is_market_holiday(d)


def is_early_close(d: date) -> bool:
    """True on 13:00 ET early-close days."""
    if not is_trading_day(d):
        return False
    thanksgiving = _nth_weekday(d.year, 11, 3, 4)
    if d == thanksgiving + timedelta(days=1):
        return True
    return (d.month, d.day) in {(12, 24), (7, 3)}


def market_close_minute(d: date) -> int:
    """Regular-session close in minutes after midnight ET."""
    return EARLY_CLOSE_MIN if is_early_close(d) else REGULAR_CLOSE_MIN


def holiday_name(d: date) -> str:
    """Best-effort label for a closure date (for dashboard messages)."""
    if d.weekday() >= 5:
        return "Weekend"
    if not is_market_holiday(d):
        return ""
    y = d.year
    names = [
        (_observed(date(y, 1, 1), allow_friday=False), "New Year's Day"),
        (_nth_weekday(y, 1, 0, 3), "Martin Luther King Jr. Day"),
        (_nth_weekday(y, 2, 0, 3), "Presidents' Day"),
        (_easter(y) - timedelta(days=2), "Good Friday"),
        (_last_weekday(y, 5, 0), "Memorial Day"),
        (_observed(date(y, 6, 19)), "Juneteenth"),
        (_observed(date(y, 7, 4)), "Independence Day"),
        (_nth_weekday(y, 9, 0, 1), "Labor Day"),
        (_nth_weekday(y, 11, 3, 4), "Thanksgiving"),
        (_observed(date(y, 12, 25)), "Christmas Day"),
    ]
    for hd, name in names:
        if hd == d:
            return name
    return "Market Holiday"


def next_trading_day(d: date) -> date:
    nxt = d + timedelta(days=1)
    while not is_trading_day(nxt):
        nxt += timedelta(days=1)
    return nxt


# -----------------------------------------------------------------------------
# Exchange sessions per symbol (shared by the live bot and the backtester)
# -----------------------------------------------------------------------------
# `_UK_EQ` symbols trade on the London Stock Exchange (08:00-16:30 Europe/London,
# Mon-Fri; UK bank holidays are not modelled). Everything else uses the US
# calendar above (09:30-16:00 America/New_York, with holidays and early closes).

UK_OPEN_MIN = 8 * 60
UK_CLOSE_MIN = 16 * 60 + 30


def is_uk_symbol(symbol: str) -> bool:
    return str(symbol).endswith("_UK_EQ")


def _exchange_local(symbol: str, when: datetime) -> datetime:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/London") if is_uk_symbol(symbol) else ZoneInfo("America/New_York")
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(tz)


def session_minutes(symbol: str, when: datetime) -> Optional[Tuple[int, int, int]]:
    """Return `(now_min, open_min, close_min)` in exchange-local minutes, or None if closed all day."""
    local = _exchange_local(symbol, when)
    d = local.date()
    if is_uk_symbol(symbol):
        if d.weekday() >= 5:
            return None
        open_min, close_min = UK_OPEN_MIN, UK_CLOSE_MIN
    else:
        if not is_trading_day(d):
            return None
        open_min, close_min = REGULAR_OPEN_MIN, market_close_minute(d)
    return local.hour * 60 + local.minute, open_min, close_min


def is_session_open(symbol: str, when: datetime) -> bool:
    mins = session_minutes(symbol, when)
    return mins is not None and mins[1] <= mins[0] < mins[2]


def in_opening_window(symbol: str, when: datetime, minutes: int) -> bool:
    """True during the first `minutes` of the symbol's session."""
    mins = session_minutes(symbol, when)
    if mins is None or minutes <= 0:
        return False
    now_min, open_min, _ = mins
    return open_min <= now_min < open_min + minutes


def in_pre_close_window(symbol: str, when: datetime, minutes: int) -> bool:
    """True during the last `minutes` of the symbol's session."""
    mins = session_minutes(symbol, when)
    if mins is None:
        return False
    now_min, open_min, close_min = mins
    return open_min <= now_min < close_min and now_min >= close_min - minutes
