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
