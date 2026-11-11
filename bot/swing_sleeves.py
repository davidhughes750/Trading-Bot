"""Swing sleeves: three multi-day rules run on the demo account as forward tests.

Built from `bot/research/swing_study.py` (`python research.py --swing-study`). That study could not show an
edge: the bot's stock list is made of past winners, so every rule looked good and none beat simply holding
the list. A forward test has no such bias, which is the reason these run. Read each sleeve's results in the
trade journal (entry_context.strategy) before trusting any of them with real money.

Rules (the settings the study chose on 2012-2019; not tuned further). Every signal uses daily closes up to the
last completed session, and the bot trades the next session after the opening-bell guard (the study traded
that session's open):
  swing_momentum  Hold the stocks with the best 252-day return among those above their 200-day average,
                  as ranked at the last close of the previous week. Sell whatever dropped out of that list.
  swing_breakout  Buy a close at a 100-day high while above the 200-day average (strongest 20-day return
                  first). Sell after a close at a 20-day low.
  swing_dip       Buy a close above the 200-day average with 2-day RSI under 5 (lowest RSI first). Sell after
                  a close above the 5-day average, or on the 10th trading day after entry.
Each sleeve has its own slots. A stock held by any other strategy is skipped, because Trading 212 keeps one
position per ticker; the study had no such limit.
The intraday machinery (trailing stops, take-profit, end-of-day flat, slot rotation, AI veto) does not touch
these positions. The only stop is a wide safety stop that the study did not have (SWING_SAFETY_STOP_PCT).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from bot.market_calendar import add_trading_days
from bot.research.strategies import rsi

MOMENTUM = "swing_momentum"
BREAKOUT = "swing_breakout"
DIP = "swing_dip"
STRATEGIES = (MOMENTUM, BREAKOUT, DIP)
LABELS = {MOMENTUM: "Momentum rotation", BREAKOUT: "Breakout", DIP: "Dip buy"}

TREND_DAYS = 200
MOMENTUM_LOOKBACK = 252
BREAKOUT_HIGH_DAYS = 100
BREAKOUT_LOW_DAYS = 20
BREAKOUT_RANK_DAYS = 20
DIP_RSI_DAYS = 2
DIP_RSI_BELOW = 5.0
DIP_EXIT_SMA_DAYS = 5
DIP_MAX_HOLD_DAYS = 10
MIN_HISTORY = MOMENTUM_LOOKBACK + 5  # sessions needed before a stock can be ranked by every rule


@dataclass(frozen=True)
class Buy:
    symbol: str
    detail: str  # why, for the log and the journal
    max_hold_until: Optional[date] = None  # sell at this session's open at the latest (dip buys only)


@dataclass
class Decision:
    sells: List[Tuple[str, str]] = field(default_factory=list)  # (symbol, reason)
    buys: List[Buy] = field(default_factory=list)  # best first; the caller buys while slots remain


def strategy_of(position: Any) -> str:
    return str((getattr(position, "entry_context", None) or {}).get("strategy") or "")


def is_swing_position(position: Any) -> bool:
    return strategy_of(position) in STRATEGIES


def closes_panel(daily: Dict[str, pd.DataFrame], today: date) -> pd.DataFrame:
    """Close prices by date (rows) and symbol (columns), completed sessions before `today` only."""
    cols = {sym: df["close"].astype(float) for sym, df in daily.items() if len(df)}
    panel = pd.DataFrame(cols).sort_index()
    return panel[panel.index.date < today]


def _week(d: date) -> Tuple[int, int]:
    iso = d.isocalendar()
    return iso[0], iso[1]


def last_week_end_row(index: pd.DatetimeIndex, today: date) -> Optional[int]:
    """Position of the last session of the most recent week that ended before `today`'s week began."""
    this_week = _week(today)
    for i in range(len(index) - 1, -1, -1):
        if _week(index[i].date()) != this_week:
            return i
    return None


def decide(
    strategy: str,
    closes: pd.DataFrame,
    today: date,
    held: Dict[str, Dict[str, Any]],
    slots: int,
) -> Decision:
    """What `strategy` should sell and buy at `today`'s session.

    `closes` comes from `closes_panel`; `held` maps this sleeve's open symbols to their entry_context.
    Buys are every qualifying stock in rank order: the caller skips blocked symbols and stops at the slot limit.
    """
    out = Decision()
    if len(closes) < MIN_HISTORY:
        return out
    last = closes.index[-1]
    sma200 = closes.rolling(TREND_DAYS, min_periods=TREND_DAYS).mean()
    up = closes > sma200

    if strategy == MOMENTUM:
        row = last_week_end_row(closes.index, today)
        if row is None or row < MIN_HISTORY - 1:
            return out
        day = closes.index[row]
        mom = (closes / closes.shift(MOMENTUM_LOOKBACK) - 1.0).where(up).loc[day].dropna()
        ranked = mom.sort_values(ascending=False)
        target = list(ranked.index[:slots])
        for sym in held:
            if sym not in target:
                out.sells.append((sym, f"Momentum rotation: no longer in the top {slots} at the {day.date()} close"))
        for sym in target:
            if sym not in held:
                out.buys.append(Buy(sym, f"12-month return {ranked[sym] * 100:+.0f}%, ranked {target.index(sym) + 1} at the {day.date()} close"))
        return out

    if strategy == BREAKOUT:
        low = closes.loc[last] <= closes.rolling(BREAKOUT_LOW_DAYS, min_periods=BREAKOUT_LOW_DAYS).min().loc[last]
        for sym in held:
            if sym in low.index and bool(low[sym]):
                out.sells.append((sym, f"Breakout: closed at a {BREAKOUT_LOW_DAYS}-day low on {last.date()}"))
        high = closes.loc[last] >= closes.rolling(BREAKOUT_HIGH_DAYS, min_periods=BREAKOUT_HIGH_DAYS).max().loc[last]
        roc = (closes / closes.shift(BREAKOUT_RANK_DAYS) - 1.0).loc[last]
        picks = roc[high & up.loc[last]].dropna().sort_values(ascending=False)
        for sym, val in picks.items():
            if sym not in held:
                out.buys.append(Buy(sym, f"{BREAKOUT_HIGH_DAYS}-day closing high on {last.date()}, {BREAKOUT_RANK_DAYS}-day return {val * 100:+.0f}%"))
        return out

    if strategy == DIP:
        above_sma5 = closes.loc[last] > closes.rolling(DIP_EXIT_SMA_DAYS).mean().loc[last]
        for sym, ctx in held.items():
            until = _parse_date(ctx.get("max_hold_until"))
            if sym in above_sma5.index and bool(above_sma5[sym]):
                out.sells.append((sym, f"Dip buy: bounced above its {DIP_EXIT_SMA_DAYS}-day average on {last.date()}"))
            elif until is not None and today >= until:
                out.sells.append((sym, f"Dip buy: {DIP_MAX_HOLD_DAYS}-day limit reached"))
        r2 = closes.apply(lambda col: rsi(col, DIP_RSI_DAYS)).loc[last]
        picks = r2[(r2 < DIP_RSI_BELOW) & up.loc[last]].dropna().sort_values()
        until = add_trading_days(today, DIP_MAX_HOLD_DAYS)
        for sym, val in picks.items():
            if sym not in held:
                out.buys.append(Buy(sym, f"{DIP_RSI_DAYS}-day RSI {val:.1f} in an uptrend on {last.date()}", until))
        return out

    raise ValueError(f"Unknown swing strategy '{strategy}'")


def _parse_date(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
