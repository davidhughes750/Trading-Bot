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


def turn_of_month(
    closes: pd.DataFrame, symbol: str, days_before: int = 1, days_after: int = 3
) -> pd.DataFrame:
    """Hold `symbol` over the turn of each month, cash otherwise.

    Invested during the last `days_before` and first `days_after` trading days of
    each month (when salary and pension money tends to be invested). Uses only the
    trading calendar, which is known in advance. The final, incomplete month of
    the data cannot know its true month-end, which only affects the last few days.
    """
    idx = closes.index
    month = idx.to_period("M")
    ones = pd.Series(1, index=idx)
    from_start = ones.groupby(month).cumsum()
    from_end = ones[::-1].groupby(month[::-1]).cumsum()[::-1]
    in_window = (from_end <= days_before) | (from_start <= days_after)
    # Weights decided at day t's close apply from day t+1's open, so set the
    # weight on the day BEFORE each window day.
    hold_next = in_window.shift(-1, fill_value=False)
    return pd.DataFrame({symbol: hold_next.astype(float)}, index=idx)


def fib_retracement(
    closes: pd.DataFrame,
    symbol: str,
    level: float = 0.618,
    lookback_days: int = 60,
    min_move_pct: float = 8.0,
    recent_high_days: int = 30,
    stop_level: float = 0.786,
    max_hold_days: int = 20,
) -> pd.DataFrame:
    """Buy a bounce off a Fibonacci retracement level of a recent rise.

    Swing: within the last `lookback_days` closes (excluding today), the highest
    close, which must be within `recent_high_days`, and the lowest close before it.
    The rise must be at least `min_move_pct`. Retracement price =
    high - level x (high - low).
    Entry: yesterday closed at or below that price and today closes above it.
    Exit: close back at the swing high (target), close below the `stop_level`
    retracement (stop), or after `max_hold_days`.
    """
    px = closes[symbol].to_numpy(dtype=float)
    held = [0.0] * len(px)
    in_pos = False
    target = stop = 0.0
    days_in = 0
    for t in range(len(px)):
        if in_pos:
            days_in += 1
            if px[t] >= target or px[t] < stop or days_in >= max_hold_days:
                in_pos = False
        elif t > lookback_days:
            window = px[t - lookback_days: t]
            hi_i = int(window.argmax())
            if hi_i < lookback_days - recent_high_days or hi_i == 0:
                held[t] = 0.0
                continue
            lo_i = int(window[: hi_i].argmin())
            hi, lo = window[hi_i], window[lo_i]
            if lo <= 0 or (hi / lo - 1.0) * 100.0 < min_move_pct:
                continue
            fib = hi - level * (hi - lo)
            if px[t - 1] <= fib < px[t]:
                in_pos = True
                target, stop, days_in = hi, hi - stop_level * (hi - lo), 0
        held[t] = 1.0 if in_pos else 0.0
    return pd.DataFrame({symbol: held}, index=closes.index)


def monthly_trend_filter(closes: pd.DataFrame, symbol: str, months: int = 10) -> pd.DataFrame:
    """Check once a month: hold `symbol` if its month-end close is above its `months`-month average.

    The decision is made on the last trading day of each month and held all next
    month, which avoids most of the day-to-day whipsaws of a daily rule.
    """
    px = closes[symbol]
    month = px.index.to_period("M")
    month_end_px = px.groupby(month).last()
    avg = month_end_px.rolling(months, min_periods=months).mean()
    signal_by_month = (month_end_px > avg).astype(float).where(avg.notna(), 0.0)
    is_month_end = px.index.to_series().groupby(month).transform("max") == px.index
    w = pd.Series(float("nan"), index=px.index)
    w[is_month_end.values] = signal_by_month.reindex(month[is_month_end.values]).to_numpy()
    return pd.DataFrame({symbol: w.ffill().fillna(0.0)}, index=px.index)
