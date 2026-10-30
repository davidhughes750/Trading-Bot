"""Unit and integration tests for the Trading 212 automated trading bot."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pytest

from bot.config import Config
from bot.data_handler import DataHandler
from bot.models import OrderBookSnapshot, Side, Signal, SignalAction, TradePlan
from bot.order_executor import OrderExecutor
from bot.risk_manager import RiskManager
from bot.screener import StockScreener
from bot.strategy_engine import StrategyEngine
from bot.t212_client import Trading212Client


def make_synthetic_ohlcv(n: int = 120) -> pd.DataFrame:
    """Build deterministic OHLCV data for indicator and signal verification."""
    timestamps = pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC")
    prices = np.linspace(100.0, 100.0, n).tolist()
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": prices,
            "high": [p + 1.0 for p in prices],
            "low": [p - 1.0 for p in prices],
            "close": prices,
            "volume": [1000.0] * n,
        }
    )


def test_config_and_t212_urls():
    cfg_demo = Config(execution_mode="demo", t212_api_key="test_demo_key")
    cfg_demo.validate()
    assert cfg_demo.resolved_t212_base_url == "https://demo.trading212.com/api/v0"

    cfg_live = Config(
        execution_mode="live",
        live_trading_confirmed=True,
        t212_api_key="test_live_key",
    )
    cfg_live.validate()
    assert cfg_live.resolved_t212_base_url == "https://live.trading212.com/api/v0"

    # Live mode without confirmation flag must fail
    with pytest.raises(ValueError, match="LIVE_TRADING_CONFIRMED"):
        Config(execution_mode="live", live_trading_confirmed=False, t212_api_key="k").validate()

    # Trading 212 Invest/ISA cannot short sell
    with pytest.raises(ValueError, match="ALLOW_SHORT=false"):
        Config(execution_mode="demo", t212_api_key="k", allow_short=True).validate()


def test_t212_ticker_resolution():
    from bot.t212_client import Trading212Client

    assert DataHandler.resolve_ticker_pair("AAPL_US_EQ") == ("AAPL_US_EQ", "AAPL")
    assert DataHandler.resolve_ticker_pair("NVDA_US_EQ") == ("NVDA_US_EQ", "NVDA")
    assert DataHandler.resolve_ticker_pair("VUAG_UK_EQ:VUAG.L") == ("VUAG_UK_EQ", "VUAG.L")
    assert DataHandler.resolve_ticker_pair("SPY") == ("SPY_US_EQ", "SPY")
    assert DataHandler.resolve_ticker_pair("DEAC_US_EQ") == ("DKNG_US_EQ", "DKNG")
    assert DataHandler.resolve_ticker_pair("AAXN_US_EQ") == ("AXON_US_EQ", "AXON")
    assert Trading212Client.to_broker_ticker("DKNG_US_EQ") == "DEAC_US_EQ"
    assert Trading212Client.to_broker_ticker("AXON_US_EQ") == "AAXN_US_EQ"
    assert Trading212Client.from_broker_ticker("DEAC_US_EQ") == "DKNG_US_EQ"
    assert Trading212Client.from_broker_ticker("AAXN_US_EQ") == "AXON_US_EQ"


def test_compute_indicators_and_signals():
    cfg = Config(execution_mode="paper", allow_short=False)
    dh = DataHandler(cfg)
    se = StrategyEngine(cfg)

    df = dh.compute_indicators(make_synthetic_ohlcv(120))
    assert {"ema_fast", "ema_slow", "rsi", "atr"}.issubset(df.columns)
    assert float(df["atr"].iloc[-1]) == pytest.approx(2.0, rel=1e-2)

    df_buy = df.iloc[-2:].copy()
    df_buy.loc[df_buy.index[0], ["ema_fast", "ema_slow", "rsi", "atr", "close"]] = [
        199.5,
        200.0,
        52.0,
        2.0,
        200.0,
    ]
    df_buy.loc[df_buy.index[1], ["ema_fast", "ema_slow", "rsi", "atr", "close"]] = [
        200.5,
        200.0,
        58.0,
        2.0,
        202.0,
    ]
    sig_buy = se.generate_signal("AAPL_US_EQ", df_buy)
    assert sig_buy.action == SignalAction.BUY
    assert sig_buy.target_side == Side.LONG


def test_risk_manager_sizing_spread_and_circuit_breaker():
    cfg = Config(
        execution_mode="paper",
        risk_per_trade_pct=0.01,
        max_open_positions=1,
        max_daily_drawdown_pct=0.05,
        max_spread_pct=0.0015,
    )
    se = StrategyEngine(cfg)
    rm = RiskManager(cfg, se)

    sig = Signal(
        symbol="AAPL_US_EQ",
        action=SignalAction.BUY,
        candle_timestamp="2026-01-01T00:00:00Z",
        close_price=200.0,
        ema_fast=201.0,
        ema_slow=200.0,
        rsi=60.0,
        atr=4.0,  # 1.5 * 4.0 = $6.00 stop distance -> $100 risk / $6 = 16.6667 shares ($3,333 notional)
        reason="Test crossover",
        target_side=Side.LONG,
    )
    ob_tight = OrderBookSnapshot(symbol="AAPL_US_EQ", bid=199.90, ask=200.00, last=199.95)
    plan = rm.validate_and_build_trade_plan(
        signal=sig,
        order_book=ob_tight,
        total_equity=10_000.0,
        available_quote=10_000.0,
        open_positions_count=0,
    )
    assert plan is not None
    assert plan.risk_amount_usd == pytest.approx(100.0, rel=1e-4)  # Strictly 1% of $10,000
    assert plan.stop_loss == pytest.approx(200.0 - 6.0)
    assert plan.take_profit == pytest.approx(200.0 + 8.0)
    assert plan.quantity == pytest.approx(100.0 / 6.0)

    # Spread guard rejects when spread > 0.15%
    ob_wide = OrderBookSnapshot(symbol="AAPL_US_EQ", bid=199.50, ask=200.00, last=199.75)  # ~0.25% spread
    assert (
        rm.validate_and_build_trade_plan(
            signal=sig,
            order_book=ob_wide,
            total_equity=10_000.0,
            available_quote=10_000.0,
            open_positions_count=0,
        )
        is None
    )

    # 5% 24-hour drawdown circuit breaker trips and blocks trades
    t0 = datetime.now(timezone.utc)
    rm.record_equity(10_000.0, now=t0)
    rm.record_equity(9_450.0, now=t0 + timedelta(hours=3))
    assert rm.circuit_breaker_tripped is True


def test_t212_demo_order_execution_and_trailing_stop(tmp_path: Path):
    state_file = tmp_path / "t212_state.json"
    cfg = Config(
        execution_mode="demo",
        t212_api_key="demo_key",
        t212_api_secret="demo_secret",
        state_file=str(state_file),
    )
    se = StrategyEngine(cfg)
    rm = RiskManager(cfg, se)

    # Mock Trading212Client to verify positive buy quantity & negative sell quantity
    mock_t212 = MagicMock(spec=Trading212Client)
    mock_t212.place_limit_order.return_value = {"id": "t212-ord-101", "status": "FILLED"}
    mock_t212.get_position.return_value = {
        "ticker": "NVDA_US_EQ",
        "quantity": 16.6667,
        "averagePrice": 120.0,
        "currentPrice": 120.0,
    }
    mock_t212.place_market_order.return_value = {"id": "t212-ord-102", "status": "FILLED"}

    oe = OrderExecutor(cfg, t212_client=mock_t212)

    sig = Signal(
        symbol="NVDA_US_EQ",
        action=SignalAction.BUY,
        candle_timestamp="2026-01-01T00:00:00Z",
        close_price=120.0,
        ema_fast=121.0,
        ema_slow=120.0,
        rsi=62.0,
        atr=4.0,  # SL = 120 - 6 = 114 (1R = $6), TP = 120 + 8 = 128
        reason="Bullish crossover",
        target_side=Side.LONG,
    )
    ob = OrderBookSnapshot(symbol="NVDA_US_EQ", bid=119.95, ask=120.00, last=119.98)
    plan = rm.validate_and_build_trade_plan(
        signal=sig,
        order_book=ob,
        total_equity=10_000.0,
        available_quote=10_000.0,
        open_positions_count=0,
    )
    assert plan is not None

    mock_notifier = MagicMock()
    mock_notifier.enabled = True
    oe.telegram_notifier = mock_notifier

    pos = oe.execute_entry(plan, ob)
    assert pos is not None
    mock_t212.place_limit_order.assert_called_once_with(
        ticker="NVDA_US_EQ",
        signed_quantity=16.6667,  # Positive quantity for BUY
        limit_price=120.0,
        time_validity="DAY",
    )
    mock_notifier.send_trade_opened_alert.assert_called_once()
    open_alert_kwargs = mock_notifier.send_trade_opened_alert.call_args[1]
    assert open_alert_kwargs["symbol"] == "NVDA_US_EQ"
    assert "risk_usd" in open_alert_kwargs
    assert open_alert_kwargs["risk_usd"] > 0

    # Move price to +1.0R ($126): trailing stop activates and locks at the Fee-Plus Breakeven Floor ($120 * 1.0035 = $120.42)
    action, _ = se.evaluate_position_exit_and_trail(pos, current_price=126.0, current_atr=4.0)
    assert action == SignalAction.HOLD
    assert pos.trailing_active is True
    assert pos.stop_loss == pytest.approx(120.0 * 1.0035)

    # Pullback to $119.50 triggers the trailing stop -> sends negative quantity market SELL to Trading 212
    action, reason = se.evaluate_position_exit_and_trail(pos, current_price=119.50, current_atr=4.0)
    assert action == SignalAction.SELL

    ob_exit = OrderBookSnapshot(symbol="NVDA_US_EQ", bid=119.50, ask=119.55, last=119.52)
    res = oe.execute_exit(pos, ob_exit, reason)
    assert res is not None and res.success
    mock_t212.place_market_order.assert_called_once_with(
        ticker="NVDA_US_EQ",
        signed_quantity=-16.6667,  # Negative quantity for SELL on Trading 212
    )
    mock_notifier.send_trade_closed_alert.assert_called_once()
    alert_kwargs = mock_notifier.send_trade_closed_alert.call_args[1]
    assert alert_kwargs["symbol"] == "NVDA_US_EQ"
    assert "held_minutes" in alert_kwargs
    assert isinstance(alert_kwargs["held_minutes"], int)


def test_stock_screener_scoring_and_ranking():
    from bot.screener import StockScreener

    cfg = Config(execution_mode="paper", enable_screener=True, trade_top_recommendation=True)
    dh = DataHandler(cfg)
    se = StrategyEngine(cfg)
    screener = StockScreener(cfg, dh, se)

    # Default universe should include 25 high-beta Trading 212 momentum equities
    universe = screener.get_scan_universe()
    assert len(universe) >= 25
    assert "MSTR_US_EQ" in universe
    assert "PLTR_US_EQ" in universe

    # Build a strong uptrend DataFrame and verify high score & actionable BUY recommendation
    df_base = dh.compute_indicators(make_synthetic_ohlcv(120))
    df_bull = df_base.copy()
    df_bull.loc[df_bull.index[-11], "close"] = 100.0
    df_bull.loc[df_bull.index[-2], ["close", "ema_fast", "ema_slow", "rsi", "atr", "volume"]] = [
        104.0, 102.5, 101.0, 58.0, 1.5, 1200.0
    ]
    df_bull.loc[df_bull.index[-1], ["close", "ema_fast", "ema_slow", "rsi", "atr", "volume"]] = [
        105.0, 103.2, 101.2, 61.0, 1.5, 2000.0
    ]

    rec_bull = screener.evaluate_dataframe("AMZN_US_EQ", df_bull)
    assert rec_bull.score >= 80.0
    assert rec_bull.rating == "STRONG BUY"
    assert rec_bull.actionable is True
    assert rec_bull.signal.action == SignalAction.BUY

    leaderboard = screener.format_leaderboard([rec_bull], top_n=5)
    assert "AMZN_US_EQ" in leaderboard
    assert "STRONG BUY" in leaderboard


def test_catch_up_sync_adopts_missing_t212_positions(tmp_path: Path):
    state_file = tmp_path / "t212_state.json"
    cfg = Config(
        execution_mode="demo",
        t212_api_key="demo_key",
        t212_api_secret="demo_secret",
        state_file=str(state_file),
    )
    mock_t212 = MagicMock(spec=Trading212Client)
    mock_t212.get_portfolio.return_value = [
        {
            "ticker": "TSLA_US_EQ",
            "quantity": 0.6791,
            "averagePrice": 368.10,
            "currentPrice": 370.50,
        },
        {
            "ticker": "MSTR_US_EQ",
            "quantity": 0.5500,
            "averagePrice": 410.00,
            "currentPrice": 415.00,
        },
        {
            "ticker": "SHOP_US_EQ",
            "quantity": 2.1500,
            "averagePrice": 115.00,
            "currentPrice": 116.80,
        },
    ]

    oe = OrderExecutor(cfg, t212_client=mock_t212)
    assert "SHOP_US_EQ" not in oe.positions

    # Run two-way catch-up sync with an ATR lookup
    oe.sync_positions_with_t212(atr_lookup=lambda sym: 2.0)

    assert set(oe.positions.keys()) == {"TSLA_US_EQ", "MSTR_US_EQ", "SHOP_US_EQ"}
    shop_pos = oe.positions["SHOP_US_EQ"]
    assert shop_pos.quantity == pytest.approx(2.15)
    assert shop_pos.entry_price == pytest.approx(115.00)
    assert shop_pos.stop_loss == pytest.approx(115.00 - 1.5 * 2.0)
    assert shop_pos.take_profit == pytest.approx(115.00 + 2.0 * 2.0)
    assert shop_pos.highest_price == pytest.approx(116.80)


def test_ai_portfolio_manager_entry_vetting_and_slot_rotation(tmp_path: Path):
    from bot.ai_manager import AIPortfolioManager
    from bot.models import Position, StockRecommendation

    ai_file = tmp_path / "ai_decisions.json"
    cfg = Config(
        execution_mode="paper",
        enable_ai_manager=True,
        ai_decisions_file=str(ai_file),
    )
    ai = AIPortfolioManager(cfg)

    sig = Signal(
        symbol="NVDA_US_EQ",
        action=SignalAction.BUY,
        candle_timestamp="2026-01-01T00:00:00Z",
        close_price=220.0,
        ema_fast=218.0,
        ema_slow=215.0,
        rsi=61.0,
        atr=3.0,
        reason="Bullish momentum",
        target_side=Side.LONG,
    )
    pick = StockRecommendation(
        symbol="NVDA_US_EQ",
        score=86.0,
        rating="STRONG BUY",
        actionable=True,
        close_price=220.0,
        ema_fast=218.0,
        ema_slow=215.0,
        rsi=61.0,
        atr=3.0,
        rvol=2.1,
        roc_10_pct=2.4,
        suggested_stop_loss=215.5,
        suggested_take_profit=226.0,
        thesis="Strong uptrend; Sweet-spot RSI",
        signal=sig,
    )

    # 1. Clean news -> APPROVE
    ai.fetch_recent_headlines = lambda sym, max_items=5: ["NVIDIA raises guidance on strong AI demand (Reuters)"]
    dec1 = ai.evaluate_entry_candidate(pick, {}, total_equity=500.0)
    assert dec1.decision == "APPROVE"
    assert dec1.size_multiplier == 1.0

    # 2. Bearish binary headline -> VETO
    ai.fetch_recent_headlines = lambda sym, max_items=5: ["Company announces secondary offering and share dilution"]
    dec2 = ai.evaluate_entry_candidate(pick, {}, total_equity=500.0)
    assert dec2.decision == "VETO"

    # 3. Slot rotation when a held position has deteriorated (< 50 score) and new pick is >= 80
    ai.fetch_recent_headlines = lambda sym, max_items=5: ["Strong institutional breakout"]
    stale_pos = Position(
        symbol="SHOP_US_EQ",
        side=Side.LONG,
        quantity=2.0,
        entry_price=115.0,
        initial_stop_loss=112.0,
        stop_loss=112.0,
        take_profit=119.0,
        atr_at_entry=2.0,
        entry_order_id="ord-shop-1",
    )
    stale_rec = StockRecommendation(
        symbol="SHOP_US_EQ",
        score=38.0,
        rating="AVOID",
        actionable=False,
        close_price=114.8,
        ema_fast=114.9,
        ema_slow=115.2,
        rsi=44.0,
        atr=2.0,
        rvol=0.7,
        roc_10_pct=-0.8,
        suggested_stop_loss=111.8,
        suggested_take_profit=118.8,
        thesis="Weak RSI",
        signal=sig,
    )
    rot = ai.evaluate_slot_rotation(
        new_pick=pick,
        open_positions={"SHOP_US_EQ": stale_pos},
        all_recommendations=[pick, stale_rec],
        latest_prices={"SHOP_US_EQ": 114.8},
    )
    assert rot is not None
    assert rot.decision == "ROTATE"
    assert rot.replace_symbol == "SHOP_US_EQ"

    # 4. Prevent Rotate-then-Veto trap: block rotating out of SHOP into RIOT when CLSK (same crypto niche) is already held
    clsk_pos = Position(
        symbol="CLSK_US_EQ",
        side=Side.LONG,
        quantity=10.0,
        entry_price=8.0,
        initial_stop_loss=7.6,
        stop_loss=8.2,
        take_profit=9.0,
        atr_at_entry=0.3,
        entry_order_id="ord-clsk-1",
        trailing_active=True,
    )
    riot_pick = StockRecommendation(
        symbol="RIOT_US_EQ",
        score=85.0,
        rating="STRONG BUY",
        actionable=True,
        close_price=13.6,
        ema_fast=13.4,
        ema_slow=13.2,
        rsi=61.0,
        atr=0.35,
        rvol=1.9,
        roc_10_pct=1.5,
        suggested_stop_loss=13.1,
        suggested_take_profit=14.5,
        thesis="Strong uptrend",
        signal=sig,
    )
    rot_blocked = ai.evaluate_slot_rotation(
        new_pick=riot_pick,
        open_positions={"SHOP_US_EQ": stale_pos, "CLSK_US_EQ": clsk_pos},
        all_recommendations=[riot_pick, stale_rec],
        latest_prices={"SHOP_US_EQ": 114.8, "CLSK_US_EQ": 8.3},
    )
    assert rot_blocked is not None
    assert rot_blocked.decision == "HOLD"



def test_dashboard_snapshot_serializes_cleanly(tmp_path: Path):
    from dashboard import build_dashboard_snapshot

    cfg = Config(
        execution_mode="paper",
        state_file=str(tmp_path / "state.json"),
        log_file=str(tmp_path / "bot.log"),
        ai_decisions_file=str(tmp_path / "ai.json"),
    )
    snap = build_dashboard_snapshot(cfg)
    assert snap["version"] == "2.6.0"
    assert "portfolio" in snap
    assert "positions" in snap
    assert "ai_manager" in snap
    assert "screener" in snap
    assert "activity" in snap
    assert "market_session" in snap
    assert "seconds_to_open" in snap["market_session"]
    assert "uk_market_session" in snap
    assert "seconds_to_open" in snap["uk_market_session"]
    assert "total_closed_seconds" in snap["uk_market_session"]
    assert snap["uk_market_session"]["state"] in ("MARKET OPEN", "MARKET CLOSED", "PRE-MARKET", "WEEKEND (CLOSED)", "OPENING GUARD")
    assert snap["uk_market_session"]["badge"] in ("GREEN", "AMBER")
    assert isinstance(snap["uk_market_session"]["is_open"], bool)
    assert "gates" in snap and len(snap["gates"]) == 4
    assert "cooldowns" in snap
    assert "watch_radar" in snap
    assert "closed_trades" in snap

    # Verify AI decision TTL expiration vs held-position pinning
    import json

    old_ts = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
    fresh_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "positions": {
                    "TSLA_US_EQ": {
                        "symbol": "TSLA_US_EQ",
                        "side": "LONG",
                        "quantity": 1.0,
                        "entry_price": 350.0,
                        "initial_stop_loss": 340.0,
                        "stop_loss": 340.0,
                        "take_profit": 370.0,
                        "atr_at_entry": 5.0,
                        "entry_order_id": "ord-tsla",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "ai.json").write_text(
        json.dumps(
            {
                "engine": "gemini-2.5-flash",
                "last_scan_status": "All 1/3 slots healthy.",
                "last_scan_timestamp": fresh_ts,
                "decisions": [
                    {
                        "timestamp": old_ts,
                        "symbol": "TSLA_US_EQ",
                        "action_type": "ENTRY_VETTING",
                        "decision": "APPROVE",
                        "confidence": 90,
                        "size_multiplier": 1.0,
                        "engine": "gemini-2.5-flash",
                        "score": 82.0,
                        "rating": "STRONG BUY",
                        "reasoning": "Held position from 4h ago stays pinned",
                        "headlines": [],
                    },
                    {
                        "timestamp": old_ts,
                        "symbol": "MRVL_US_EQ",
                        "action_type": "ENTRY_VETTING",
                        "decision": "APPROVE",
                        "confidence": 85,
                        "size_multiplier": 0.9,
                        "engine": "gemini-2.5-flash",
                        "score": 76.0,
                        "rating": "BUY",
                        "reasoning": "Unheld position from 4h ago expires",
                        "headlines": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    snap2 = build_dashboard_snapshot(cfg)
    active_syms = [d["symbol"] for d in snap2["ai_manager"]["decisions"]]
    expired_syms = [d["symbol"] for d in snap2["ai_manager"]["expired_decisions"]]
    assert active_syms == ["TSLA_US_EQ"]
    assert snap2["ai_manager"]["decisions"][0]["is_held"] is True
    assert expired_syms == ["MRVL_US_EQ"]


def test_overextension_anti_whipsaw_and_loss_cooldown(tmp_path: Path):
    from bot.screener import StockScreener

    state_file = tmp_path / "state_cooldown.json"
    cfg = Config(
        execution_mode="paper",
        state_file=str(state_file),
        stop_loss_atr_mult=2.0,
        take_profit_atr_mult=3.5,
        trailing_stop_atr_mult=1.5,
        max_ema_extension_atr=1.6,
        min_rvol_for_entry=1.0,
        cooldown_minutes_after_loss=120,
    )
    dh = DataHandler(cfg)
    se = StrategyEngine(cfg)
    screener = StockScreener(cfg, dh, se)
    oe = OrderExecutor(cfg)

    # 1. Overextended spike (> 1.6x ATR above EMA20) must be marked non-actionable ('WATCH')
    df_ext = dh.compute_indicators(make_synthetic_ohlcv(120))
    df_ext.loc[df_ext.index[-1], ["close", "high", "low", "ema_fast", "ema_slow", "rsi", "atr", "volume"]] = [
        110.0, 110.5, 108.0, 103.0, 101.0, 63.0, 2.0, 2500.0  # +3.5x ATR above EMA20!
    ]
    rec_ext = screener.evaluate_dataframe("TSLA_US_EQ", df_ext)
    assert rec_ext.actionable is False
    assert rec_ext.rating == "WATCH"
    assert "Overextended" in rec_ext.thesis

    # 2. Breakeven floor at +1.0R even when stop_loss_atr_mult (2.0) > trailing_stop_atr_mult (1.5)
    # and current_atr expands: stop can never be below entry_price once +1.0R is reached
    from bot.models import Position

    pos = Position(
        symbol="PLTR_US_EQ",
        side=Side.LONG,
        quantity=10.0,
        entry_price=100.0,
        initial_stop_loss=96.0,  # 1R = $4.00
        stop_loss=96.0,
        take_profit=107.0,
        atr_at_entry=2.0,
        entry_order_id="ord-1",
    )
    # Intra-bar dip to 95.80 (within 0.35 * ATR = 0.70 wick buffer above 95.30) holds intra-bar
    act_wick, _ = se.evaluate_position_exit_and_trail(
        pos, current_price=95.80, current_atr=2.0, is_candle_close=False
    )
    assert act_wick == SignalAction.HOLD
    # On candle close at 95.80 (<= 96.0), standard stop triggers
    act_close, reason_close = se.evaluate_position_exit_and_trail(
        pos, current_price=95.80, current_atr=2.0, is_candle_close=True
    )
    assert act_close == SignalAction.SELL

    # 3. Exiting at a loss places symbol in 120-minute cooldown
    oe.positions["PLTR_US_EQ"] = pos
    ob_loss = OrderBookSnapshot(symbol="PLTR_US_EQ", bid=95.80, ask=95.85, last=95.82)
    oe.execute_exit(pos, ob_loss, reason_close)
    assert oe.is_in_cooldown("PLTR_US_EQ") is True







def test_take_profit_extends_on_strong_trend_else_sells(tmp_path: Path):
    from bot.models import Position

    cfg = Config(execution_mode="paper", state_file=str(tmp_path / "s.json"))
    engine = StrategyEngine(cfg)

    def make_pos() -> Position:
        return Position(
            symbol="NVDA_US_EQ",
            side=Side.LONG,
            quantity=1.0,
            entry_price=100.0,
            initial_stop_loss=96.0,
            stop_loss=96.0,
            take_profit=107.0,
            atr_at_entry=2.0,
            entry_order_id="o1",
        )

    # Strong trend at target -> extend (HOLD), stop locked, target raised
    pos = make_pos()
    action, _ = engine.evaluate_position_exit_and_trail(
        pos, 107.0, current_atr=2.0, is_candle_close=False, trend_strong=True
    )
    assert action == SignalAction.HOLD
    assert pos.tp_extensions == 1
    assert pos.take_profit == pytest.approx(110.0)
    assert pos.stop_loss >= 105.0  # target - 1.0*ATR lock

    # Trend not strong / unknown -> classic sell at target
    for flag in (False, None):
        pos = make_pos()
        action, reason = engine.evaluate_position_exit_and_trail(
            pos, 107.0, current_atr=2.0, is_candle_close=False, trend_strong=flag
        )
        assert action == SignalAction.SELL
        assert "Take-Profit" in reason

    # Extension cap respected
    pos = make_pos()
    pos.tp_extensions = cfg.tp_extension_max
    action, _ = engine.evaluate_position_exit_and_trail(
        pos, 107.0, current_atr=2.0, is_candle_close=False, trend_strong=True
    )
    assert action == SignalAction.SELL


def test_market_order_retries_with_fewer_decimals_on_precision_error():
    from bot.t212_client import Trading212APIError, Trading212Client

    cfg = Config(execution_mode="demo", t212_api_key="k")
    client = Trading212Client(cfg)
    sent = []

    def fake_request(method, path, json_body=None, rate_key=None, max_attempts=3):
        sent.append(json_body["quantity"])
        if len(str(json_body["quantity"]).split(".")[-1]) > 2:
            raise Trading212APIError(
                400, '{"type":"/api-errors/quantity-precision-mismatch"}'
            )
        return {"id": 1, "status": "FILLED"}

    client._request = fake_request  # type: ignore[assignment]
    resp = client.place_market_order("NU_US_EQ", 9.8411)
    assert resp["id"] == 1
    assert sent[-1] == 9.84  # truncated, never rounded up
    assert client._qty_decimals["NU_US_EQ"] == 2

    # Learned precision is reused: first attempt already uses 2 decimals
    sent.clear()
    client.place_market_order("NU_US_EQ", 10.3878)
    assert sent == [10.38]


def test_us_market_open_helper():
    from main import TradingBot
    from unittest.mock import patch
    from datetime import datetime
    from zoneinfo import ZoneInfo

    app = TradingBot.__new__(TradingBot)

    class FakeDT(datetime):
        fake_now = None

        @classmethod
        def now(cls, tz=None):
            return cls.fake_now

    cases = [
        (datetime(2026, 10, 24, 14, 0, tzinfo=ZoneInfo("America/New_York")), False),  # Sat
        (datetime(2026, 10, 26, 10, 0, tzinfo=ZoneInfo("America/New_York")), True),   # Mon
        (datetime(2026, 10, 26, 16, 5, tzinfo=ZoneInfo("America/New_York")), False),  # after close
        (datetime(2026, 10, 26, 9, 0, tzinfo=ZoneInfo("America/New_York")), False),   # pre-open
    ]
    for when, expected in cases:
        FakeDT.fake_now = when
        with patch("main.datetime", FakeDT):
            assert app._is_us_market_open() is expected


def test_us_market_calendar_holidays_and_early_closes():
    from datetime import date

    from bot.market_calendar import (
        is_early_close,
        is_market_holiday,
        is_trading_day,
        market_close_minute,
        next_trading_day,
    )

    holidays_2026 = [
        date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
        date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
        date(2026, 11, 26), date(2026, 12, 25),
    ]
    holidays_2027 = [
        date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26),
        date(2027, 5, 31), date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6),
        date(2027, 11, 25), date(2027, 12, 24),
    ]
    for d in holidays_2026 + holidays_2027:
        assert is_market_holiday(d), d
        assert not is_trading_day(d), d

    # Jan 1 on a Saturday (2022) is NOT observed on the prior Friday
    assert not is_market_holiday(date(2021, 12, 31))

    # Ordinary days are trading days; weekends are not
    assert is_trading_day(date(2026, 10, 26))
    assert not is_trading_day(date(2026, 10, 24))

    # Early closes (13:00 ET)
    assert is_early_close(date(2026, 11, 27)) and market_close_minute(date(2026, 11, 27)) == 13 * 60
    assert is_early_close(date(2026, 12, 24))
    assert not is_early_close(date(2026, 7, 3))  # full holiday, not early close
    assert market_close_minute(date(2026, 10, 26)) == 16 * 60

    # Next trading day skips weekend + holiday
    assert next_trading_day(date(2026, 12, 24)) == date(2026, 12, 28)
    assert next_trading_day(date(2026, 10, 23)) == date(2026, 10, 26)


def test_telegram_notifier_and_chart_generation():
    import pandas as pd
    from bot.telegram_notifier import TelegramNotifier

    cfg = Config(
        execution_mode="demo",
        t212_api_key="demo_key",
        enable_telegram=True,
        telegram_bot_token="test_token",
        telegram_chat_id="12345678",
    )
    notifier = TelegramNotifier(cfg)
    assert notifier.enabled is True
    assert notifier.chat_id == "12345678"

    # Test in-memory candlestick chart generation
    dates = pd.date_range("2026-10-26 09:30", periods=20, freq="15min")
    df = pd.DataFrame({
        "timestamp": dates,
        "open": [100.0 + i for i in range(20)],
        "high": [102.0 + i for i in range(20)],
        "low": [99.0 + i for i in range(20)],
        "close": [101.0 + i for i in range(20)],
        "volume": [1000 + i * 50 for i in range(20)],
        "ema_fast": [100.5 + i for i in range(20)],
        "ema_slow": [99.5 + i for i in range(20)],
    })

    buf = notifier.generate_candlestick_chart(
        symbol="DKNG_US_EQ",
        df=df,
        entry_price=115.0,
        stop_loss=112.0,
        take_profit=120.0,
        title_suffix="Test Chart",
    )
    assert buf is not None
    assert len(buf.getvalue()) > 1000

    # Test daily summary performance chart generation
    summary_chart = notifier.generate_daily_summary_chart(
        date_str="Monday, Oct 26, 2026",
        closed_trades=[{"symbol": "AXON_US_EQ", "net_pnl": 2.62}],
        open_positions=[{"symbol": "DKNG_US_EQ", "unrealized_pnl": 0.50}],
        total_equity=501.98,
    )
    assert summary_chart is not None
    assert len(summary_chart.getvalue()) > 1000


def test_round_trip_fx_fee_accounting(tmp_path: Path):
    """Verify that Trading 212's 0.15% per leg (0.30% round-trip) FX fee is deducted accurately."""
    state_file = tmp_path / "fee_test_state.json"
    cfg = Config(
        execution_mode="paper",
        fx_fee_rate=0.0015,  # 0.15% per leg
        state_file=str(state_file),
    )
    oe = OrderExecutor(cfg)

    # Buy 10 shares of CRWD at $100 -> Notional = $1,000. Entry fee = $1.50
    ob_entry = OrderBookSnapshot(symbol="CRWD_US_EQ", bid=99.95, ask=100.00, last=99.98)
    plan = TradePlan(
        symbol="CRWD_US_EQ",
        side=Side.LONG,
        order_side="buy",
        quantity=10.0,
        reference_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        atr=2.5,
        risk_amount_usd=50.0,
        notional_usd=1000.0,
        spread_pct=0.0005,
        reason="Quant Signal",
    )
    pos = oe.execute_entry(plan, ob_entry)
    assert pos is not None
    assert pos.entry_fee_paid == pytest.approx(1.50, abs=1e-3)

    # Sell 10 shares at $110 -> Gross PnL = $100. Notional = $1,100. Exit fee = $1.65
    ob_exit = OrderBookSnapshot(symbol="CRWD_US_EQ", bid=110.00, ask=110.05, last=110.02)
    res = oe.execute_exit(pos, ob_exit, "TAKE_PROFIT_TRIGGERED")
    assert res is not None and res.success

    # Total fee = $1.50 + $1.65 = $3.15
    # Net PnL = $100.00 - $3.15 = $96.85
    assert len(oe.closed_trades) == 1
    trade = oe.closed_trades[0]
    assert trade["gross_pnl"] == pytest.approx(100.00, abs=1e-2)
    assert trade["fee_paid"] == pytest.approx(3.15, abs=1e-2)
    assert trade["net_pnl"] == pytest.approx(96.85, abs=1e-2)
    # Net return % on $1,000 entry = 9.685%
    assert trade["pnl_pct"] == pytest.approx(9.69, abs=1e-2)
    assert oe.realized_pnl == pytest.approx(96.85, abs=1e-2)


def test_uk_etp_sleeve_resolution_and_zero_fee_exemption(tmp_path: Path):
    """Verify UK 3x Leveraged & Inverse Short ETP ticker resolution, T212 translation, universe toggle, and 0% FX/Stamp Duty fee."""
    # 1. Ticker resolution (3x Bull & 3x Short GBP share classes)
    assert DataHandler.resolve_ticker_pair("QQQ3_UK_EQ") == ("QQQ3_UK_EQ", "LQQ3.L")
    assert DataHandler.resolve_ticker_pair("3LUS_UK_EQ") == ("3LUS_UK_EQ", "3LUS.L")
    assert DataHandler.resolve_ticker_pair("3LSE_UK_EQ") == ("3LSE_UK_EQ", "3SMC.L")
    assert DataHandler.resolve_ticker_pair("QQQS_UK_EQ") == ("QQQS_UK_EQ", "LQQS.L")
    assert DataHandler.resolve_ticker_pair("3USS_UK_EQ") == ("3USS_UK_EQ", "3ULS.L")

    # 2. Trading 212 broker ticker translations
    assert Trading212Client.to_broker_ticker("QQQ3_UK_EQ") == "LQQ3l_EQ"
    assert Trading212Client.to_broker_ticker("3LUS_UK_EQ") == "3LUS1l_EQ"
    assert Trading212Client.to_broker_ticker("3LSE_UK_EQ") == "3SMCl_EQ"
    assert Trading212Client.to_broker_ticker("QQQS_UK_EQ") == "LQQSl_EQ"
    assert Trading212Client.to_broker_ticker("3USS_UK_EQ") == "3ULSl_EQ"
    assert Trading212Client.from_broker_ticker("LQQ3l_EQ") == "QQQ3_UK_EQ"
    assert Trading212Client.from_broker_ticker("3LUS1l_EQ") == "3LUS_UK_EQ"
    assert Trading212Client.from_broker_ticker("3SMCl_EQ") == "3LSE_UK_EQ"
    assert Trading212Client.from_broker_ticker("LQQSl_EQ") == "QQQS_UK_EQ"
    assert Trading212Client.from_broker_ticker("3ULSl_EQ") == "3USS_UK_EQ"

    # 3. Screener universe with UK ETP sleeve enabled vs disabled
    cfg_enabled = Config(
        execution_mode="paper",
        symbols=[],
        enable_screener=True,
        enable_uk_etp_sleeve=True,
        state_file=str(tmp_path / "uk_state.json"),
    )
    dh = DataHandler(cfg_enabled)
    se = StrategyEngine(cfg_enabled)
    screener_on = StockScreener(cfg_enabled, dh, se)
    uni_on = screener_on.get_scan_universe()
    assert len(uni_on) == 71
    for uk_sym in (
        "QQQ3_UK_EQ",
        "3LUS_UK_EQ",
        "3LSE_UK_EQ",
        "3NVD_UK_EQ",
        "3TSL_UK_EQ",
        "3LGO_UK_EQ",
        "QQQS_UK_EQ",
        "3USS_UK_EQ",
    ):
        assert uk_sym in uni_on
    for mega_sym in ("GOOGL_US_EQ", "META_US_EQ", "AMZN_US_EQ", "MSFT_US_EQ", "AAPL_US_EQ", "NFLX_US_EQ"):
        assert mega_sym in uni_on

    cfg_disabled = Config(
        symbols=[],
        enable_screener=True,
        enable_uk_etp_sleeve=False,
        state_file=str(tmp_path / "uk_off_state.json"),
    )
    screener_off = StockScreener(cfg_disabled, DataHandler(cfg_disabled), StrategyEngine(cfg_disabled))
    uni_off = screener_off.get_scan_universe()
    assert len(uni_off) == 63
    assert "QQQ3_UK_EQ" not in uni_off

    # 4. 0% FX & 0% Stamp Duty fee exemption for _UK_EQ symbols
    oe = OrderExecutor(cfg_enabled)
    ob_entry = OrderBookSnapshot(symbol="QQQ3_UK_EQ", bid=311.40, ask=311.55, last=311.50)
    plan = TradePlan(
        symbol="QQQ3_UK_EQ",
        side=Side.LONG,
        order_side="buy",
        quantity=1.0,
        reference_price=311.55,
        stop_loss=300.00,
        take_profit=335.00,
        atr=5.5,
        risk_amount_usd=11.55,
        notional_usd=311.55,
        spread_pct=0.0005,
        reason="UK 3x ETP Momentum Breakout",
    )
    pos = oe.execute_entry(plan, ob_entry)
    assert pos is not None
    assert pos.entry_fee_paid == 0.0

    ob_exit = OrderBookSnapshot(symbol="QQQ3_UK_EQ", bid=331.55, ask=331.70, last=331.60)
    res = oe.execute_exit(pos, ob_exit, "TAKE_PROFIT_TRIGGERED")
    assert res is not None and res.success
    trade = oe.closed_trades[0]
    assert trade["fee_paid"] == 0.0
    assert trade["gross_pnl"] == pytest.approx(20.00, abs=1e-2)
    assert trade["net_pnl"] == pytest.approx(20.00, abs=1e-2)

    # 5. Verify 3 US + 1 UK dedicated slot reservation (4 total slots)
    from main import TradingBot
    from bot.models import Position

    bot = TradingBot(cfg_enabled)
    for us_sym in ("PLTR_US_EQ", "NVDA_US_EQ", "COIN_US_EQ"):
        bot.order_executor.positions[us_sym] = Position(
            symbol=us_sym,
            side=Side.LONG,
            quantity=1.0,
            entry_price=100.0,
            initial_stop_loss=95.0,
            stop_loss=95.0,
            take_profit=110.0,
            atr_at_entry=2.5,
            entry_order_id="test",
        )
    # 3 US slots are full -> 4th US stock is blocked, but 4th slot is open for UK ETP
    assert bot._has_open_slot_for_symbol("AMD_US_EQ") is False
    assert bot._has_open_slot_for_symbol("QQQ3_UK_EQ") is True
    assert bot._has_open_slot_for_symbol("QQQS_UK_EQ") is True

    # 6. Verify inverse ETP regime-inverted score thresholds (favored in BEARISH, stricter in BULLISH)
    # In BEARISH regime: long stocks require 86.0, whereas 3x Short ETPs only require base min_score (76.0)
    assert bot._required_min_score_for_symbol("QQQ3_UK_EQ", "BEARISH", 86.0) == 86.0
    assert bot._required_min_score_for_symbol("QQQS_UK_EQ", "BEARISH", 86.0) == cfg_enabled.min_recommendation_score
    assert bot._required_min_score_for_symbol("3USS_UK_EQ", "BEARISH", 86.0) == cfg_enabled.min_recommendation_score
    # In BULLISH regime: long stocks require base min_score (76.0), whereas 3x Short ETPs require >= 80.0
    assert bot._required_min_score_for_symbol("QQQ3_UK_EQ", "BULLISH", 76.0) == 76.0
    assert bot._required_min_score_for_symbol("QQQS_UK_EQ", "BULLISH", 76.0) >= 80.0


def test_position_trade_journey_trajectory(tmp_path: Path):
    """Verify per-position price_history journey tracking from buy to sell and dashboard snapshot enrichment."""
    from dashboard import build_dashboard_snapshot

    cfg = Config(
        execution_mode="paper",
        state_file=str(tmp_path / "journey_state.json"),
        log_file=str(tmp_path / "journey_bot.log"),
    )
    oe = OrderExecutor(cfg)
    ob_entry = OrderBookSnapshot(symbol="LUNR_US_EQ", bid=11.18, ask=11.20, last=11.19)
    plan = TradePlan(
        symbol="LUNR_US_EQ",
        side=Side.LONG,
        order_side="buy",
        quantity=10.0,
        reference_price=11.20,
        stop_loss=10.70,
        take_profit=12.40,
        atr=0.35,
        risk_amount_usd=5.0,
        notional_usd=112.0,
        spread_pct=0.001,
        reason="Breakout",
    )
    pos = oe.execute_entry(plan, ob_entry)
    assert pos is not None
    assert len(pos.price_history) == 1
    assert pos.price_history[0]["price"] == pytest.approx(11.20, abs=1e-3)

    # Record intraday price waypoints along the journey
    assert pos.record_price_point(11.35) is True
    assert pos.record_price_point(11.52) is True
    oe.save_state()

    snap = build_dashboard_snapshot(cfg)
    assert len(snap["positions"]) == 1
    enriched = snap["positions"][0]
    assert enriched["symbol"] == "LUNR_US_EQ"
    assert len(enriched["price_history"]) >= 3
    assert enriched["price_history"][0]["price"] == pytest.approx(11.20, abs=1e-3)

    # Close the position and verify the full Buy -> Sell journey is preserved in closed_trades
    ob_exit = OrderBookSnapshot(symbol="LUNR_US_EQ", bid=11.80, ask=11.82, last=11.81)
    res = oe.execute_exit(pos, ob_exit, "TAKE_PROFIT_TRIGGERED")
    assert res is not None and res.success
    closed = oe.closed_trades[0]
    assert "price_history" in closed
    assert len(closed["price_history"]) >= 4
    assert closed["price_history"][0]["price"] == pytest.approx(11.20, abs=1e-3)
    assert closed["price_history"][-1]["price"] == pytest.approx(11.80, abs=1e-3)


def test_trade_journal_postmortem_and_persistent_circuit_breaker(tmp_path: Path):
    """Verify permanent trade_journal.jsonl, AI postmortem generation, persistent 24h circuit breaker, and 2-stage trailing stop."""
    from bot.ai_manager import AIPortfolioManager

    state_file = tmp_path / "t212_state.json"
    decisions_file = tmp_path / "ai_decisions.json"
    cfg = Config(
        execution_mode="paper",
        state_file=str(state_file),
        ai_decisions_file=str(decisions_file),
        stop_loss_atr_mult=2.0,
        take_profit_atr_mult=3.5,
        trailing_stop_activate_r=1.0,
        trailing_stop_start_r=1.5,
        trailing_stop_atr_mult=1.5,
    )
    se = StrategyEngine(cfg)
    rm = RiskManager(cfg, se)
    ai = AIPortfolioManager(cfg)
    oe = OrderExecutor(cfg)

    # 1. Persistent 24h Circuit Breaker survives process restart
    t0 = datetime.now(timezone.utc) - timedelta(hours=2)
    rm.record_equity(500.0, now=t0)
    rm.record_equity(472.0, now=t0 + timedelta(minutes=30))  # -5.6% drawdown -> trips breaker
    assert rm.circuit_breaker_tripped is True

    # Simulate systemd restart by instantiating a brand-new RiskManager pointing at the same state dir
    rm_reloaded = RiskManager(cfg, se)
    assert rm_reloaded.circuit_breaker_tripped is True
    assert "5.60%" in rm_reloaded.circuit_breaker_reason

    # 2. Two-Stage Trailing Stop: Stage 1 (+1.0R) locks fee-plus breakeven; Stage 2 (+1.5R) activates ATR ratchet
    from bot.models import Position

    pos = Position(
        symbol="DKNG_US_EQ",
        side=Side.LONG,
        quantity=10.0,
        entry_price=100.0,
        initial_stop_loss=96.0,  # 1R = $4.00 (2.0 * ATR=2.0)
        stop_loss=96.0,
        take_profit=107.0,
        atr_at_entry=2.0,
        entry_order_id="ord-dkng-1",
    )
    # At +1.10R ($104.40, < 1.5R): stop locks at Fee-Plus Breakeven ($100.35), NOT $104.40 - $3.00 = $101.40
    se.evaluate_position_exit_and_trail(pos, current_price=104.40, current_atr=2.0)
    assert pos.trailing_active is True
    assert pos.stop_loss == pytest.approx(100.0 * 1.0035)

    # At +1.60R ($106.40, >= 1.5R): Stage 2 ATR ratchet activates ($106.40 - 1.5*2.0 = $103.40)
    se.evaluate_position_exit_and_trail(pos, current_price=106.40, current_atr=2.0)
    assert pos.stop_loss == pytest.approx(103.40)

    # 3. Permanent Trade Journal & Loss Postmortem classification (including 3LSE_UK_EQ overnight gap)
    pm_gap = ai.generate_loss_postmortem(
        {
            "symbol": "3LSE_UK_EQ",
            "entry_price": 68.91,
            "exit_price": 60.37,
            "net_pnl": -18.30,
            "gross_pnl": -18.30,
            "fee_paid": 0.0,
            "pnl_pct": -12.40,
            "r_multiple": -3.32,
            "held_minutes": 1342,
            "opened_at": "2026-10-29T09:53:00+00:00",
            "closed_at": "2026-10-30T08:15:00+00:00",
            "reason": "Stop-Loss hit at 60.3679 (stop=66.3348)",
        },
        allow_llm=False,
    )
    assert pm_gap["outcome_tag"] == "OVERNIGHT_GAP"
    assert "EOD Flat Rule" in pm_gap["tactical_lesson"]


def test_disk_monitor_telemetry_and_alerting(tmp_path: Path):
    from unittest.mock import patch
    from collections import namedtuple
    from bot.disk_monitor import DiskMonitor

    Usage = namedtuple("Usage", ["total", "used", "free"])
    # Mock disk: 100 GB total, 25 GB used, 75 GB free (25% used)
    mock_usage = Usage(total=100 * (1024**3), used=25 * (1024**3), free=75 * (1024**3))

    with patch("shutil.disk_usage", return_value=mock_usage):
        monitor = DiskMonitor(target_path=str(tmp_path), alert_threshold_pct=80.0, critical_threshold_pct=90.0)
        telem = monitor.get_disk_telemetry()
        assert telem["total_gb"] == 100.0
        assert telem["used_gb"] == 25.0
        assert telem["free_gb"] == 75.0
        assert telem["used_pct"] == 25.0
        assert telem["is_above_warning"] is False
        assert telem["status_badge"] == "HEALTHY 🟢"

        # Test formatting status message
        status_msg = monitor.format_status_message(telem)
        assert "Proxmox Node Storage Status" in status_msg

    # Test alerting threshold triggers
    alert_needed, level = monitor.should_alert({"used_pct": 82.5})
    assert alert_needed is True
    assert level == "WARNING"

    crit_needed, crit_level = monitor.should_alert({"used_pct": 91.0})
    assert crit_needed is True
    assert crit_level == "CRITICAL"

    alert_msg = monitor.format_telegram_alert({
        "target_path": "/",
        "total_gb": 8.0,
        "used_gb": 6.5,
        "free_gb": 1.5,
        "used_pct": 81.2,
        "is_above_critical": False,
        "logs_total_mb": 25.0,
        "trade_journal_kb": 12.0,
    })
    assert "DISK SPACE WARNING: 81.2% Used" in alert_msg








