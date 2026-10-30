"""Daily-bar portfolio simulator for strategy research.

A strategy produces a table of target weights: one row per trading day, one
column per instrument, values 0..1 summing to at most 1 (the rest is cash).
A row dated day t may only use information up to day t's close.

Timing (no look-ahead):
- Weights decided at the close of day t are traded at the open of day t+1.
- The overnight move (close t -> open t+1) is earned by the weights held before
  the trade; the day's move (open t+1 -> close t+1) by the new weights.
- Each trade costs `cost_per_side` x the fraction of the portfolio traded.
- Between rebalances the portfolio is treated as held at its target weights
  (an approximation that only matters for multi-asset weights).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Optional

import pandas as pd

TRADING_DAYS = 252


@dataclass
class SimResult:
    name: str
    equity: pd.Series  # portfolio value at each close, starting at 1.0
    held: pd.DataFrame  # weights held during each day's session
    costs: float  # total costs as a fraction of starting capital (approximate)
    entries: int  # number of times a position was opened
    params: Dict[str, object] = field(default_factory=dict)

    def metrics(self) -> Dict[str, float]:
        return compute_metrics(self.equity, self.held, self.entries)


def compute_metrics(equity: pd.Series, held: Optional[pd.DataFrame] = None, entries: int = 0) -> Dict[str, float]:
    eq = equity.dropna()
    if len(eq) < 2:
        return {}
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    total = eq.iloc[-1] / eq.iloc[0] - 1.0
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0
    rets = eq.pct_change().dropna()
    vol = float(rets.std() * math.sqrt(TRADING_DAYS))
    sharpe = float(rets.mean() / rets.std() * math.sqrt(TRADING_DAYS)) if rets.std() > 0 else 0.0
    dd = eq / eq.cummax() - 1.0
    max_dd = float(dd.min())
    return {
        "total_return_pct": round(total * 100.0, 1),
        "cagr_pct": round(cagr * 100.0, 2),
        "volatility_pct": round(vol * 100.0, 1),
        "sharpe": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd * 100.0, 1),
        "return_over_drawdown": round(cagr / abs(max_dd), 2) if max_dd < 0 else float("inf"),
        "time_in_market_pct": round(float(held.sum(axis=1).mean()) * 100.0, 0) if held is not None else 100.0,
        "entries_per_year": round(entries / years, 1),
        "years": round(years, 1),
    }


def build_panel(data: Dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (opens, closes) indexed by date, one column per symbol, on common dates."""
    opens, closes = {}, {}
    for sym, df in data.items():
        d = df.copy()
        # Daily bars are stamped at local midnight; use the calendar date
        ts = pd.to_datetime(d["timestamp"], utc=True)
        d["date"] = ts.dt.tz_convert("Europe/London").dt.tz_localize(None).dt.normalize()
        d = d.drop_duplicates("date", keep="last").set_index("date")
        opens[sym] = d["open"].astype(float)
        closes[sym] = d["close"].astype(float)
    o = pd.DataFrame(opens).dropna()
    c = pd.DataFrame(closes).reindex(o.index).dropna()
    o = o.reindex(c.index)
    return o, c


def simulate(
    name: str,
    weights: pd.DataFrame,
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    cost_per_side: float | Dict[str, float] = 0.001,
    start: Optional[pd.Timestamp] = None,
    end: Optional[pd.Timestamp] = None,
    cash_rate: float = 0.0,
    params: Optional[Dict[str, object]] = None,
) -> SimResult:
    """Run `weights` (decided at each close) through the opens/closes panel."""
    cols = list(weights.columns)
    idx = closes.index
    if start is not None:
        idx = idx[idx >= pd.Timestamp(start)]
    if end is not None:
        idx = idx[idx <= pd.Timestamp(end)]
    w = weights.reindex(closes.index).fillna(0.0)[cols].clip(lower=0.0)
    over = w.sum(axis=1) > 1.0 + 1e-9
    if over.any():
        w.loc[over] = w.loc[over].div(w.loc[over].sum(axis=1), axis=0)

    o = opens[cols].reindex(closes.index)
    c = closes[cols]
    costs = pd.Series(
        [cost_per_side.get(s, 0.001) if isinstance(cost_per_side, dict) else cost_per_side for s in cols],
        index=cols,
    )
    daily_cash = (1.0 + cash_rate) ** (1.0 / TRADING_DAYS) - 1.0

    pos = {d: i for i, d in enumerate(closes.index)}
    first = pos[idx[0]]
    equity_vals = [1.0]
    held_rows = [pd.Series(0.0, index=cols)]
    total_cost = 0.0
    entries = 0
    prev_held = pd.Series(0.0, index=cols)  # start in cash: the first trade pays its cost

    for i in range(first + 1, pos[idx[-1]] + 1):
        e = equity_vals[-1]
        target = w.iloc[i - 1]  # decided at yesterday's close, traded at today's open
        gap = (o.iloc[i] / c.iloc[i - 1] - 1.0).fillna(0.0)
        intraday = (c.iloc[i] / o.iloc[i] - 1.0).fillna(0.0)

        e *= 1.0 + float((prev_held * gap).sum()) + (1.0 - float(prev_held.sum())) * daily_cash / 2
        traded = (target - prev_held).abs()
        cost = float((traded * costs).sum()) * e
        e -= cost
        total_cost += cost
        entries += int(((prev_held <= 1e-12) & (target > 1e-12)).sum())
        e *= 1.0 + float((target * intraday).sum()) + (1.0 - float(target.sum())) * daily_cash / 2

        equity_vals.append(e)
        held_rows.append(target)
        prev_held = target

    dates = closes.index[first: pos[idx[-1]] + 1]
    equity = pd.Series(equity_vals, index=dates)
    held = pd.DataFrame(held_rows, index=dates)
    return SimResult(name=name, equity=equity, held=held, costs=total_cost, entries=entries, params=params or {})
