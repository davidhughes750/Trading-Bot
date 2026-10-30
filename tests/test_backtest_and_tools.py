"""Tests for the backtester, log analysis, and shared helpers (no network access)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bot.analysis import analyze_ai_decisions, analyze_journal, analyze_scans
from bot.backtest import Backtester, simulate_bracket
from bot.config import Config
from bot.market_calendar import in_opening_window, in_pre_close_window, is_session_open
from bot.models import OrderBookSnapshot, Side, Signal, SignalAction
from bot.risk_manager import RiskManager, has_open_slot, required_min_score
from bot.strategy_engine import StrategyEngine
from bot.utils import atomic_write_json


def us_session_bars(days: int, start: str = "2026-09-01", seed: int = 1, drift: float = 0.0004) -> pd.DataFrame:
    """15m regular-session bars (09:30-16:00 ET) on weekdays with a gentle trend and noise."""
    rng = np.random.default_rng(seed)
    stamps = []
    for d in pd.bdate_range(start, periods=days):
        opens = pd.date_range(f"{d.date()} 09:30", f"{d.date()} 15:45", freq="15min", tz="America/New_York")
        stamps.extend(opens.tz_convert("UTC"))
    n = len(stamps)
    steps = drift + rng.normal(0, 0.003, n)
    close = 100.0 * np.exp(np.cumsum(steps))
    open_ = np.concatenate([[100.0], close[:-1]])
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.0015, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.0015, n)))
    volume = rng.integers(800, 2500, n).astype(float)
    return pd.DataFrame({"timestamp": stamps, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


def test_simulate_bracket_outcomes():
    bars = pd.DataFrame({
        "open": [100.0, 101.0, 103.0],
        "high": [101.5, 103.5, 104.0],
        "low": [99.5, 100.5, 102.0],
        "close": [101.0, 103.0, 103.5],
    })
    hit = simulate_bracket(bars, entry_price=100.0, stop_loss=98.0, take_profit=103.0)
    assert hit["outcome"] == "target" and hit["r_multiple"] == pytest.approx(1.5)

    stop = simulate_bracket(bars, entry_price=100.0, stop_loss=99.6, take_profit=110.0)
    assert stop["outcome"] == "stop" and stop["r_multiple"] == pytest.approx(-1.0)

    gap = pd.DataFrame({"open": [95.0], "high": [96.0], "low": [94.0], "close": [95.5]})
    assert simulate_bracket(gap, 100.0, 98.0, 104.0)["exit_price"] == pytest.approx(95.0)

    timeout = simulate_bracket(bars, entry_price=100.0, stop_loss=90.0, take_profit=120.0)
    assert timeout["outcome"] == "timeout" and timeout["exit_price"] == pytest.approx(103.5)


def test_backtester_runs_and_respects_limits():
    cfg = Config(
        execution_mode="paper",
        account_currency="GBP",
        min_recommendation_score=0.0,
        min_rvol_for_entry=0.0,
        max_open_positions=2,
        max_us_positions=2,
        market_regime_filter=False,
        enable_uk_etp_sleeve=False,
        min_target_move_pct_fx=0.0,  # synthetic prices are too calm to clear the FX-fee hurdle
    )
    data = {f"S{i}_US_EQ": us_session_bars(25, seed=i) for i in range(4)}
    bt = Backtester(cfg, fx_rates={"USD": 0.8}, starting_equity=1_000.0)
    result = bt.run(data)

    assert result.trades, "expected the permissive config to trade"
    s = result.summary()
    assert s["trades"] == len(result.trades)
    assert result.account_currency == "GBP"
    # Fees: 0.15% per leg on US trades, recorded in GBP
    assert all(t.fees > 0 for t in result.trades)
    # Never more than 2 positions open at once
    events = sorted(
        [(t.entry_time, 1) for t in result.trades] + [(t.exit_time, -1) for t in result.trades],
        key=lambda e: (e[0], e[1]),
    )
    open_now, peak = 0, 0
    for _, delta in events:
        open_now += delta
        peak = max(peak, open_now)
    assert peak <= 2
    # Entries fill at a bar open within regular hours, never in the first 15 minutes
    for t in result.trades:
        entry = datetime.fromisoformat(t.entry_time)
        assert is_session_open("SPY_US_EQ", entry)
    # Equity bookkeeping is consistent with the trade list (net P&L is rounded to pennies per trade)
    assert result.equity_curve[-1][1] == pytest.approx(
        1_000.0 + sum(t.net_pnl for t in result.trades), abs=0.01 * len(result.trades)
    )
    report = result.format_report()
    assert "BACKTEST RESULTS" in report and "By entry score" in report


def test_analysis_reports_with_injected_history():
    cfg = Config(execution_mode="paper")
    df = us_session_bars(5, seed=3)
    hist = {"AAA_US_EQ": df}
    scans = [
        {"candle_ts": str(df["timestamp"].iloc[i]), "symbol": "AAA_US_EQ", "score": 50 + i % 40,
         "actionable": i % 3 == 0, "atr": 0.5}
        for i in range(10, 60)
    ]
    out = analyze_scans(cfg, scans, history=hist)
    assert "Screener score vs what happened next" in out and "ALL" in out

    i = 20
    px = float(df["close"].iloc[i])
    ai = [
        {"candle_ts": str(df["timestamp"].iloc[i]), "symbol": "AAA_US_EQ", "decision": d,
         "reference_price": px, "stop_loss": px - 1.0, "take_profit": px + 1.5}
        for d in ("APPROVE", "VETO")
    ]
    out = analyze_ai_decisions(cfg, ai, history=hist)
    assert "APPROVE" in out and "VETO" in out

    journal = [
        {"net_pnl": 5.0, "r_multiple": 1.2, "fee_paid": 0.3, "currency": "GBP", "entry_slippage_pct": 0.02,
         "exit_slippage_pct": 0.05, "exit_price_source": "broker_fill", "outcome_tag": "WIN"},
        {"net_pnl": -3.0, "r_multiple": -1.0, "fee_paid": 0.3, "currency": "GBP", "outcome_tag": "STOPPED_OUT"},
    ]
    out = analyze_journal(journal)
    assert "2 trades" in out and "broker_fill 1" in out


def test_shared_slot_and_score_rules():
    cfg = Config(execution_mode="paper", max_open_positions=4, max_us_positions=3, max_uk_positions=1,
                 min_recommendation_score=76.0)
    assert has_open_slot(cfg, "NVDA_US_EQ", ["A_US_EQ", "B_US_EQ"])
    assert not has_open_slot(cfg, "NVDA_US_EQ", ["A_US_EQ", "B_US_EQ", "C_US_EQ"])
    assert not has_open_slot(cfg, "QQQ3_UK_EQ", ["3LUS_UK_EQ"])
    assert required_min_score(cfg, "QQQS_UK_EQ", "BEARISH", 86.0) == 76.0
    assert required_min_score(cfg, "QQQS_UK_EQ", "BULLISH", 76.0) == 80.0
    assert required_min_score(cfg, "NVDA_US_EQ", "CAUTIOUS", 80.0) == 80.0


def test_session_windows():
    utc = timezone.utc
    assert in_opening_window("NVDA_US_EQ", datetime(2026, 10, 26, 13, 40, tzinfo=utc), 15)  # 09:40 ET
    assert not in_opening_window("NVDA_US_EQ", datetime(2026, 10, 26, 13, 50, tzinfo=utc), 15)
    assert in_pre_close_window("NVDA_US_EQ", datetime(2026, 10, 26, 19, 55, tzinfo=utc), 10)  # 15:55 ET
    assert not is_session_open("NVDA_US_EQ", datetime(2026, 11, 26, 15, 0, tzinfo=utc))  # Thanksgiving
    assert is_session_open("QQQ3_UK_EQ", datetime(2026, 10, 26, 9, 0, tzinfo=utc))
    assert not is_session_open("QQQ3_UK_EQ", datetime(2026, 10, 31, 9, 0, tzinfo=utc))  # Saturday


def test_atomic_write_replaces_file_and_leaves_no_temp(tmp_path: Path):
    target = tmp_path / "state.json"
    atomic_write_json(target, {"a": 1})
    atomic_write_json(target, {"a": 2})
    assert json.loads(target.read_text()) == {"a": 2}
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_unverified_spread_is_flagged_and_can_be_required():
    sig = Signal(
        symbol="AAPL_US_EQ", action=SignalAction.BUY, candle_timestamp="2026-01-01T00:00:00Z",
        close_price=200.0, ema_fast=201.0, ema_slow=200.0, rsi=60.0, atr=4.0,
        reason="t", target_side=Side.LONG,
    )
    ob = OrderBookSnapshot(symbol="AAPL_US_EQ", bid=199.98, ask=200.02, last=200.0, spread_verified=False)
    lenient = Config(execution_mode="paper")
    plan = RiskManager(lenient, StrategyEngine(lenient)).validate_and_build_trade_plan(
        signal=sig, order_book=ob, total_equity=10_000.0, available_quote=10_000.0, open_positions_count=0
    )
    assert plan is not None and plan.spread_verified is False

    strict = Config(execution_mode="paper", require_verified_spread=True)
    assert RiskManager(strict, StrategyEngine(strict)).validate_and_build_trade_plan(
        signal=sig, order_book=ob, total_equity=10_000.0, available_quote=10_000.0, open_positions_count=0
    ) is None
