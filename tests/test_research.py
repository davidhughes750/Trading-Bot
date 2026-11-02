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


def test_turn_of_month_holds_only_around_month_end():
    from bot.research.strategies import turn_of_month

    idx = pd.bdate_range("2021-01-01", "2021-03-31")
    c = pd.DataFrame({"A": 100.0}, index=idx)
    w = turn_of_month(c, "A", days_before=1, days_after=2)["A"]
    # Weight on day t means "hold from day t+1's open": so the day before Jan's last
    # trading day (Jan 28) is the first 1.0, and it stays on through Feb 2.
    on = list(w[w == 1.0].index.strftime("%m-%d"))
    assert on[0] == "01-01"  # data starts on a month's first day: hold into Jan 4 (2nd day)
    assert on[1:4] == ["01-28", "01-29", "02-01"]
    assert "02-02" not in on and "01-27" not in on


def test_fib_retracement_buys_bounce_and_exits_at_old_high():
    from bot.research.strategies import fib_retracement

    rise = list(np.linspace(100, 120, 30))       # +20% swing, high at 120
    pullback = [116, 112, 108, 107.6]            # 61.8% retracement of 100->120 = 107.64
    bounce = [109, 114, 121, 121]                # back above the level, then above the old high
    o, c = panel({"A": [100.0] * 20 + rise + pullback + bounce})
    w = fib_retracement(c, "A", level=0.618, lookback_days=40, min_move_pct=8.0)["A"]
    entry_day = 20 + 30 + len(pullback)  # first bounce close
    assert w.iloc[entry_day] == 1.0 and w.iloc[entry_day - 1] == 0.0
    assert w.iloc[-1] == 0.0  # sold once the old high was regained


def test_cash_interest_series_and_monthly_trend_filter():
    from bot.research.strategies import monthly_trend_filter

    o, c = panel({"A": [100.0] * 253})
    rate = pd.Series(0.05, index=c.index)
    res = simulate("cash", pd.DataFrame({"A": 0.0}, index=c.index), o, c, cost_per_side=0.0, cash_rate=rate)
    assert res.equity.iloc[-1] == pytest.approx(1.05, rel=0.01)  # ~a year of 5% interest

    idx = pd.bdate_range("2020-01-01", "2021-12-31")
    rising = pd.DataFrame({"A": np.linspace(100, 200, len(idx))}, index=idx)
    w = monthly_trend_filter(rising, "A", months=3)["A"]
    changes = w.diff().abs().fillna(0)
    month_end = idx.to_series().groupby(idx.to_period("M")).transform("max") == idx
    assert (changes[~month_end.values] == 0).all()  # only switches at month-ends
    assert w.iloc[-1] == 1.0 and w.iloc[:40].sum() == 0  # needs 3 months of history first


def test_bootstrap_difference_separates_a_real_edge_from_noise():
    from bot.research.validate_momentum import bootstrap_difference

    idx = pd.date_range("2010-01-31", periods=120, freq="ME")
    rng = np.random.default_rng(1)
    base = pd.Series(rng.normal(0.008, 0.04, len(idx)), index=idx)
    better = base + 0.02  # +2 points every single month: an unmistakable edge
    worse = base - 0.02
    assert bootstrap_difference(better, base)["prob_sharpe_ahead"] > 0.95
    assert bootstrap_difference(worse, base)["prob_sharpe_ahead"] < 0.05
    noisy = pd.Series(rng.normal(0.008, 0.04, len(idx)), index=idx)  # same average, different luck
    assert 0.05 < bootstrap_difference(noisy, base)["prob_sharpe_ahead"] < 0.95
    assert bootstrap_difference(base.iloc[:10], base.iloc[:10]) == {}  # too little data to say anything
    assert bootstrap_difference(better, base, seed=3) == bootstrap_difference(better, base, seed=3)  # reproducible


def test_annual_and_monthly_returns_from_an_equity_curve():
    from bot.research.validate_momentum import annual_returns, monthly_returns

    idx = pd.bdate_range("2020-01-02", "2021-12-31")
    eq = pd.Series(np.linspace(1.0, 1.44, len(idx)), index=idx)  # a smooth climb
    yearly = annual_returns(eq)
    assert list(yearly.index) == [2020, 2021]
    assert (1 + yearly).prod() == pytest.approx(1.44, rel=1e-6)  # the two years compound to the whole move
    monthly = monthly_returns(eq)
    assert len(monthly) >= 22 and (monthly > 0).all()
