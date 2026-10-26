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
from bot.models import OrderBookSnapshot, Side, Signal, SignalAction
from bot.order_executor import OrderExecutor
from bot.risk_manager import RiskManager
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

    pos = oe.execute_entry(plan, ob)
    assert pos is not None
    mock_t212.place_limit_order.assert_called_once_with(
        ticker="NVDA_US_EQ",
        signed_quantity=16.6667,  # Positive quantity for BUY
        limit_price=120.0,
        time_validity="DAY",
    )

    # Move price to +1.0R ($126): trailing stop activates and trails by 1.5 * ATR ($6) -> SL moves to $120
    action, _ = se.evaluate_position_exit_and_trail(pos, current_price=126.0, current_atr=4.0)
    assert action == SignalAction.HOLD
    assert pos.trailing_active is True
    assert pos.stop_loss == pytest.approx(120.0)

    # Pullback to $119.50 triggers the trailing stop -> sends negative quantity market SELL to Trading 212
    action, reason = se.evaluate_position_exit_and_trail(pos, current_price=119.50, current_atr=4.0)
    assert action == SignalAction.SELL
    mock_notifier = MagicMock()
    mock_notifier.enabled = True
    oe.telegram_notifier = mock_notifier

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
