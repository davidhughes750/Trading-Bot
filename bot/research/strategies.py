"""Daily strategies expressed as target-weight tables (see engine.py for timing).

Every function returns a DataFrame indexed like `closes`, where row t uses only
closes up to and including day t.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd


def buy_and_hold(closes: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Always 100% in `symbol` (the benchmark to beat)."""
    w = pd.DataFrame(0.0, index=closes.index, columns=[symbol])
    w[symbol] = 1.0
    return w


def trend_filter(
    closes: pd.DataFrame, symbol: str, sma_days: int = 200, safe: Optional[str] = None
) -> pd.DataFrame:
    """Hold `symbol` while its close is above its `sma_days` moving average.

    Below the average, hold `safe` (e.g. gilts) or cash. The aim is mainly to
    sit out long bear markets rather than to beat the market in rising ones.
    """
    px = closes[symbol]
    above = px > px.rolling(sma_days, min_periods=sma_days).mean()
    cols = [symbol] + ([safe] if safe else [])
    w = pd.DataFrame(0.0, index=closes.index, columns=cols)
    w[symbol] = above.astype(float)
    if safe:
        ready = px.rolling(sma_days, min_periods=sma_days).mean().notna()
        w[safe] = ((~above) & ready).astype(float)
    return w


def momentum_rotation(
    closes: pd.DataFrame,
    symbols: List[str],
    lookback_days: int = 126,
    top_n: int = 2,
    safe: Optional[str] = None,
    absolute_filter: bool = True,
) -> pd.DataFrame:
    """Each month-end, hold the `top_n` assets with the best `lookback_days` return.

    With `absolute_filter`, an asset is only held if its own return is positive;
    its share goes to `safe` (or cash) instead. Weights are equal and held until
    the next month-end.
    """
    universe = [s for s in symbols if s != safe]
    ret = closes[universe] / closes[universe].shift(lookback_days) - 1.0
    month_end = closes.index.to_series().groupby(closes.index.to_period("M")).transform("max") == closes.index

    cols = universe + ([safe] if safe and safe not in universe else [])
    w = pd.DataFrame(float("nan"), index=closes.index, columns=cols)
    for day in closes.index[month_end.values]:
        r = ret.loc[day].dropna()
        if len(r) < top_n:
            continue
        row = pd.Series(0.0, index=cols)
        picks = r.sort_values(ascending=False).head(top_n)
        for sym, val in picks.items():
            if absolute_filter and val <= 0:
                if safe:
                    row[safe] += 1.0 / top_n
            else:
                row[sym] += 1.0 / top_n
        w.loc[day] = row
    return w.ffill().fillna(0.0)


def rsi(series: pd.Series, days: int) -> pd.Series:
    """Wilder's RSI."""
    delta = series.diff()
    gain = delta.clip(lower=0.0).ewm(alpha=1.0 / days, adjust=False, min_periods=days).mean()
    loss = (-delta.clip(upper=0.0)).ewm(alpha=1.0 / days, adjust=False, min_periods=days).mean()
    rs = gain / loss.replace(0.0, float("nan"))
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.where(loss > 0, 100.0)


def dip_buy(
    closes: pd.DataFrame,
    symbol: str,
    entry_rsi: float = 10.0,
    rsi_days: int = 2,
    trend_days: int = 200,
    exit_sma_days: int = 5,
    max_hold_days: int = 10,
) -> pd.DataFrame:
    """Buy short pullbacks inside a long-term uptrend; sell on the bounce.

    Enter when the close is above its `trend_days` average and the `rsi_days` RSI
    is below `entry_rsi`. Exit when the close rises above its `exit_sma_days`
    average, or after `max_hold_days`.
    """
    px = closes[symbol]
    trend = px.rolling(trend_days, min_periods=trend_days).mean()
    exit_ma = px.rolling(exit_sma_days, min_periods=exit_sma_days).mean()
    r = rsi(px, rsi_days)

    held = []
    in_pos, days_in = False, 0
    for day in closes.index:
        p, t, e, x = px.loc[day], trend.loc[day], exit_ma.loc[day], r.loc[day]
        if in_pos:
            days_in += 1
            if p > e or days_in >= max_hold_days:
                in_pos = False
        elif pd.notna(t) and pd.notna(x) and p > t and x < entry_rsi:
            in_pos, days_in = True, 0
        held.append(1.0 if in_pos else 0.0)
    return pd.DataFrame({symbol: held}, index=closes.index)
