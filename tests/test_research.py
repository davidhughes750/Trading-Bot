"""Tests for the daily research engine and strategies (offline, synthetic data)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bot.research.engine import compute_metrics, simulate
from bot.research.strategies import buy_and_hold, dip_buy, momentum_rotation, trend_filter


def panel(closes: dict, opens: dict | None = None):
    idx = pd.bdate_range("2020-01-01", periods=len(next(iter(closes.values()))))
    c = pd.DataFrame(closes, index=idx, dtype=float)
    o = pd.DataFrame(opens, index=idx, dtype=float) if opens else c.shift(1).fillna(c.iloc[0])
    return o, c


def test_buy_and_hold_pays_one_entry_cost_and_starts_at_first_open():
    o, c = panel({"A": [100, 110, 121, 133.1]}, {"A": [100, 105, 115, 125]})
    res = simulate("bh", buy_and_hold(c, "A"), o, c, cost_per_side=0.01)
    # Decided at day 0 close, bought at day 1 open (105), held to the last close (133.1)
    assert res.equity.iloc[-1] == pytest.approx((133.1 / 105.0) * 0.99)
    assert res.entries == 1


def test_no_lookahead_signal_earns_next_session_not_same_day():
    o, c = panel({"A": [100, 100, 150, 150, 150]}, {"A": [100, 100, 100, 150, 150]})
    # Signal on day 2 (the day of the +50% move) must not capture that move
    w = pd.DataFrame({"A": [0, 0, 1, 1, 1]}, index=c.index, dtype=float)
    res = simulate("late", w, o, c, cost_per_side=0.0)
    assert res.equity.iloc[-1] == pytest.approx(1.0)
    # Signal on day 1 is executed at day 2's open and does capture it
    w2 = pd.DataFrame({"A": [0, 1, 1, 1, 1]}, index=c.index, dtype=float)
    assert simulate("ontime", w2, o, c, cost_per_side=0.0).equity.iloc[-1] == pytest.approx(1.5)


def test_round_trips_cost_twice():
    o, c = panel({"A": [100.0] * 6})
    w = pd.DataFrame({"A": [1, 0, 1, 0, 1, 0]}, index=c.index, dtype=float)
    res = simulate("churn", w, o, c, cost_per_side=0.01)
    assert res.equity.iloc[-1] == pytest.approx(0.99 ** 5)  # 5 changes after the first decision
    assert res.entries == 3


def test_trend_filter_switches_to_safe_asset():
    up = list(np.linspace(100, 200, 30))
    down = list(np.linspace(200, 120, 30))
    o, c = panel({"EQ": up + down, "BOND": [100.0] * 60})
    w = trend_filter(c, "EQ", sma_days=10, safe="BOND")
    assert w["EQ"].iloc[25] == 1.0 and w["BOND"].iloc[25] == 0.0
    assert w["EQ"].iloc[-1] == 0.0 and w["BOND"].iloc[-1] == 1.0
    assert (w.iloc[:9].sum(axis=1) == 0).all()  # nothing before the average exists


def test_momentum_rotation_picks_winners_monthly_and_respects_absolute_filter():
    n = 130
    idx_len = n
    o, c = panel({
        "WIN": list(np.linspace(100, 200, idx_len)),
        "MID": list(np.linspace(100, 120, idx_len)),
        "LOSE": list(np.linspace(100, 60, idx_len)),
        "SAFE": [100.0] * idx_len,
    })
    w = momentum_rotation(c, ["WIN", "MID", "LOSE", "SAFE"], lookback_days=20, top_n=2, safe="SAFE")
    last = w.iloc[-1]
    assert last["WIN"] == pytest.approx(0.5) and last["MID"] == pytest.approx(0.5)
    assert last["LOSE"] == 0.0
    changes = w.diff().abs().sum(axis=1)
    month_ends = c.index.to_series().groupby(c.index.to_period("M")).transform("max") == c.index
    assert (changes[~month_ends.values] == 0).all()  # only trades at month-ends

    w1 = momentum_rotation(c, ["LOSE", "SAFE"], lookback_days=20, top_n=1, safe="SAFE")
    assert w1["SAFE"].iloc[-1] == 1.0 and w1["LOSE"].iloc[-1] == 0.0


def test_dip_buy_only_in_uptrend_and_exits_on_bounce():
    base = list(np.linspace(100, 150, 60))
    dip = [148, 145, 142]
    bounce = [150, 152, 153]
    o, c = panel({"A": base + dip + bounce})
    w = dip_buy(c, "A", entry_rsi=20, trend_days=20, exit_sma_days=3)
    assert w["A"].iloc[:60].sum() == 0
    assert w["A"].iloc[61] == 1.0 or w["A"].iloc[62] == 1.0
    assert w["A"].iloc[-1] == 0.0

    falling = list(np.linspace(150, 100, 60)) + dip
    o2, c2 = panel({"A": falling})
    assert dip_buy(c2, "A", entry_rsi=20, trend_days=20)["A"].sum() == 0  # no buying in a downtrend


def test_metrics_drawdown_and_cagr():
    idx = pd.bdate_range("2020-01-01", periods=3)
    eq = pd.Series([1.0, 0.5, 1.0], index=[idx[0], idx[0] + pd.Timedelta(days=183), idx[0] + pd.Timedelta(days=366)])
    m = compute_metrics(eq)
    assert m["max_drawdown_pct"] == pytest.approx(-50.0)
    assert m["cagr_pct"] == pytest.approx(0.0, abs=0.01)
