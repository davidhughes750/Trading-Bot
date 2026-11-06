"""Gap-rebound sleeve: buy a stock the day after it gapped down hard on its own news, hold a few days.

Built from `bot/research/gap_study.py` (`python research.py --gap-study`). That study found positive
averages but negative medians, a weak edge once realistic entries and costs are applied, and a
survivorship bias that flatters it. This sleeve runs on the demo account as a forward test; read its results in
the trade journal (entry_context.strategy == "gap_rebound") before trusting it with anything.

Rules (fixed, taken from the study; not tuned):
  Event     a stock opened >= GAP_REBOUND_THRESHOLD_PCT below its previous close, on a day SPY did not gap
            down more than 2%, with no other such gap in the previous 10 trading days.
  Entry     the next trading day, after the opening-bell guard (the study bought that day's open).
  Exit      the close of the 5th trading day after the gap day, or a hard stop GAP_REBOUND_STOP_PCT below entry.
  Size      GAP_REBOUND_POSITION_PCT of equity, at most GAP_REBOUND_MAX_POSITIONS at once.
The intraday machinery (trailing stops, take-profit, end-of-day flat, slot rotation, AI veto) does not touch these.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List

import pandas as pd

from bot.market_calendar import add_trading_days, next_trading_day
from bot.research.gap_study import find_events

STRATEGY = "gap_rebound"
BENCHMARK = "SPY_US_EQ"


@dataclass(frozen=True)
class GapCandidate:
    symbol: str
    gap_date: date
    gap_pct: float  # negative, e.g. -26.7
    exit_date: date  # close of this day (the 5th trading day after the gap day by default)


def is_gap_position(position: Any) -> bool:
    return (getattr(position, "entry_context", None) or {}).get("strategy") == STRATEGY


def find_candidates(
    daily: Dict[str, pd.DataFrame], today: date, threshold_pct: float, hold_days: int
) -> List[GapCandidate]:
    """Stocks that gapped down yesterday (the last completed session before `today`) and qualify today.

    `daily` maps symbol -> date-indexed open/close frame; it must contain the SPY benchmark. A gap older than
    the previous trading day is ignored: entering late would not be the tested trade.
    """
    spy = daily.get(BENCHMARK)
    if spy is None or len(spy) < 5:
        return []
    spy_gap = spy["open"] / spy["close"].shift(1) - 1.0
    threshold = -abs(threshold_pct) / 100.0
    out: List[GapCandidate] = []
    for sym, df in daily.items():
        if sym == BENCHMARK or len(df) < 30:
            continue
        past = df[df.index.date < today]
        if len(past) < 30:
            continue
        gap_day = past.index[-1]
        if next_trading_day(gap_day.date()) != today:
            continue
        if gap_day not in find_events(past, spy_gap, threshold):
            continue
        prev_close = float(past["close"].iloc[-2])
        gap_pct = (float(past["open"].iloc[-1]) / prev_close - 1.0) * 100.0
        out.append(GapCandidate(sym, gap_day.date(), round(gap_pct, 1), add_trading_days(gap_day.date(), hold_days)))
    return sorted(out, key=lambda c: c.gap_pct)  # the deepest gap first
