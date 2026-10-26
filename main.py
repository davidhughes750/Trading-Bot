#!/usr/bin/env python3
"""Main execution loop and CLI entry point for the Trading 212 Automated Trading Bot.

Usage:
    python main.py                        # Scan 25+ stocks, print recommendations, and auto-trade the #1 pick
    python main.py --recommend            # Scan 25+ stocks and display the ranked recommendation leaderboard only
    python main.py --once                 # Run one full recommendation + trading cycle and exit
    python main.py --test-buy MSFT_US_EQ  # Force a single risk-sized Demo/Paper BUY order immediately
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Optional

from bot import __version__
from bot.ai_manager import AIPortfolioManager
from bot.config import Config
from bot.data_handler import DataHandler
from bot.models import OrderBookSnapshot, Side, Signal, SignalAction
from bot.order_executor import OrderExecutor
from bot.risk_manager import RiskManager
from bot.screener import StockScreener
from bot.strategy_engine import StrategyEngine
from bot.t212_client import Trading212Client

logger = logging.getLogger("trading212_bot")


def setup_logging(log_level: str, log_file: str) -> None:
    """Configure structured console and rotating file logging."""
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    fmt = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


class TradingBot:
    """Asynchronous orchestrator coordinating StockScreener, Trading 212 API, strategy, and risk."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.t212_client: Optional[Trading212Client] = (
            Trading212Client(config)
            if config.execution_mode in {"demo", "live"}
            else None
        )
        self.data_handler = DataHandler(config, t212_client=self.t212_client)
        self.strategy_engine = StrategyEngine(config)
        self.risk_manager = RiskManager(config, self.strategy_engine)
        self.order_executor = OrderExecutor(config, t212_client=self.t212_client)
        self.screener = StockScreener(config, self.data_handler, self.strategy_engine)
        self.ai_manager = AIPortfolioManager(config)

        self._stop_event = asyncio.Event()
        self._last_scan_bar_ts: Optional[str] = None
        self._latest_atr: Dict[str, float] = {}
        # Per-symbol "trend still strong" flag from the latest closed-bar scan,
        # used to decide whether to extend a take-profit instead of selling.
        self._trend_strong: Dict[str, bool] = {}
        self._market_regime: str = "BULLISH"
        self._market_regime_summary: str = f"Awaiting {config.market_benchmark_symbol} regime check"
        self._effective_min_score: float = config.min_recommendation_score

    def _update_runtime_status(self, state: str, detail: str) -> None:
        """Persist real-time bot operational state to `logs/bot_runtime.json` for the Web GUI."""
        try:
            runtime_path = Path("logs/bot_runtime.json")
            runtime_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "state": state,
                "detail": detail,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "last_candle_ts": self._last_scan_bar_ts or "",
                "market_regime": self._market_regime,
                "market_regime_summary": self._market_regime_summary,
                "effective_min_score": self._effective_min_score,
                "poll_interval_sec": self.config.poll_interval_sec,
            }
            runtime_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    def request_shutdown(self) -> None:
        logger.info("Shutdown signal received. Finishing current cycle cleanly...")
        self._stop_event.set()

    async def run(self, run_once: bool = False) -> None:
        """Main asynchronous polling loop aligned with candle closes and intra-bar risk ticks."""
        endpoint_desc = (
            self.config.resolved_t212_base_url
            if self.config.execution_mode in {"demo", "live"}
            else "Local Paper Simulator"
        )
        universe = self.screener.get_scan_universe()
        if not run_once:
            from dashboard import start_background_dashboard

            start_background_dashboard(self.config)

        logger.info(
            "Starting Trading 212 Bot v%s | mode=%s (%s) | universe=%d stocks | timeframe=%s | AI Manager=%s",
            __version__,
            self.config.execution_mode.upper(),
            endpoint_desc,
            len(universe),
            self.config.timeframe,
            self.ai_manager.active_engine_label,
        )

        while not self._stop_event.is_set():
            try:
                await self.run_cycle()
            except Exception as exc:
                logger.exception("Unhandled error in trading cycle: %s", exc)

            if run_once or self.risk_manager.circuit_breaker_tripped:
                if self.risk_manager.circuit_breaker_tripped:
                    logger.critical(
                        "Halting bot loop due to tripped 24h drawdown circuit breaker: %s",
                        self.risk_manager.circuit_breaker_reason,
                    )
                break

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=float(self.config.poll_interval_sec)
                )
            except asyncio.TimeoutError:
                pass

        logger.info("Trading 212 Bot stopped cleanly.")

    def _lookup_atr_for_symbol(self, symbol: str) -> Optional[float]:
        """Return cached or freshly computed 14-period ATR for a recovered Trading 212 position."""
        if symbol in self._latest_atr and self._latest_atr[symbol] > 0:
            return self._latest_atr[symbol]
        df = self.data_handler.fetch_closed_ohlcv(symbol)
        atr_val = float(df["atr"].iloc[-1])
        self._latest_atr[symbol] = atr_val
        return atr_val

    def _is_us_market_open(self) -> bool:
        """Return True during the regular US cash session.

        Mon-Fri 09:30-16:00 ET (13:00 ET on early-close days), excluding NYSE/Nasdaq
        holidays (see `bot.market_calendar`). Unscheduled closures are not modelled.
        """
        try:
            from zoneinfo import ZoneInfo

            from bot.market_calendar import is_trading_day, market_close_minute

            now_et = datetime.now(ZoneInfo("America/New_York"))
            if not is_trading_day(now_et.date()):
                return False
            mins = now_et.hour * 60 + now_et.minute
            return (9 * 60 + 30) <= mins < market_close_minute(now_et.date())
        except Exception:
            return True  # fail open: never block trading on a timezone lookup error

    def _is_in_opening_bell_window(self) -> bool:
        """Return True during the first `skip_opening_minutes` (09:30-09:45 ET) of the US market open."""
        if self.config.skip_opening_minutes <= 0:
            return False
        try:
            from zoneinfo import ZoneInfo

            now_et = datetime.now(ZoneInfo("America/New_York"))
            if now_et.weekday() >= 5:
                return False
            mins_since_midnight = now_et.hour * 60 + now_et.minute
            open_min = 9 * 60 + 30
            return open_min <= mins_since_midnight < (open_min + self.config.skip_opening_minutes)
        except Exception:
            return False

    def _evaluate_market_regime(self) -> tuple[str, str, float]:
        """Evaluate broad US market regime (QQQ) to adapt minimum entry score threshold."""
        base_min = self.config.min_recommendation_score
        if not self.config.market_regime_filter:
            return "BULLISH", "Regime filter disabled", base_min

        bench = self.config.market_benchmark_symbol or "QQQ"
        try:
            df = self.data_handler.fetch_closed_ohlcv(bench)
            curr = df.iloc[-1]
            close_p = float(curr["close"])
            ema20 = float(curr["ema_fast"])
            ema50 = float(curr["ema_slow"])
            rsi = float(curr["rsi"])

            if close_p > ema20 and ema20 >= ema50 and rsi >= 50.0:
                summary = (
                    f"BULLISH ({bench} ${close_p:.2f} > EMA20 ${ema20:.2f} > EMA50 ${ema50:.2f}, RSI {rsi:.1f})"
                )
                return "BULLISH", summary, base_min
            if close_p >= ema50 or rsi >= 46.0:
                cautious_min = max(base_min, 80.0)
                summary = (
                    f"CAUTIOUS / MIXED ({bench} ${close_p:.2f}, EMA20 ${ema20:.2f}, EMA50 ${ema50:.2f}, "
                    f"RSI {rsi:.1f} -> requiring STRONG BUY score >= {cautious_min:.0f})"
                )
                return "CAUTIOUS", summary, cautious_min

            bearish_min = max(base_min, 86.0)
            summary = (
                f"BEARISH RISK-OFF ({bench} ${close_p:.2f} < EMA20 ${ema20:.2f} < EMA50 ${ema50:.2f}, "
                f"RSI {rsi:.1f} -> only A+ outliers >= {bearish_min:.0f} allowed)"
            )
            return "BEARISH", summary, bearish_min
        except Exception as exc:
            logger.warning("Could not evaluate %s market regime (%s); using default threshold.", bench, exc)
            return "BULLISH", f"{bench} regime unavailable", base_min

    async def run_cycle(self) -> None:
        """Execute a single evaluation cycle:
        1. Sync portfolio with Trading 212 (`/equity/portfolio`) and fetch live quotes for open positions.
        2. Check account equity (`/equity/account/cash`) and evaluate 5% 24h drawdown circuit breaker.
        3. Manage open positions intra-bar every 15s (Stop-Loss, Take-Profit, and 1R Trailing Stop).
        4. On each newly closed candle, run the StockScreener across the 25-stock universe,
           print the ranked recommendation leaderboard, and trade the #1 actionable recommendation.
        """
        had_positions_before_sync = len(self.order_executor.positions) > 0
        await asyncio.to_thread(
            self.order_executor.sync_positions_with_t212, self._lookup_atr_for_symbol
        )
        if (
            had_positions_before_sync
            and len(self.order_executor.positions) == 0
            and self.config.execution_mode in {"demo", "live"}
        ):
            logger.info(
                "All open positions were externally closed/reset on Trading 212; "
                "resetting candle scan lock and 24h equity watermark to re-scan immediately."
            )
            self._last_scan_bar_ts = None
            self.risk_manager._equity_history.clear()
            self.risk_manager.circuit_breaker_tripped = False
            self.risk_manager.circuit_breaker_reason = ""

        order_books: Dict[str, OrderBookSnapshot] = {}
        latest_prices: Dict[str, float] = {}

        # Always fetch live quotes for any currently open positions so intra-bar SL/TP/trail works every 15s
        for sym in list(self.order_executor.positions.keys()):
            try:
                ob = await asyncio.to_thread(
                    self.data_handler.fetch_order_book_snapshot, sym
                )
                order_books[sym] = ob
                latest_prices[sym] = ob.mid_price
            except Exception as exc:
                logger.error("[%s] Failed to fetch quote for open position: %s", sym, exc)

        if latest_prices:
            Path("logs/live_quotes.json").write_text(
                json.dumps(latest_prices, indent=2), encoding="utf-8"
            )

        # 1. Check account equity & 24-hour drawdown circuit breaker
        total_equity, available_cash = await asyncio.to_thread(
            self.order_executor.get_account_equity_and_cash, latest_prices
        )
        dd_pct = self.risk_manager.record_equity(total_equity)
        logger.info(
            "Trading 212 Portfolio | Total Equity=$%.2f | Free Cash=$%.2f | Open Positions=%d/%d | 24h DD=%.2f%%",
            total_equity,
            available_cash,
            len(self.order_executor.positions),
            self.config.max_open_positions,
            dd_pct * 100.0,
        )

        if self.risk_manager.circuit_breaker_tripped:
            for sym, pos in list(self.order_executor.positions.items()):
                ob = order_books.get(sym)
                if ob:
                    await asyncio.to_thread(
                        self.order_executor.execute_exit,
                        pos,
                        ob,
                        "Emergency flatten: 24h drawdown circuit breaker tripped",
                    )
            return

        # 2. Intra-bar management of open positions (SL / TP / 1R Trailing Stop with anti-whipsaw buffer)
        for sym, pos in list(self.order_executor.positions.items()):
            ob = order_books.get(sym)
            if ob is None:
                continue

            mark_price = ob.bid if pos.side.value == "LONG" else ob.ask
            prev_sl = pos.stop_loss
            prev_tp = pos.take_profit
            exit_action, exit_reason = self.strategy_engine.evaluate_position_exit_and_trail(
                position=pos,
                current_price=mark_price,
                current_atr=self._latest_atr.get(sym),
                is_candle_close=False,
                trend_strong=self._trend_strong.get(sym),
            )
            if pos.stop_loss != prev_sl or pos.take_profit != prev_tp:
                self.order_executor.save_state()

            if exit_action != SignalAction.HOLD:
                logger.info("[%s] Intra-bar protective exit triggered: %s", sym, exit_reason)
                await asyncio.to_thread(
                    self.order_executor.execute_exit, pos, ob, exit_reason
                )

        # 3. Check if a new closed candle is available using benchmark ticker
        universe = self.screener.get_scan_universe()
        probe_symbol = universe[0]
        try:
            probe_df = await asyncio.to_thread(
                self.data_handler.fetch_closed_ohlcv, probe_symbol
            )
        except Exception as exc:
            logger.error("[%s] Failed to fetch probe OHLCV data: %s", probe_symbol, exc)
            return

        latest_candle_ts = str(probe_df["timestamp"].iloc[-1])
        if self._last_scan_bar_ts == latest_candle_ts:
            open_cnt = len(self.order_executor.positions)
            held_str = ", ".join(self.order_executor.positions.keys()) if open_cnt > 0 else "100% Cash"
            self._update_runtime_status(
                "MONITORING",
                f"Intra-bar SL/TP & 1R Trailing Stop guard active ({open_cnt}/{self.config.max_open_positions} slots: {held_str}) • "
                f"Waiting for next {self.config.timeframe} candle close.",
            )
            logger.debug(
                "Candle %s already scanned; monitoring positions until next %s candle close.",
                latest_candle_ts,
                self.config.timeframe,
            )
            return

        self._last_scan_bar_ts = latest_candle_ts
        probe_t212, _ = self.data_handler.resolve_ticker_pair(probe_symbol)
        ohlcv_cache = {probe_t212: probe_df}

        # 4. Run Quantitative Stock Screener across the full universe
        self._update_runtime_status(
            "SCANNING_UNIVERSE",
            f"Scanning {len(universe)} high-beta US stocks across 6 parallel threads on closed {self.config.timeframe} candle ({latest_candle_ts})...",
        )
        logger.info(
            "Scanning %d Trading 212 stocks on closed %s bar (%s)...",
            len(universe),
            self.config.timeframe,
            latest_candle_ts,
        )
        recommendations = await asyncio.to_thread(
            self.screener.scan_universe,
            self.order_executor.positions,
            ohlcv_cache,
        )

        for rec in recommendations:
            self._latest_atr[rec.symbol] = rec.atr
            self._trend_strong[rec.symbol] = rec.trend_strong

        leaderboard = self.screener.format_leaderboard(
            recommendations, top_n=self.config.screener_top_n
        )
        logger.info("%s", leaderboard)

        # 5. Check if any currently open position has a candle-close stop-loss or bearish reversal exit signal
        for rec in recommendations:
            open_pos = self.order_executor.positions.get(rec.symbol)
            if open_pos is None:
                continue
            if rec.signal.is_exit:
                ob = order_books.get(rec.symbol) or await asyncio.to_thread(
                    self.data_handler.fetch_order_book_snapshot, rec.symbol
                )
                await asyncio.to_thread(
                    self.order_executor.execute_exit, open_pos, ob, rec.signal.reason
                )
                continue

            # Candle-close stop-loss check using the closed bar's close price
            prev_close_tp = open_pos.take_profit
            close_exit_action, close_exit_reason = self.strategy_engine.evaluate_position_exit_and_trail(
                position=open_pos,
                current_price=rec.close_price,
                current_atr=rec.atr,
                is_candle_close=True,
                trend_strong=rec.trend_strong,
            )
            if open_pos.take_profit != prev_close_tp:
                self.order_executor.save_state()
            if close_exit_action != SignalAction.HOLD:
                logger.info("[%s] Candle-close protective exit triggered: %s", rec.symbol, close_exit_reason)
                ob = order_books.get(rec.symbol) or await asyncio.to_thread(
                    self.data_handler.fetch_order_book_snapshot, rec.symbol
                )
                await asyncio.to_thread(
                    self.order_executor.execute_exit, open_pos, ob, close_exit_reason
                )

        # 5a. Never place new entries while the US market is closed (weekends / overnight)
        if self.config.require_market_open_for_entries and not self._is_us_market_open():
            msg = (
                "US market closed — scan complete, new entries paused until the next "
                "regular session (09:30 ET on the next trading day). Open positions remain protected."
            )
            logger.info("%s", msg)
            self.ai_manager.record_scan_status(msg)
            self._update_runtime_status("MARKET_CLOSED", msg)
            return

        # 5b. Skip new entries during the chaotic first 15 minutes of the US market open (09:30-09:45 ET)
        if self._is_in_opening_bell_window():
            msg = (
                f"US opening-bell whipsaw guard active (first {self.config.skip_opening_minutes}m after 09:30 ET) — "
                "deferring new entries until opening volatility settles."
            )
            logger.info("%s", msg)
            self.ai_manager.record_scan_status(msg)
            self._update_runtime_status("OPENING_BELL_GUARD", msg)
            self._last_scan_bar_ts = None
            return

        # 5c. Evaluate Broad Market Regime (QQQ)
        regime_state, market_regime_summary, effective_min_score = await asyncio.to_thread(
            self._evaluate_market_regime
        )
        self._market_regime = regime_state
        self._market_regime_summary = market_regime_summary
        self._effective_min_score = effective_min_score
        logger.info("Market Regime Check: %s", market_regime_summary)

        # 6. Auto-trade the top-ranked actionable recommendation(s) up to MAX_OPEN_POSITIONS
        actionable_picks = []
        for r in recommendations:
            if not r.actionable or r.symbol in self.order_executor.positions:
                continue
            if self.order_executor.is_in_cooldown(r.symbol):
                logger.info("[%s] Skipping actionable pick: ticker is in post-loss cooldown.", r.symbol)
                continue
            if r.score < effective_min_score:
                logger.info(
                    "[%s] Skipping pick (score %.1f < regime-adjusted threshold %.1f for %s market).",
                    r.symbol,
                    r.score,
                    effective_min_score,
                    regime_state,
                )
                continue
            actionable_picks.append(r)

        if not actionable_picks:
            top_rec = recommendations[0] if recommendations else None
            top_desc = f"{top_rec.symbol} ({top_rec.score:.1f}/100, {top_rec.rating})" if top_rec else "N/A"
            held_syms = ", ".join(self.order_executor.positions.keys()) or "None"
            status_msg = (
                f"Scanned {len(recommendations)} stocks ({market_regime_summary}) • "
                f"Open Slots: {len(self.order_executor.positions)}/{self.config.max_open_positions} ({held_syms}) • "
                f"Top candidate {top_desc} below sniper entry criteria (min score {effective_min_score:.0f}); standing pat."
            )
            self.ai_manager.record_scan_status(status_msg)
            self._update_runtime_status("MONITORING", status_msg)
            logger.info(
                "No stocks met the regime-adjusted BUY threshold (score >= %.1f, RVOL >= %.2fx, not overextended) on this bar.",
                effective_min_score,
                self.config.min_rvol_for_entry,
            )
            return

        # 6a. AI Smart Slot Rotation: if all slots are full and a new STRONG BUY (>=80) appears,
        # check if we should rotate out of a stagnant/deteriorating position.
        if len(self.order_executor.positions) >= self.config.max_open_positions:
            rot_dec = None
            if self.config.enable_ai_manager and actionable_picks[0].score >= 80.0:
                rot_dec = await asyncio.to_thread(
                    self.ai_manager.evaluate_slot_rotation,
                    actionable_picks[0],
                    self.order_executor.positions,
                    recommendations,
                    latest_prices,
                )
            if (
                rot_dec is not None
                and rot_dec.decision == "ROTATE"
                and rot_dec.replace_symbol in self.order_executor.positions
            ):
                stale_sym = rot_dec.replace_symbol
                stale_pos = self.order_executor.positions[stale_sym]
                logger.info(
                    "[AI Portfolio Manager] SLOT ROTATION APPROVED (%s, conf=%d%%): Closing %s -> Buying %s | %s",
                    rot_dec.engine,
                    rot_dec.confidence,
                    stale_sym,
                    actionable_picks[0].symbol,
                    rot_dec.reasoning,
                )
                stale_ob = order_books.get(stale_sym) or await asyncio.to_thread(
                    self.data_handler.fetch_order_book_snapshot, stale_sym
                )
                await asyncio.to_thread(
                    self.order_executor.execute_exit,
                    stale_pos,
                    stale_ob,
                    f"AI Slot Rotation -> {actionable_picks[0].symbol}: {rot_dec.reasoning}",
                )
            else:
                held_syms = ", ".join(self.order_executor.positions.keys())
                status_msg = (
                    f"All {len(self.order_executor.positions)}/{self.config.max_open_positions} portfolio slots full & healthy "
                    f"({held_syms}) • Market: {regime_state} • No slot rotation required on this candle."
                )
                self.ai_manager.record_scan_status(status_msg)
                self._update_runtime_status("MONITORING", status_msg)
                return

        self.ai_manager.record_scan_status(
            f"Scanned {len(recommendations)} stocks ({market_regime_summary}) • "
            f"Evaluating {len(actionable_picks)} actionable BUY candidate(s) for open portfolio slot(s)."
        )

        # 6b. Evaluate each actionable pick through RiskManager + AI Portfolio Manager
        for pick in actionable_picks:
            if len(self.order_executor.positions) >= self.config.max_open_positions:
                break

            logger.info(
                "Top Actionable Recommendation Selected: %s | Rating=%s | Score=%.1f/100 | Thesis: %s",
                pick.symbol,
                pick.rating,
                pick.score,
                pick.thesis,
            )
            try:
                ob = order_books.get(pick.symbol) or await asyncio.to_thread(
                    self.data_handler.fetch_order_book_snapshot, pick.symbol
                )
                order_books[pick.symbol] = ob
                latest_prices[pick.symbol] = ob.mid_price
            except Exception as exc:
                logger.error("[%s] Could not fetch quote for recommended pick: %s", pick.symbol, exc)
                continue

            total_equity, available_cash = await asyncio.to_thread(
                self.order_executor.get_account_equity_and_cash, latest_prices
            )

            plan = self.risk_manager.validate_and_build_trade_plan(
                signal=pick.signal,
                order_book=ob,
                total_equity=total_equity,
                available_quote=available_cash,
                open_positions_count=len(self.order_executor.positions),
            )
            if plan is None:
                continue

            size_mult = 1.0
            if self.config.enable_ai_manager:
                self._update_runtime_status(
                    "CONSULTING_AI",
                    f"Consulting Gemini AI on {pick.symbol} (Score {pick.score:.1f}/100, {pick.rating})...",
                )
                ai_dec = await asyncio.to_thread(
                    self.ai_manager.evaluate_entry_candidate,
                    pick,
                    self.order_executor.positions,
                    total_equity,
                    market_regime_summary,
                )
                logger.info(
                    "[AI Portfolio Manager] %s -> %s (Confidence=%d%%, SizeMult=%.2fx, Engine=%s) | %s",
                    pick.symbol,
                    ai_dec.decision,
                    ai_dec.confidence,
                    ai_dec.size_multiplier,
                    ai_dec.engine,
                    ai_dec.reasoning,
                )
                if ai_dec.decision == "VETO":
                    continue
                size_mult = ai_dec.size_multiplier

            if size_mult < 1.0:
                from dataclasses import replace

                plan = replace(
                    plan,
                    quantity=round(
                        plan.quantity * size_mult, self.config.fractional_decimals
                    ),
                    risk_amount_usd=plan.risk_amount_usd * size_mult,
                    notional_usd=plan.notional_usd * size_mult,
                )
            self._update_runtime_status(
                "EXECUTING_ORDER",
                f"Submitting {plan.symbol} BUY order ({plan.quantity:.4f} shares) to Trading 212...",
            )
            await asyncio.to_thread(
                self.order_executor.execute_entry, plan, ob
            )

        open_cnt = len(self.order_executor.positions)
        held_str = ", ".join(self.order_executor.positions.keys()) if open_cnt > 0 else "100% Cash"
        self._update_runtime_status(
            "MONITORING",
            f"Intra-bar SL/TP & 1R Trailing Stop guard active ({open_cnt}/{self.config.max_open_positions} slots: {held_str}) • "
            f"Waiting for next {self.config.timeframe} candle close.",
        )

    async def run_recommendations_only(self) -> None:
        """Scan the full Trading 212 stock universe and print the recommendation leaderboard without trading."""
        universe = self.screener.get_scan_universe()
        logger.info("Scanning %d Trading 212 stocks for recommendations...", len(universe))
        recommendations = await asyncio.to_thread(
            self.screener.scan_universe,
            self.order_executor.positions,
        )
        print(
            self.screener.format_leaderboard(
                recommendations, top_n=len(recommendations)
            )
        )

    async def execute_test_buy(self, raw_symbol: str) -> None:
        """Force a single risk-managed BUY signal on Demo/Paper to verify end-to-end order placement."""
        if self.config.execution_mode == "live":
            raise RuntimeError("--test-buy is disabled in 'live' mode for safety.")

        t212_ticker, _ = self.data_handler.resolve_ticker_pair(raw_symbol)
        logger.info("[%s] Running end-to-end DEMO test buy...", t212_ticker)

        ob = await asyncio.to_thread(
            self.data_handler.fetch_order_book_snapshot, raw_symbol
        )
        df = await asyncio.to_thread(
            self.data_handler.fetch_closed_ohlcv, raw_symbol
        )
        curr = df.iloc[-1]

        synthetic_signal = Signal(
            symbol=t212_ticker,
            action=SignalAction.BUY,
            candle_timestamp=curr["timestamp"],
            close_price=float(curr["close"]),
            ema_fast=float(curr["ema_fast"]),
            ema_slow=float(curr["ema_slow"]),
            rsi=float(curr["rsi"]),
            atr=float(curr["atr"]),
            reason="Manual --test-buy verification signal",
            target_side=Side.LONG,
            is_exit=False,
        )

        total_equity, available_cash = await asyncio.to_thread(
            self.order_executor.get_account_equity_and_cash,
            {t212_ticker: ob.mid_price},
        )
        plan = self.risk_manager.validate_and_build_trade_plan(
            signal=synthetic_signal,
            order_book=ob,
            total_equity=total_equity,
            available_quote=available_cash,
            open_positions_count=len(self.order_executor.positions),
        )
        if plan is not None:
            await asyncio.to_thread(self.order_executor.execute_entry, plan, ob)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Production-grade Modular Automated Trading Bot & Screener for Trading 212"
    )
    parser.add_argument(
        "--env",
        type=str,
        default=None,
        help="Optional path to .env configuration file",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Execute a single screening + trading cycle and exit immediately",
    )
    parser.add_argument(
        "--recommend",
        action="store_true",
        help="Scan all 25+ Trading 212 stocks and display the ranked recommendation leaderboard without placing orders",
    )
    parser.add_argument(
        "--test-buy",
        type=str,
        default=None,
        metavar="SYMBOL",
        help="Force a single risk-sized Demo/Paper BUY order (e.g. MSFT_US_EQ) to verify order execution immediately",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = Config.from_env(args.env)
    setup_logging(config.log_level, config.log_file)

    bot = TradingBot(config)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig_name, bot.request_shutdown)
        except NotImplementedError:
            pass

    try:
        if args.recommend:
            loop.run_until_complete(bot.run_recommendations_only())
        elif args.test_buy:
            loop.run_until_complete(bot.execute_test_buy(args.test_buy))
        else:
            loop.run_until_complete(bot.run(run_once=args.once))
    finally:
        loop.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
