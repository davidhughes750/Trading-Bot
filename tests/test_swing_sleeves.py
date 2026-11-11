"""The swing sleeves' decisions (bot/swing_sleeves.py), checked against the study they were built from."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from bot import swing_sleeves as sw
from bot.market_calendar import add_trading_days, next_trading_day
from bot.research import swing_study


@pytest.fixture(scope="module")
def market():
    """Ten random-walk stocks over about three years, plus the study's signal tables for them."""
    rng = np.random.default_rng(11)
    idx = pd.bdate_range("2023-01-02", "2026-10-30")
    closes = pd.DataFrame(
        {f"S{i}_US_EQ": 50 * np.exp(np.cumsum(rng.normal(0.0006, 0.025, len(idx)))) for i in range(10)}, index=idx
    )
    spy = pd.Series(100.0, index=idx)
    return closes, swing_study.families(closes, spy)


def _panel_before(closes: pd.DataFrame, today: date) -> pd.DataFrame:
    return sw.closes_panel({s: closes[[s]].rename(columns={s: "close"}) for s in closes}, today)


def _study_buys(fam: dict, day: pd.Timestamp) -> list:
    row = fam["entry"].loc[day]
    syms = [s for s in row.index[row.to_numpy(dtype=bool)] if np.isfinite(fam["rank"].at[day, s])]
    return sorted(syms, key=lambda s: fam["rank"].at[day, s], reverse=True)


@pytest.mark.parametrize("strategy,family,setting", [
    (sw.BREAKOUT, "Buy new highs, sell new lows", "100-day high, 20-day low"),
    (sw.DIP, "Buy dips in an uptrend, sell the bounce", "2-day RSI under 5"),
])
def test_daily_sleeves_make_the_same_decisions_as_the_study(market, strategy, family, setting):
    closes, fams = market
    fam = fams[family][setting]
    held = {s: {} for s in closes.columns[:4]}
    buys_seen = sells_seen = 0
    for i in range(len(closes) - 200, len(closes) - 1):
        day, today = closes.index[i], closes.index[i + 1].date()  # the synthetic calendar has no holidays
        d = sw.decide(strategy, _panel_before(closes, today), today, held, slots=5)
        assert [b.symbol for b in d.buys] == [s for s in _study_buys(fam, day) if s not in held], day
        assert sorted(s for s, _ in d.sells) == sorted(s for s in held if bool(fam["exit_"].at[day, s])), day
        buys_seen += len(d.buys)
        sells_seen += len(d.sells)
    assert buys_seen > 5 and sells_seen > 5  # the comparison actually exercised both sides


def test_momentum_holds_the_studys_week_end_picks_all_week(market):
    closes, fams = market
    fam = fams["Hold the 5 strongest, re-pick weekly"]["252-day return"]
    checked = 0
    for day in closes.index[-120:-6]:
        if day.dayofweek != 4:
            continue  # a Friday close: the study re-picks here
        target = _study_buys(fam, day)
        monday = next_trading_day(day.date())
        for today in (monday, add_trading_days(monday, 2)):  # the same list on Monday and on Wednesday
            d = sw.decide(sw.MOMENTUM, _panel_before(closes, today), today, held={}, slots=5)
            assert [b.symbol for b in d.buys] == target, (day, today)
        checked += 1
    assert checked > 10


def test_momentum_sells_what_dropped_out_and_keeps_what_stayed(market):
    closes, _ = market
    today = date(2026, 11, 3)
    panel = _panel_before(closes, today)
    target = [b.symbol for b in sw.decide(sw.MOMENTUM, panel, today, {}, slots=3).buys]
    outsider = next(s for s in closes.columns if s not in target)
    d = sw.decide(sw.MOMENTUM, panel, today, held={target[0]: {}, outsider: {}}, slots=3)
    assert [s for s, _ in d.sells] == [outsider]
    assert [b.symbol for b in d.buys] == target[1:]


def test_last_week_end_row_is_the_previous_weeks_final_session():
    idx = pd.bdate_range("2026-10-19", "2026-11-03")  # Mon 19 Oct .. Tue 3 Nov
    assert idx[sw.last_week_end_row(idx[:-1], date(2026, 11, 3))].date() == date(2026, 10, 30)  # on a Tuesday: last Friday
    assert idx[sw.last_week_end_row(idx[:-2], date(2026, 11, 2))].date() == date(2026, 10, 30)  # on a Monday: last Friday
    assert idx[sw.last_week_end_row(idx[:5], date(2026, 10, 30))].date() == date(2026, 10, 23)  # on a Friday: the Friday before


def test_dip_buy_is_sold_at_its_ten_day_limit_and_tags_new_buys_with_it(market):
    closes, _ = market
    today = date(2026, 11, 3)
    falling = closes.copy()
    falling.iloc[-6:, 0] = falling.iloc[-7, 0] * np.linspace(0.99, 0.94, 6)  # still below its 5-day average
    panel = _panel_before(falling, today)
    sym = closes.columns[0]
    assert sw.decide(sw.DIP, panel, today, {sym: {"max_hold_until": "2026-11-04"}}, 5).sells == []
    sells = sw.decide(sw.DIP, panel, today, {sym: {"max_hold_until": "2026-11-03"}}, 5).sells
    assert [s for s, _ in sells] == [sym] and "10-day limit" in sells[0][1]
    for b in sw.decide(sw.DIP, panel, today, {}, 5).buys:
        assert b.max_hold_until == add_trading_days(today, 10)


def test_no_decision_without_enough_history(market):
    closes, _ = market
    short = _panel_before(closes.iloc[-200:], date(2026, 11, 3))
    for strategy in sw.STRATEGIES:
        d = sw.decide(strategy, short, date(2026, 11, 3), {closes.columns[0]: {}}, 5)
        assert d.buys == [] and d.sells == []
