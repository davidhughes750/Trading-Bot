"""End-to-end tests of the live trading loop (`TradingBot.run_cycle` and its steps).

The real TradingBot runs against the paper simulator with a fake clock, fake quotes and a fake
screener, so each test exercises the code that ties together sync, risk, exits, scanning and
entries, which the unit tests only cover piece by piece.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import pytest

from bot.config import Config
from bot.fx import FixedFxConverter
from bot.models import (
    OrderBookSnapshot,
    Position,
    Side,
    Signal,
    SignalAction,
    StockRecommendation,
    TradePlan,
)
from main import TradingBot

UTC = timezone.utc
# 2026-11-03 is a Tuesday and US daylight saving has ended, so ET = UTC-5 and London = UTC.
MID_SESSION = datetime(2026, 11, 3, 15, 30, tzinfo=UTC)  # 10:30 ET / 15:30 London: both markets open
OPENING_BELL = datetime(2026, 11, 3, 14, 35, tzinfo=UTC)  # 09:35 ET: first-15-minutes guard
US_PRE_CLOSE = datetime(2026, 11, 3, 20, 52, tzinfo=UTC)  # 15:52 ET
UK_PRE_CLOSE = datetime(2026, 11, 3, 16, 22, tzinfo=UTC)  # 16:22 London
WEEKEND = datetime(2026, 11, 7, 15, 30, tzinfo=UTC)  # Saturday


def make_rec(symbol: str, score: float = 90.0, price: float = 200.0, atr: float = 2.0, actionable: bool = True) -> StockRecommendation:
    sig = Signal(
        symbol=symbol, action=SignalAction.BUY, candle_timestamp="2026-11-03T15:15:00+00:00", close_price=price,
        ema_fast=price * 1.01, ema_slow=price, rsi=60.0, atr=atr, reason="test setup",
        target_side=Side.LONG if actionable else None,
    )
    return StockRecommendation(
        symbol=symbol, score=score, rating="STRONG BUY" if actionable else "WATCH", actionable=actionable,
        close_price=price, ema_fast=price * 1.01, ema_slow=price, rsi=60.0, atr=atr, rvol=1.5, roc_10_pct=1.0,
        suggested_stop_loss=price - 3 * atr / 2, suggested_take_profit=price + 4, thesis="test", signal=sig,
        trend_strong=True,
    )


class Harness:
    """A TradingBot wired to fakes. `quotes` maps symbol -> (bid, ask); `recs` is what the screener returns."""

    def __init__(self, tmp_path: Path, monkeypatch, now: datetime, **cfg_overrides) -> None:
        monkeypatch.chdir(tmp_path)  # the loop writes logs/*.json relative to the working directory
        (tmp_path / "logs").mkdir()
        self.tmp = tmp_path
        settings = dict(
            execution_mode="paper",
            state_file=str(tmp_path / "logs" / "t212_state.json"),
            log_file=str(tmp_path / "logs" / "bot.log"),
            ai_decisions_file=str(tmp_path / "logs" / "ai_decisions.json"),
            enable_ai_manager=False,
            enable_telegram=False,
            market_regime_filter=False,
            account_currency="GBP",
            paper_initial_equity=10_000.0,
            symbols=["AAPL_US_EQ", "NVDA_US_EQ"],
        )
        settings.update(cfg_overrides)
        self.cfg = Config(**settings)
        self.now = now
        monkeypatch.setattr(TradingBot, "_now", staticmethod(lambda: self.now))
        self.bot = TradingBot(self.cfg)
        self.fx = FixedFxConverter(self.cfg, {"USD": 0.8})  # 1 USD = 0.80 GBP, no network
        self.bot.fx = self.fx
        self.bot.order_executor.fx = self.fx
        self.quotes: Dict[str, tuple] = {}
        self.recs: List[StockRecommendation] = []
        self.fetch_calls: List[str] = []
        self.quote_age_sec: Dict[str, float] = {}  # symbol -> how old the last trade in its quote is
        self.bar_ts = pd.Timestamp("2026-11-03 15:15", tz="UTC")

        def fake_quote(symbol: str) -> OrderBookSnapshot:
            bid, ask = self.quotes[symbol]
            now = datetime.now(UTC)
            traded = now - timedelta(seconds=self.quote_age_sec[symbol]) if symbol in self.quote_age_sec else None
            return OrderBookSnapshot(
                symbol=symbol, bid=bid, ask=ask, last=(bid + ask) / 2, timestamp=now, quote_time=traded
            )

        def fake_history(symbol: str, limit: Optional[int] = None) -> pd.DataFrame:
            self.fetch_calls.append(symbol)
            return pd.DataFrame({"timestamp": [self.bar_ts]})

        self.bot.data_handler.fetch_order_book_snapshot = fake_quote
        self.bot.data_handler.fetch_closed_ohlcv = fake_history
        self.bot.screener.scan_universe = lambda positions, cache=None: list(self.recs)

    def cycle(self) -> None:
        asyncio.run(self.bot.run_cycle())

    @property
    def positions(self) -> Dict[str, Position]:
        return self.bot.order_executor.positions

    def open_position(self, symbol: str, price: float = 200.0, atr: float = 2.0, qty: float = 10.0) -> Position:
        """Open a position through the real executor, as the loop would."""
        ob = OrderBookSnapshot(symbol=symbol, bid=price - 0.05, ask=price, last=price)
        self.quotes[symbol] = (price - 0.05, price)
        fx = self.fx.rate_for_symbol(symbol)
        plan = TradePlan(
            symbol=symbol, side=Side.LONG, order_side="buy", quantity=qty, reference_price=price,
            stop_loss=price - 1.5 * atr, take_profit=price + 2 * atr, atr=atr, risk_amount=20.0,
            notional=qty * price * fx, spread_pct=0.0002, reason="test", fx_rate=fx,
        )
        pos = self.bot.order_executor.execute_entry(plan, ob)
        assert pos is not None
        return pos

    def journal(self) -> List[dict]:
        path = self.tmp / "logs" / "trade_journal.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@pytest.fixture
def make_harness(tmp_path, monkeypatch):
    def _make(now: datetime = MID_SESSION, **overrides) -> Harness:
        return Harness(tmp_path, monkeypatch, now, **overrides)
    return _make


# ----------------------------------------------------------------------------- entries
def test_cycle_opens_a_position_for_an_actionable_pick_and_sizes_it_in_gbp(make_harness):
    h = make_harness()
    h.quotes["NVDA_US_EQ"] = (199.95, 200.00)
    h.recs = [make_rec("NVDA_US_EQ")]
    h.cycle()

    assert list(h.positions) == ["NVDA_US_EQ"]
    pos = h.positions["NVDA_US_EQ"]
    assert pos.fx_rate_at_entry == pytest.approx(0.8)
    notional_gbp = pos.quantity * pos.entry_price * 0.8
    assert notional_gbp <= 0.33 * 10_000 + 1  # single-position cap
    assert pos.quantity * pos.entry_price * 0.8 <= 10_000 / 4 + 1  # cash split across the open slots
    assert pos.stop_loss < pos.entry_price < pos.take_profit
    assert pos.entry_context["score"] == 90.0  # the journal can later explain why it was bought
    assert h.bot.order_executor.paper_quote_balance < 10_000  # cash was spent
    assert (h.tmp / "logs" / "scan_log.jsonl").exists()  # every scored candidate is recorded


def test_no_entry_on_a_delayed_quote(make_harness):
    # Yahoo's UK quotes run 15-20 minutes late: acting on them means trading on old prices
    h = make_harness()
    h.quotes["NVDA_US_EQ"] = (199.95, 200.00)
    h.recs = [make_rec("NVDA_US_EQ")]
    h.quote_age_sec["NVDA_US_EQ"] = 15 * 60
    h.cycle()
    assert h.positions == {}


def test_entry_allowed_on_a_fresh_quote(make_harness):
    h = make_harness()
    h.quotes["NVDA_US_EQ"] = (199.95, 200.00)
    h.recs = [make_rec("NVDA_US_EQ")]
    h.quote_age_sec["NVDA_US_EQ"] = 20
    h.cycle()
    assert list(h.positions) == ["NVDA_US_EQ"]


def test_quote_age_limit_can_be_switched_off(make_harness):
    h = make_harness(max_quote_age_sec=0)
    h.quotes["NVDA_US_EQ"] = (199.95, 200.00)
    h.recs = [make_rec("NVDA_US_EQ")]
    h.quote_age_sec["NVDA_US_EQ"] = 15 * 60
    h.cycle()
    assert list(h.positions) == ["NVDA_US_EQ"]


def test_no_entry_when_score_is_below_the_threshold_or_pick_not_actionable(make_harness):
    h = make_harness()
    h.quotes.update({"NVDA_US_EQ": (199.95, 200.0), "AMD_US_EQ": (99.95, 100.0)})
    h.recs = [make_rec("NVDA_US_EQ", score=70.0), make_rec("AMD_US_EQ", score=95.0, actionable=False)]
    h.cycle()
    assert h.positions == {}


def test_slot_limits_per_market_sleeve(make_harness):
    h = make_harness()
    for sym in ("A_US_EQ", "B_US_EQ", "C_US_EQ"):
        h.open_position(sym, qty=2.0)
    h.quotes.update({"NVDA_US_EQ": (199.95, 200.0), "QQQ3_UK_EQ": (49.95, 50.0)})
    h.recs = [make_rec("NVDA_US_EQ"), make_rec("QQQ3_UK_EQ", price=50.0, atr=0.5)]
    h.cycle()
    # The 3 US slots are full, but the dedicated UK slot is free
    assert "NVDA_US_EQ" not in h.positions
    assert "QQQ3_UK_EQ" in h.positions
    assert len(h.positions) == 4


def test_cooldown_after_a_loss_blocks_re_entry(make_harness):
    h = make_harness()
    h.open_position("NVDA_US_EQ")
    asyncio.run(h.bot._manage_positions_intrabar({"NVDA_US_EQ": OrderBookSnapshot("NVDA_US_EQ", 150.0, 150.05, 150.0)}))
    assert "NVDA_US_EQ" not in h.positions and h.bot.order_executor.is_in_cooldown("NVDA_US_EQ")
    h.quotes["NVDA_US_EQ"] = (199.95, 200.0)
    h.recs = [make_rec("NVDA_US_EQ")]
    h.cycle()
    assert "NVDA_US_EQ" not in h.positions


# ----------------------------------------------------------------------------- exits
def test_intrabar_stop_loss_closes_the_position_and_journals_it_in_gbp(make_harness):
    h = make_harness()
    h.open_position("NVDA_US_EQ", price=200.0, atr=2.0, qty=10.0)
    crash = {"NVDA_US_EQ": OrderBookSnapshot("NVDA_US_EQ", 190.0, 190.05, 190.0)}
    asyncio.run(h.bot._manage_positions_intrabar(crash))

    assert h.positions == {}
    rec = h.journal()[-1]
    assert rec["symbol"] == "NVDA_US_EQ" and rec["reason"].startswith("Stop-Loss")
    assert rec["currency"] == "GBP" and rec["net_pnl"] < 0
    # 10 shares from 200 to ~190 is about -$100, or about -GBP 80, plus fees
    assert -90 < rec["net_pnl"] < -75
    assert rec["fx_rate_entry"] == pytest.approx(0.8)
    assert h.bot.order_executor.is_in_cooldown("NVDA_US_EQ")


def test_trailing_stop_ratchets_up_and_take_profit_extends_on_a_strong_trend(make_harness):
    h = make_harness()
    pos = h.open_position("NVDA_US_EQ", price=200.0, atr=2.0, qty=5.0)
    h.bot._latest_atr["NVDA_US_EQ"] = 2.0
    h.bot._trend_strong["NVDA_US_EQ"] = True
    start_stop = pos.stop_loss
    up = {"NVDA_US_EQ": OrderBookSnapshot("NVDA_US_EQ", 203.0, 203.05, 203.0)}  # +1.0R: trailing activates
    asyncio.run(h.bot._manage_positions_intrabar(up))
    assert pos.trailing_active and pos.stop_loss > start_stop and "NVDA_US_EQ" in h.positions
    target = pos.take_profit
    through_target = {"NVDA_US_EQ": OrderBookSnapshot("NVDA_US_EQ", target + 0.1, target + 0.15, target + 0.1)}
    asyncio.run(h.bot._manage_positions_intrabar(through_target))
    assert "NVDA_US_EQ" in h.positions and pos.tp_extensions == 1 and pos.take_profit > target


def test_end_of_day_flat_closes_uk_etps_and_weak_us_positions_but_keeps_strong_winners(make_harness):
    h = make_harness(now=UK_PRE_CLOSE)
    h.open_position("QQQ3_UK_EQ", price=50.0, atr=0.5, qty=20.0)
    # +2R, so only the "UK ETPs never stay overnight" rule (not the +1R test) can close it
    books = {"QQQ3_UK_EQ": OrderBookSnapshot("QQQ3_UK_EQ", 51.5, 51.55, 51.5)}
    asyncio.run(h.bot._apply_end_of_day_flat(books))
    assert "QQQ3_UK_EQ" not in h.positions, "UK 3x ETPs are never held overnight"
    assert "End-of-day flat" in h.journal()[-1]["reason"]

    h.now = US_PRE_CLOSE
    h.open_position("WEAK_US_EQ", price=100.0, atr=1.0, qty=5.0)
    h.open_position("WINNER_US_EQ", price=100.0, atr=1.0, qty=5.0)
    books = {
        "WEAK_US_EQ": OrderBookSnapshot("WEAK_US_EQ", 100.2, 100.25, 100.2),  # +0.13R
        "WINNER_US_EQ": OrderBookSnapshot("WINNER_US_EQ", 102.0, 102.05, 102.0),  # +1.3R
    }
    asyncio.run(h.bot._apply_end_of_day_flat(books))
    assert "WEAK_US_EQ" not in h.positions
    assert "WINNER_US_EQ" in h.positions, "a winner above +1R may be held overnight"


def test_circuit_breaker_flattens_everything_and_blocks_new_entries(make_harness):
    h = make_harness()
    h.open_position("NVDA_US_EQ", qty=10.0)
    h.quotes["NVDA_US_EQ"] = (199.95, 200.0)
    h.cycle()  # first cycle records the equity peak
    assert not h.bot.risk_manager.circuit_breaker_tripped

    h.bot.order_executor.paper_quote_balance -= 700.0  # ~7% of equity gone within 24 hours
    h.recs = [make_rec("AMD_US_EQ", price=100.0, atr=1.0)]
    h.quotes["AMD_US_EQ"] = (99.95, 100.0)
    h.cycle()
    assert h.bot.risk_manager.circuit_breaker_tripped
    assert h.positions == {}, "open positions are flattened"
    assert "AMD_US_EQ" not in h.positions, "no new entries while the breaker is tripped"
    assert "circuit breaker" in h.journal()[-1]["reason"].lower()


# ----------------------------------------------------------------------------- when not to trade
def test_no_entries_while_markets_are_closed(make_harness):
    h = make_harness(now=WEEKEND)
    h.quotes["NVDA_US_EQ"] = (199.95, 200.0)
    h.recs = [make_rec("NVDA_US_EQ")]
    h.cycle()
    assert h.positions == {}


def test_opening_bell_guard_defers_entries_and_rescans_the_same_candle(make_harness):
    h = make_harness(now=OPENING_BELL, enable_uk_etp_sleeve=False)
    h.quotes["NVDA_US_EQ"] = (199.95, 200.0)
    h.recs = [make_rec("NVDA_US_EQ")]
    h.cycle()
    assert h.positions == {}
    assert h.bot._last_scan_bar_ts is None, "the scan lock is released so the candle is re-evaluated after the bell"
    h.now = MID_SESSION
    h.cycle()
    assert "NVDA_US_EQ" in h.positions


def test_each_closed_candle_is_scanned_once(make_harness):
    h = make_harness()
    scans = []
    h.bot.screener.scan_universe = lambda positions, cache=None: scans.append(1) or []
    h.cycle()
    h.cycle()
    assert len(scans) == 1  # same candle: no second scan
    h.bar_ts = pd.Timestamp("2026-11-03 15:30", tz="UTC")
    h.cycle()
    assert len(scans) == 2  # a new candle triggers a new scan


def test_a_failed_probe_does_not_consume_the_candle(make_harness):
    h = make_harness()
    scans = []
    h.bot.screener.scan_universe = lambda positions, cache=None: scans.append(1) or []
    good = h.bot.data_handler.fetch_closed_ohlcv

    def broken(symbol, limit=None):
        raise RuntimeError("Empty OHLCV history")

    h.bot.data_handler.fetch_closed_ohlcv = broken
    h.cycle()
    assert scans == []  # nothing scanned, no crash
    h.bot.data_handler.fetch_closed_ohlcv = good
    h.cycle()
    assert len(scans) == 1  # the very next poll scans the candle that was missed


def test_a_crashing_cycle_does_not_stop_the_loop(make_harness, monkeypatch):
    import dashboard

    monkeypatch.setattr(dashboard, "start_background_dashboard", lambda cfg: None)  # don't bind port 8050
    h = make_harness()
    h.bot.config = replace(h.bot.config, poll_interval_sec=0)
    calls = []

    async def flaky_cycle():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("transient failure")
        h.bot.request_shutdown()

    h.bot.run_cycle = flaky_cycle
    asyncio.run(h.bot.run(run_once=False))
    assert len(calls) == 2, "the loop logs the failure and carries on to the next cycle"


# ----------------------------------------------------------------------------- heartbeat health
def test_heartbeat_health_follows_the_price_feed_only_while_markets_are_open(make_harness):
    import time

    h = make_harness()
    assert h.bot._data_is_fresh() is False, "markets are open and no price has arrived yet"
    h.cycle()
    assert h.bot._data_is_fresh() is True
    h.bot._last_data_ok = time.monotonic() - 700  # feed silent for ~12 minutes
    assert h.bot._data_is_fresh() is False

    h.now = WEEKEND  # nothing to scan on a weekend, so silence is normal
    assert h.bot._data_is_fresh() is True

    h.now = MID_SESSION
    h.bot.risk_manager.circuit_breaker_tripped = True  # trading is paused on purpose
    assert h.bot._data_is_fresh() is True


def test_a_failed_probe_does_not_refresh_the_health_clock(make_harness):
    h = make_harness()
    h.cycle()
    first = h.bot._last_data_ok

    def broken(symbol, limit=None):
        raise RuntimeError("Empty OHLCV history")

    h.bot.data_handler.fetch_closed_ohlcv = broken
    h.cycle()
    assert h.bot._last_data_ok == first


# ----------------------------------------------------------------------------- gap-rebound sleeve
def _daily(last_day: str, gap: float = 0.0, spy_gap: float = 0.0, periods: int = 60) -> pd.DataFrame:
    """Flat daily history ending on `last_day`, whose open gaps by `gap` from the previous close (and closes 3% up)."""
    idx = pd.bdate_range(end=last_day, periods=periods)
    close = pd.Series(100.0, index=idx)
    open_ = close.copy()
    open_.iloc[-1] = 100.0 * (1.0 + gap)
    close.iloc[-1] = open_.iloc[-1] * 1.03
    return pd.DataFrame({"open": open_, "close": close})


class GapHarness:
    """The orchestrator Harness with the gap-rebound sleeve on and synthetic daily history."""

    def __init__(self, make_harness, now=MID_SESSION, gap=-0.20, spy_gap=0.0, last_day="2026-11-02", **cfg):
        self.h = make_harness(now, enable_gap_rebound=True, **cfg)
        self.loads = 0
        self.frames = {
            "NVDA_US_EQ": _daily(last_day, gap=gap),
            "AAPL_US_EQ": _daily(last_day, gap=0.0),
            "SPY_US_EQ": _daily(last_day, gap=spy_gap),
        }
        self.h.quotes["NVDA_US_EQ"] = (79.95, 80.00)
        self.h.bot.screener.get_scan_universe = lambda: ["NVDA_US_EQ", "AAPL_US_EQ"]

        def load(symbols):
            self.loads += 1
            return self.frames

        self.h.bot._load_gap_daily = load


def test_gap_rebound_buys_the_stock_that_gapped_down_yesterday_and_tags_it(make_harness):
    g = GapHarness(make_harness)
    g.h.cycle()
    assert list(g.h.positions) == ["NVDA_US_EQ"]  # AAPL did not gap
    pos = g.h.positions["NVDA_US_EQ"]
    ctx = pos.entry_context
    assert ctx["strategy"] == "gap_rebound" and ctx["gap_pct"] == pytest.approx(-20.0, abs=0.1)
    assert ctx["exit_after"] == "2026-11-09"  # the 5th trading day after Monday 2 Nov
    assert pos.quantity * pos.entry_price * 0.8 == pytest.approx(0.15 * 10_000, rel=0.02)  # 15% of equity, in GBP
    assert pos.stop_loss == pytest.approx(pos.entry_price * 0.90, rel=0.001)  # the hard stop


def test_gap_rebound_is_off_by_default_and_waits_for_the_opening_bell(make_harness):
    h = make_harness()  # default config: sleeve disabled
    h.quotes["NVDA_US_EQ"] = (79.95, 80.0)
    h.bot.screener.get_scan_universe = lambda: ["NVDA_US_EQ"]
    h.bot._load_gap_daily = lambda s: {"NVDA_US_EQ": _daily("2026-11-02", -0.2), "SPY_US_EQ": _daily("2026-11-02")}
    h.cycle()
    assert h.positions == {}


def test_gap_rebound_waits_for_the_opening_bell_guard_to_end(make_harness):
    g = GapHarness(make_harness, now=OPENING_BELL)
    g.h.cycle()
    assert g.h.positions == {} and g.loads == 0  # no entry, and no scan either


def test_gap_rebound_ignores_stale_gaps_market_wide_selloffs_and_scans_once_a_day(make_harness):
    stale = GapHarness(make_harness, last_day="2026-10-30")  # newest daily bar is the Friday before: too old to trade
    stale.h.cycle()
    assert stale.h.positions == {}


def test_gap_rebound_skips_a_market_wide_selloff(make_harness):
    g = GapHarness(make_harness, spy_gap=-0.05)
    g.h.cycle()
    assert g.h.positions == {}


def test_gap_rebound_scans_once_per_session_and_caps_positions(make_harness):
    g = GapHarness(make_harness, gap_rebound_max_positions=1)
    g.frames["AAPL_US_EQ"] = _daily("2026-11-02", gap=-0.15)  # a second candidate
    g.h.quotes["AAPL_US_EQ"] = (79.95, 80.0)
    g.h.cycle()
    assert list(g.h.positions) == ["NVDA_US_EQ"]  # the deeper gap first, then the cap stops it
    g.h.cycle()
    assert g.loads == 1  # not rescanned in the same session


def test_gap_position_is_not_flattened_trailed_or_stopped_by_the_intraday_rules(make_harness):
    g = GapHarness(make_harness)
    g.h.cycle()
    entry = g.h.positions["NVDA_US_EQ"].entry_price
    g.h.now = US_PRE_CLOSE  # an intraday position below +1R would be sold here
    g.h.quotes["NVDA_US_EQ"] = (entry - 0.55, entry - 0.50)
    g.h.cycle()
    assert "NVDA_US_EQ" in g.h.positions
    g.h.quotes["NVDA_US_EQ"] = (entry * 1.2, entry * 1.2 + 0.05)  # far above any intraday take-profit
    g.h.cycle()
    pos = g.h.positions["NVDA_US_EQ"]
    assert pos.stop_loss == pytest.approx(entry * 0.90, rel=0.001) and not pos.trailing_active


def test_gap_position_exits_on_the_hard_stop(make_harness):
    g = GapHarness(make_harness)
    g.h.cycle()
    entry = g.h.positions["NVDA_US_EQ"].entry_price
    g.h.quotes["NVDA_US_EQ"] = (entry * 0.85, entry * 0.85 + 0.05)
    g.h.cycle()
    assert g.h.positions == {}
    rows = g.h.journal()
    assert "hard stop" in rows[-1]["reason"] and rows[-1]["entry_context"]["strategy"] == "gap_rebound"


def test_gap_position_is_held_until_the_close_of_its_exit_day(make_harness):
    g = GapHarness(make_harness)
    g.h.cycle()
    entry = g.h.positions["NVDA_US_EQ"].entry_price
    g.h.quotes["NVDA_US_EQ"] = (entry - 0.05, entry)
    g.h.now = datetime(2026, 11, 6, 20, 52, tzinfo=UTC)  # the day before the exit day, near the close
    g.h.cycle()
    assert "NVDA_US_EQ" in g.h.positions
    g.h.now = datetime(2026, 11, 9, 15, 30, tzinfo=UTC)  # exit day, mid-session: not yet
    g.h.cycle()
    assert "NVDA_US_EQ" in g.h.positions
    g.h.now = datetime(2026, 11, 9, 20, 52, tzinfo=UTC)  # exit day, last minutes
    g.h.cycle()
    assert g.h.positions == {}
    assert "5-day hold complete" in g.h.journal()[-1]["reason"]


def test_gap_position_ignores_a_bearish_intraday_exit_signal(make_harness):
    g = GapHarness(make_harness)
    g.h.cycle()
    entry = g.h.positions["NVDA_US_EQ"].entry_price
    rec = make_rec("NVDA_US_EQ", actionable=False, price=entry)
    g.h.recs = [replace(rec, signal=replace(rec.signal, action=SignalAction.SELL, is_exit=True, reason="EMA crossed down"))]
    g.h.bar_ts = pd.Timestamp("2026-11-03 15:30", tz="UTC")  # a new candle, so the screener result is acted on
    g.h.now = datetime(2026, 11, 3, 15, 50, tzinfo=UTC)
    g.h.cycle()
    assert "NVDA_US_EQ" in g.h.positions  # an intraday position would have been sold on this signal


def test_gap_positions_do_not_use_the_intraday_slots(make_harness):
    # two intraday slots in total; the two gap positions must not eat into them
    g = GapHarness(make_harness, max_open_positions=2, max_us_positions=2, gap_rebound_max_positions=2)
    g.frames["AAPL_US_EQ"] = _daily("2026-11-02", gap=-0.15)
    g.h.quotes["AAPL_US_EQ"] = (79.95, 80.0)
    for sym in ("MSFT_US_EQ", "AMD_US_EQ"):
        g.h.quotes[sym] = (199.95, 200.0)
    g.h.recs = [make_rec("MSFT_US_EQ"), make_rec("AMD_US_EQ", score=88.0)]
    g.h.cycle()
    assert set(g.h.positions) == {"NVDA_US_EQ", "AAPL_US_EQ", "MSFT_US_EQ", "AMD_US_EQ"}
    assert sum(1 for p in g.h.positions.values() if p.entry_context.get("strategy") == "gap_rebound") == 2


def test_full_intraday_slots_do_not_block_a_gap_entry(make_harness):
    g = GapHarness(make_harness, max_open_positions=2, max_us_positions=2)
    g.h.open_position("MSFT_US_EQ")
    g.h.open_position("AMD_US_EQ")
    g.h.cycle()
    assert "NVDA_US_EQ" in g.h.positions and len(g.h.positions) == 3


def _skipped(h):
    path = h.tmp / "logs" / "skipped_picks.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_picks_that_are_not_traded_are_logged_with_the_reason(make_harness):
    h = make_harness(max_open_positions=1, max_us_positions=1)
    h.open_position("AAPL_US_EQ")  # the only slot is taken
    h.quotes["NVDA_US_EQ"] = (199.95, 200.0)
    h.recs = [make_rec("NVDA_US_EQ", score=90.0), make_rec("MSFT_US_EQ", score=40.0)]
    h.cycle()
    rows = _skipped(h)
    by_symbol = {r["symbol"]: r for r in rows}
    assert by_symbol["NVDA_US_EQ"]["reason"] == "no_slot"
    assert by_symbol["MSFT_US_EQ"]["reason"] == "regime_score" and "40 <" in by_symbol["MSFT_US_EQ"]["detail"]
    nv = by_symbol["NVDA_US_EQ"]
    assert nv["price"] == pytest.approx(200.0) and nv["stop_loss"] < nv["price"] < nv["take_profit"]  # replayable


def test_a_traded_pick_is_not_logged_as_skipped(make_harness):
    h = make_harness()
    h.quotes["NVDA_US_EQ"] = (199.95, 200.0)
    h.recs = [make_rec("NVDA_US_EQ")]
    h.cycle()
    assert "NVDA_US_EQ" in h.positions and _skipped(h) == []


def test_a_restart_keeps_gap_positions_and_their_tags(make_harness):
    g = GapHarness(make_harness)
    g.h.cycle()
    before = g.h.positions["NVDA_US_EQ"]
    restarted = TradingBot(g.h.cfg)  # same state file, as after a service restart
    after = restarted.order_executor.positions.get("NVDA_US_EQ")
    assert after is not None
    assert after.entry_context["strategy"] == "gap_rebound" and after.entry_context["exit_after"] == "2026-11-09"
    assert after.stop_loss == pytest.approx(before.stop_loss) and after.quantity == pytest.approx(before.quantity)


# ----------------------------------------------------------------------------- intraday entries switch
def test_intraday_entries_off_buys_nothing_on_a_strong_pick(make_harness):
    h = make_harness(enable_intraday_entries=False)
    h.quotes["NVDA_US_EQ"] = (199.95, 200.00)
    h.recs = [make_rec("NVDA_US_EQ")]
    h.cycle()
    assert h.positions == {}


def test_intraday_entries_off_still_closes_an_open_position_at_its_stop(make_harness):
    h = make_harness(enable_intraday_entries=False)
    h.open_position("NVDA_US_EQ")
    asyncio.run(h.bot._manage_positions_intrabar({"NVDA_US_EQ": OrderBookSnapshot("NVDA_US_EQ", 150.0, 150.05, 150.0)}))
    assert "NVDA_US_EQ" not in h.positions


def test_intraday_entries_off_leaves_the_gap_sleeve_buying(make_harness):
    g = GapHarness(make_harness, enable_intraday_entries=False)
    g.h.recs = [make_rec("AAPL_US_EQ")]
    g.h.quotes["AAPL_US_EQ"] = (199.95, 200.00)
    g.h.cycle()
    assert list(g.h.positions) == ["NVDA_US_EQ"]  # the gap trade, not the screener pick
    assert g.h.positions["NVDA_US_EQ"].entry_context["strategy"] == "gap_rebound"
