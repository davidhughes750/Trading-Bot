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
from bot.telegram_notifier import TelegramNotifier

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

    # UK 3x Inverse Short ETPs that profit when US indices fall (bear-market hedge sleeve)
    INVERSE_ETP_SYMBOLS = {"QQQS_UK_EQ", "3USS_UK_EQ"}

    def __init__(self, config: Config) -> None:
        self.config = config
        self.t212_client: Optional[Trading212Client] = (
            Trading212Client(config)
            if config.execution_mode in {"demo", "live"}
            else None
        )
        self.telegram_notifier = TelegramNotifier(config)
        self.data_handler = DataHandler(config, t212_client=self.t212_client)
        self.strategy_engine = StrategyEngine(config)
        self.risk_manager = RiskManager(config, self.strategy_engine)
        self.order_executor = OrderExecutor(
            config,
            t212_client=self.t212_client,
            telegram_notifier=self.telegram_notifier,
            data_handler=self.data_handler,
        )
        self.screener = StockScreener(config, self.data_handler, self.strategy_engine)
        self.ai_manager = AIPortfolioManager(config)
        self.order_executor.on_trade_closed = self.ai_manager.record_loss_postmortem_async
        self.ai_manager.backfill_postmortems_from_trades(self.order_executor.closed_trades)

        self._stop_event = asyncio.Event()
        self._last_scan_bar_ts: Optional[str] = None
        self._latest_atr: Dict[str, float] = {}
        # Per-symbol "trend still strong" flag from the latest closed-bar scan,
        # used to decide whether to extend a take-profit instead of selling.
        self._trend_strong: Dict[str, bool] = {}
        self._market_regime: str = "BULLISH"
        self._market_regime_summary: str = f"Awaiting {config.market_benchmark_symbol} regime check"
        self._effective_min_score: float = config.min_recommendation_score
        self._last_daily_summary_date: Optional[str] = None

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

        telegram_task = None
        if not run_once and self.telegram_notifier.enabled:
            telegram_task = asyncio.create_task(self._run_telegram_listener())

        cb_alerted = self.risk_manager.circuit_breaker_tripped  # don't re-alert after a restart
        while not self._stop_event.is_set():
            try:
                await self.run_cycle()
            except Exception as exc:
                logger.exception("Unhandled error in trading cycle: %s", exc)

            # A tripped breaker no longer exits the process (systemd would restart it and
            # wipe the drawdown memory). The bot stays up in cooldown: no new entries,
            # dashboard + Telegram remain online, and it auto-resumes after the cooldown.
            if self.risk_manager.circuit_breaker_tripped and not cb_alerted:
                cb_alerted = True
                resume_at = self.risk_manager.circuit_breaker_resumes_at()
                logger.critical(
                    "Circuit breaker tripped — entering cooldown until %s UTC: %s",
                    resume_at.strftime("%Y-%m-%d %H:%M") if resume_at else "?",
                    self.risk_manager.circuit_breaker_reason,
                )
                if self.telegram_notifier.enabled:
                    await asyncio.to_thread(
                        self.telegram_notifier.send_circuit_breaker_alert,
                        self.risk_manager.circuit_breaker_reason,
                    )
            elif not self.risk_manager.circuit_breaker_tripped:
                cb_alerted = False

            if run_once:
                break

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=float(self.config.poll_interval_sec)
                )
            except asyncio.TimeoutError:
                pass

        if telegram_task and not telegram_task.done():
            telegram_task.cancel()

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

    def _is_uk_market_open(self) -> bool:
        """Return True during the regular London Stock Exchange (LSE) session (08:00-16:30 UK, Mon-Fri)."""
        if not getattr(self.config, "enable_uk_etp_sleeve", True):
            return False
        try:
            from zoneinfo import ZoneInfo

            now_uk = datetime.now(ZoneInfo("Europe/London"))
            if now_uk.weekday() >= 5:
                return False
            mins = now_uk.hour * 60 + now_uk.minute
            return (8 * 60) <= mins < (16 * 60 + 30)
        except Exception:
            return False

    def _is_in_pre_close_window(self, symbol: str) -> bool:
        """True during the last `eod_flat_minutes_before_close` minutes of `symbol`'s session.

        LSE closes 16:30 Europe/London; NYSE/Nasdaq close 16:00 ET (13:00 on early-close days).
        """
        if not self._is_market_open_for_symbol(symbol):
            return False
        window = int(getattr(self.config, "eod_flat_minutes_before_close", 10))
        try:
            from zoneinfo import ZoneInfo

            if str(symbol).endswith("_UK_EQ"):
                now_uk = datetime.now(ZoneInfo("Europe/London"))
                mins = now_uk.hour * 60 + now_uk.minute
                return mins >= (16 * 60 + 30) - window

            from bot.market_calendar import market_close_minute

            now_et = datetime.now(ZoneInfo("America/New_York"))
            mins = now_et.hour * 60 + now_et.minute
            return mins >= market_close_minute(now_et.date()) - window
        except Exception:
            return False

    def _is_market_open_for_symbol(self, symbol: str) -> bool:
        """Return True if the exchange for `symbol` (`_UK_EQ` -> LSE, `_US_EQ` -> NYSE/Nasdaq) is open."""
        if str(symbol).endswith("_UK_EQ"):
            return self._is_uk_market_open()
        return self._is_us_market_open()

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

    def _is_in_uk_opening_bell_window(self) -> bool:
        """Return True during the first `skip_opening_minutes` (08:00-08:15 UK) of the LSE market open."""
        if self.config.skip_opening_minutes <= 0:
            return False
        try:
            from zoneinfo import ZoneInfo

            now_uk = datetime.now(ZoneInfo("Europe/London"))
            if now_uk.weekday() >= 5:
                return False
            mins_since_midnight = now_uk.hour * 60 + now_uk.minute
            open_min = 8 * 60
            return open_min <= mins_since_midnight < (open_min + self.config.skip_opening_minutes)
        except Exception:
            return False

    def _is_in_opening_bell_for_symbol(self, symbol: str) -> bool:
        """Return True if `symbol`'s exchange is within its opening-bell whipsaw guard window."""
        if str(symbol).endswith("_UK_EQ"):
            return self._is_in_uk_opening_bell_window()
        return self._is_in_opening_bell_window()

    def _count_us_positions(self) -> int:
        """Return number of currently open US equity positions."""
        return sum(
            1 for sym in self.order_executor.positions if not str(sym).endswith("_UK_EQ")
        )

    def _count_uk_positions(self) -> int:
        """Return number of currently open UK ETP sleeve positions."""
        return sum(
            1 for sym in self.order_executor.positions if str(sym).endswith("_UK_EQ")
        )

    def _has_open_slot_for_symbol(self, symbol: str) -> bool:
        """Return True if both total portfolio capacity and the symbol's regional sleeve (3 US + 1 UK) have an open slot."""
        if len(self.order_executor.positions) >= self.config.max_open_positions:
            return False
        if str(symbol).endswith("_UK_EQ"):
            max_uk = min(
                self.config.max_open_positions,
                getattr(self.config, "max_uk_positions", 1),
            )
            return self._count_uk_positions() < max_uk
        max_us = min(
            self.config.max_open_positions,
            getattr(self.config, "max_us_positions", 3),
        )
        return self._count_us_positions() < max_us

    def _required_min_score_for_symbol(
        self, symbol: str, regime_state: str, effective_min_score: float
    ) -> float:
        """Return the regime-adjusted minimum score threshold for `symbol`.

        Standard long equities/ETPs require higher scores in CAUTIOUS (80) or BEARISH (86)
        market regimes. Inverse 3x Short ETPs (`QQQS_UK_EQ`, `3USS_UK_EQ`) are designed to
        profit during BEARISH/CAUTIOUS downturns, so they use the base sniper threshold (76)
        when the market is BEARISH/CAUTIOUS, and require >=80 during a BULLISH market regime.
        """
        if str(symbol) in self.INVERSE_ETP_SYMBOLS:
            if regime_state in {"BEARISH", "CAUTIOUS"}:
                return float(self.config.min_recommendation_score)
            return max(float(self.config.min_recommendation_score), 80.0)
        return effective_min_score

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
            if not self.risk_manager.circuit_breaker_tripped:
                # Fresh equity baseline (e.g. demo account reset). A tripped breaker is NOT cleared here.
                self.risk_manager._equity_history.clear()

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
            resume_at = self.risk_manager.circuit_breaker_resumes_at()
            self._update_runtime_status(
                "CIRCUIT_BREAKER_COOLDOWN",
                f"New entries paused until {resume_at.strftime('%a %H:%M') if resume_at else '?'} UTC • "
                f"{self.risk_manager.circuit_breaker_reason}",
            )
            return

        # 2a. End-of-day flat rule: close positions shortly before their exchange shuts
        if getattr(self.config, "eod_flat_enabled", True):
            for sym, pos in list(self.order_executor.positions.items()):
                ob = order_books.get(sym)
                if ob is None or not self._is_in_pre_close_window(sym):
                    continue
                mark = ob.bid if pos.side.value == "LONG" else ob.ask
                r_now = pos.current_r_multiple(mark)
                is_uk = str(sym).endswith("_UK_EQ")
                if is_uk or r_now < self.config.eod_hold_min_r:
                    why = (
                        "UK 3x ETP never held overnight (LSE shut while US trades)"
                        if is_uk
                        else f"below +{self.config.eod_hold_min_r:.1f}R ({r_now:+.2f}R)"
                    )
                    logger.info("[%s] End-of-day flat exit: %s", sym, why)
                    await asyncio.to_thread(
                        self.order_executor.execute_exit, pos, ob, f"End-of-day flat: {why}"
                    )

        # 2. Intra-bar management of open positions (SL / TP / 1R Trailing Stop with anti-whipsaw buffer)
        for sym, pos in list(self.order_executor.positions.items()):
            ob = order_books.get(sym)
            if ob is None:
                continue
            if self.config.require_market_open_for_entries and not self._is_market_open_for_symbol(sym):
                continue

            mark_price = ob.bid if pos.side.value == "LONG" else ob.ask
            journey_recorded = pos.record_price_point(mark_price)
            prev_sl = pos.stop_loss
            prev_tp = pos.take_profit
            exit_action, exit_reason = self.strategy_engine.evaluate_position_exit_and_trail(
                position=pos,
                current_price=mark_price,
                current_atr=self._latest_atr.get(sym),
                is_candle_close=False,
                trend_strong=self._trend_strong.get(sym),
            )
            if pos.stop_loss > prev_sl:
                self.order_executor.save_state()
                # Only notify Telegram when crossing into 100% Risk-Free Breakeven (Stop >= Entry)
                # to prevent buzzing your phone every 15 seconds on fractional cent ticks.
                crossed_breakeven = (prev_sl < pos.entry_price <= pos.stop_loss)
                if crossed_breakeven and self.telegram_notifier and getattr(self.telegram_notifier, "enabled", False):
                    await asyncio.to_thread(
                        self.telegram_notifier.send_breakeven_alert,
                        pos.symbol,
                        pos.entry_price,
                        pos.stop_loss,
                        mark_price,
                    )
            elif pos.take_profit != prev_tp or journey_recorded:
                self.order_executor.save_state()

            if exit_action != SignalAction.HOLD:
                logger.info("[%s] Intra-bar protective exit triggered: %s", sym, exit_reason)
                await asyncio.to_thread(
                    self.order_executor.execute_exit, pos, ob, exit_reason
                )

        # 3. Check if a new closed candle is available using active market benchmark ticker
        universe = self.screener.get_scan_universe()
        probe_symbol = universe[0]
        if self._is_uk_market_open() and not self._is_us_market_open():
            uk_candidates = [s for s in universe if str(s).endswith("_UK_EQ")]
            if uk_candidates:
                probe_symbol = uk_candidates[0]
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
            # Backfill journey waypoints from closed 15m candles if position was opened prior to history tracking
            if len(open_pos.price_history) <= 2 and rec.candles:
                try:
                    opened_dt = datetime.fromisoformat(str(open_pos.opened_at).replace("Z", "+00:00"))
                    if opened_dt.tzinfo is None:
                        opened_dt = opened_dt.replace(tzinfo=timezone.utc)
                    backfilled = [{"ts": open_pos.opened_at, "price": round(float(open_pos.entry_price), 4)}]
                    for c in rec.candles:
                        c_iso = str(c.get("ts_iso") or "")
                        if c_iso:
                            c_dt = datetime.fromisoformat(c_iso.replace("Z", "+00:00"))
                            if c_dt.tzinfo is None:
                                c_dt = c_dt.replace(tzinfo=timezone.utc)
                            if c_dt >= opened_dt:
                                backfilled.append({"ts": c_iso, "price": round(float(c.get("c", open_pos.entry_price)), 4)})
                    if len(backfilled) > len(open_pos.price_history):
                        open_pos.price_history = backfilled
                        self.order_executor.save_state()
                except Exception:
                    pass
            if self.config.require_market_open_for_entries and not self._is_market_open_for_symbol(rec.symbol):
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

        us_open = self._is_us_market_open()
        uk_open = self._is_uk_market_open()

        # Check if we should automatically dispatch the End-of-Day Daily Summary after US close
        if not us_open:
            try:
                from zoneinfo import ZoneInfo
                from bot.market_calendar import is_trading_day, market_close_minute
                now_et = datetime.now(ZoneInfo("America/New_York"))
                today_str = now_et.strftime("%Y-%m-%d")
                close_min = market_close_minute(now_et.date())
                current_min = now_et.hour * 60 + now_et.minute
                if (
                    is_trading_day(now_et.date())
                    and current_min >= close_min
                    and self._last_daily_summary_date != today_str
                    and self.telegram_notifier
                    and getattr(self.telegram_notifier, "enabled", False)
                ):
                    self._last_daily_summary_date = today_str
                    await self._dispatch_daily_summary()
            except Exception as exc:
                logger.warning("Error checking daily summary trigger: %s", exc)

        # 5a. Never place new entries while both US and UK markets are closed (weekends / overnight)
        if self.config.require_market_open_for_entries and not (us_open or uk_open):
            msg = (
                "US & UK markets closed — scan complete, new entries paused until the next "
                "regular session (08:00 London / 09:30 ET). Open positions remain protected."
            )
            logger.info("%s", msg)
            self.ai_manager.record_scan_status(msg)
            self._update_runtime_status("MARKET_CLOSED", msg)
            return

        # 5b. Skip new entries if the only open market is in its first 15-minute opening-bell window
        us_bell = us_open and self._is_in_opening_bell_window()
        uk_bell = uk_open and self._is_in_uk_opening_bell_window()
        if (us_open and not uk_open and us_bell) or (uk_open and not us_open and uk_bell) or (us_bell and uk_bell):
            bell_label = "UK LSE (08:00 UK)" if (uk_bell and not us_bell) else "US (09:30 ET)"
            msg = (
                f"{bell_label} opening-bell whipsaw guard active (first {self.config.skip_opening_minutes}m) — "
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
            if self.config.require_market_open_for_entries and not self._is_market_open_for_symbol(r.symbol):
                continue
            if self._is_in_opening_bell_for_symbol(r.symbol):
                logger.info("[%s] Deferring pick during exchange opening-bell whipsaw guard window.", r.symbol)
                continue
            if getattr(self.config, "eod_flat_enabled", True) and self._is_in_pre_close_window(r.symbol):
                logger.info("[%s] Skipping pick during exchange pre-close EOD flat window.", r.symbol)
                continue
            if self.order_executor.is_in_cooldown(r.symbol):
                logger.info("[%s] Skipping actionable pick: ticker is in post-loss cooldown.", r.symbol)
                continue
            req_score = self._required_min_score_for_symbol(
                r.symbol, regime_state, effective_min_score
            )
            if r.score < req_score:
                logger.info(
                    "[%s] Skipping pick (score %.1f < regime-adjusted threshold %.1f for %s market).",
                    r.symbol,
                    r.score,
                    req_score,
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

        # 6a. AI Smart Slot Rotation: if a regional sleeve (3 US or 1 UK) is full and a new
        # STRONG BUY (>=80) appears for that sleeve while its exchange is open, check if we should
        # rotate out of a stagnant/deteriorating position in the same open exchange sleeve.
        pre_approved_rotations: Dict[str, Any] = {}
        top_pick = actionable_picks[0]
        if not self._has_open_slot_for_symbol(top_pick.symbol):
            is_uk_pick = str(top_pick.symbol).endswith("_UK_EQ")
            eligible_held = {
                sym: pos
                for sym, pos in self.order_executor.positions.items()
                if (str(sym).endswith("_UK_EQ") == is_uk_pick)
                and self._is_market_open_for_symbol(sym)
            }
            rot_dec = None
            if (
                self.config.enable_ai_manager
                and top_pick.score >= 80.0
                and eligible_held
            ):
                rot_dec = await asyncio.to_thread(
                    self.ai_manager.evaluate_slot_rotation,
                    top_pick,
                    eligible_held,
                    recommendations,
                    latest_prices,
                )
            if (
                rot_dec is not None
                and rot_dec.decision == "ROTATE"
                and rot_dec.replace_symbol in eligible_held
            ):
                stale_sym = rot_dec.replace_symbol
                stale_pos = self.order_executor.positions[stale_sym]
                logger.info(
                    "[AI Portfolio Manager] SLOT ROTATION APPROVED (%s, conf=%d%%): Closing %s -> Buying %s | %s",
                    rot_dec.engine,
                    rot_dec.confidence,
                    stale_sym,
                    top_pick.symbol,
                    rot_dec.reasoning,
                )
                stale_ob = order_books.get(stale_sym) or await asyncio.to_thread(
                    self.data_handler.fetch_order_book_snapshot, stale_sym
                )
                exit_res = await asyncio.to_thread(
                    self.order_executor.execute_exit,
                    stale_pos,
                    stale_ob,
                    f"AI Slot Rotation -> {top_pick.symbol}: {rot_dec.reasoning}",
                )
                if exit_res is not None and exit_res.success:
                    pre_approved_rotations[top_pick.symbol] = rot_dec

        # Check if at least one actionable pick has an available regional slot (3 US + 1 UK)
        actionable_with_slot = [
            p for p in actionable_picks if self._has_open_slot_for_symbol(p.symbol)
        ]
        if not actionable_with_slot:
            held_syms = ", ".join(self.order_executor.positions.keys())
            status_msg = (
                f"Portfolio sleeve slots full & healthy ({len(self.order_executor.positions)}/{self.config.max_open_positions}: "
                f"US {self._count_us_positions()}/{getattr(self.config, 'max_us_positions', 3)}, "
                f"UK {self._count_uk_positions()}/{getattr(self.config, 'max_uk_positions', 1)} — {held_syms}) • "
                f"Market: {regime_state} • No slot rotation required on this candle."
            )
            self.ai_manager.record_scan_status(status_msg)
            self._update_runtime_status("MONITORING", status_msg)
            return

        self.ai_manager.record_scan_status(
            f"Scanned {len(recommendations)} stocks ({market_regime_summary}) • "
            f"Evaluating {len(actionable_with_slot)} actionable BUY candidate(s) for open portfolio slot(s)."
        )

        # 6b. Evaluate each actionable pick through RiskManager + AI Portfolio Manager
        for pick in actionable_picks:
            if not self._has_open_slot_for_symbol(pick.symbol):
                continue

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

            from dataclasses import replace

            plan = replace(
                plan,
                score=getattr(pick, "score", 0.0),
                rating=getattr(pick, "rating", "STRONG BUY"),
                rvol=getattr(pick, "rvol", 1.0),
                thesis=getattr(pick, "thesis", ""),
            )

            size_mult = 1.0
            if self.config.enable_ai_manager:
                if pick.symbol in pre_approved_rotations:
                    ai_dec = pre_approved_rotations[pick.symbol]
                    logger.info(
                        "[AI Portfolio Manager] %s -> PRE-APPROVED via Atomic Slot Rotation (Confidence=%d%%, SizeMult=%.2fx, Engine=%s)",
                        pick.symbol,
                        ai_dec.confidence,
                        ai_dec.size_multiplier,
                        ai_dec.engine,
                    )
                    size_mult = ai_dec.size_multiplier
                else:
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
            opened_pos = await asyncio.to_thread(
                self.order_executor.execute_entry, plan, ob
            )
            if opened_pos is not None:
                opened_pos.entry_context = {
                    "score": round(float(getattr(pick, "score", 0.0)), 1),
                    "rating": str(getattr(pick, "rating", "")),
                    "rsi": round(float(getattr(pick, "rsi", 0.0)), 2),
                    "atr": round(float(getattr(pick, "atr", 0.0)), 4),
                    "rvol": round(float(getattr(pick, "rvol", 1.0)), 2),
                    "roc_10_pct": round(float(getattr(pick, "roc_10_pct", 0.0)), 2),
                    "thesis": str(getattr(pick, "thesis", "")),
                    "market_regime": regime_state,
                    "ai_confidence": int(getattr(ai_dec, "confidence", 0)) if self.config.enable_ai_manager else None,
                    "ai_engine": str(getattr(ai_dec, "engine", "")) if self.config.enable_ai_manager else None,
                    "ai_reasoning": str(getattr(ai_dec, "reasoning", "")) if self.config.enable_ai_manager else "",
                }
                self.order_executor.save_state()

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

    def _fetch_telegram_updates(self, offset: int) -> list:
        """Fetch incoming Telegram messages for remote control."""
        if not self.telegram_notifier or not self.telegram_notifier.enabled:
            return []
        try:
            import requests
            resp = requests.get(
                f"{self.telegram_notifier.base_url}/getUpdates",
                params={"offset": offset, "timeout": 2},
                timeout=6,
            )
            if resp.status_code == 200:
                return resp.json().get("result", [])
        except Exception:
            pass
        return []

    async def _handle_telegram_command(self, cmd_text: str) -> None:
        """Process remote commands sent by David from his iPhone."""
        import json
        cmd_parts = cmd_text.strip().split()
        cmd = cmd_parts[0].lower().split("@")[0]
        arg = cmd_parts[1].upper() if len(cmd_parts) > 1 else ""

        if cmd in {"/start", "/help"}:
            help_text = (
                "🤖 <b>Trading 212 Quant Bot Commands</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• <b>/recommendations</b> (or <b>/screener</b>) - 🔍 Top ranked picks across all 71 assets\n"
                "• <b>/positions</b> - 📦 Active positions, stop-loss &amp; PnL\n"
                "• <b>/status</b> - 📊 Live portfolio equity, cash &amp; US/UK market state\n"
                "• <b>/uk</b> (or <b>/etp</b>) - 🇬🇧 8 UK 3x Leveraged ETPs (QQQ3, 3LUS, 3LSE, 3NVD...)\n"
                "• <b>/chart [TICKER]</b> - 🕯️ 15m chart (e.g. <code>/chart QQQ3</code> or <code>/chart NVDA</code>)\n"
                "• <b>/summary</b> - 📈 Executive Daily Summary (PnL, trades &amp; chart)\n"
                "• <b>/help</b> - Show this help menu"
            )
            await asyncio.to_thread(self.telegram_notifier.send_message, help_text)

        elif cmd in {"/summary", "/daily"}:
            await self._dispatch_daily_summary(is_manual=True)

        elif cmd == "/status":
            try:
                tot_eq, free_cash = await asyncio.to_thread(
                    self.order_executor.get_account_equity_and_cash, {}
                )
                open_cnt = len(self.order_executor.positions)
                held_str = ", ".join(self.order_executor.positions.keys()) if open_cnt > 0 else "100% Cash"
                us_open = self._is_us_market_open()
                uk_open = self._is_uk_market_open()
                us_str = "🟢 OPEN (09:30–16:00 ET)" if us_open else "🔴 CLOSED"
                uk_str = "🟢 OPEN (08:00–16:30 UK)" if uk_open else "🔴 CLOSED"
                status_text = (
                    f"📊 <b>Portfolio Telemetry</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 <b>Total Equity:</b> ${tot_eq:,.2f}\n"
                    f"💵 <b>Free Cash:</b> ${free_cash:,.2f}\n"
                    f"📦 <b>Active Slots:</b> {open_cnt}/{self.config.max_open_positions} ({held_str})\n"
                    f"🇬🇧 <b>UK LSE Session:</b> {uk_str}\n"
                    f"🇺🇸 <b>US Session:</b> {us_str}\n"
                    f"📈 <b>Regime:</b> {self._market_regime} ({self.config.market_benchmark_symbol})\n"
                    f"🤖 <b>AI Manager:</b> {self.ai_manager.active_engine_label}\n"
                )
                await asyncio.to_thread(self.telegram_notifier.send_message, status_text)
            except Exception as exc:
                await asyncio.to_thread(self.telegram_notifier.send_message, f"❌ Status lookup error: {exc}")

        elif cmd == "/positions":
            if not self.order_executor.positions:
                await asyncio.to_thread(
                    self.telegram_notifier.send_message,
                    "📦 <b>No Open Positions</b>\nPortfolio is currently 100% cash, standing pat for sniper entries."
                )
                return

            lines = ["📦 <b>Active Open Positions</b>", "━━━━━━━━━━━━━━━━━━━━"]
            for sym, pos in self.order_executor.positions.items():
                is_uk = str(sym).endswith("_UK_EQ")
                clean_sym = sym.replace("_UK_EQ", ".L") if is_uk else sym.replace("_US_EQ", "")
                ccy = "£" if is_uk else "$"
                try:
                    ob = await asyncio.to_thread(self.data_handler.fetch_order_book_snapshot, sym)
                    cur_price = ob.mid_price
                except Exception:
                    cur_price = pos.entry_price

                pnl = (cur_price - pos.entry_price) * pos.quantity
                pnl_pct = (cur_price - pos.entry_price) / pos.entry_price * 100.0 if pos.entry_price > 0 else 0.0
                sign = "+" if pnl >= 0 else "-"
                init_sl = pos.initial_stop_loss or pos.stop_loss
                r_mult = (cur_price - pos.entry_price) / max(pos.entry_price - init_sl, 0.001)

                lines.append(
                    f"• <b>{clean_sym}</b> ({pos.side.value}): {pos.quantity:.4f} shares\n"
                    f"  Entry: {ccy}{pos.entry_price:.2f} ➔ Current: {ccy}{cur_price:.2f}\n"
                    f"  PnL: <b>{sign}{ccy}{abs(pnl):.2f}</b> ({pnl_pct:+.2f}%, {r_mult:+.2f}R)\n"
                    f"  SL: {ccy}{pos.stop_loss:.2f} | TP: {ccy}{pos.take_profit:.2f}\n"
                )
            await asyncio.to_thread(self.telegram_notifier.send_message, "\n".join(lines))

        elif cmd in {"/uk", "/etp", "/etps"}:
            try:
                uk_names = {
                    "QQQ3_UK_EQ": "📈 WisdomTree NASDAQ 100 3x Bull (GBP)",
                    "3LUS_UK_EQ": "📈 WisdomTree S&P 500 3x Bull (GBP)",
                    "3LSE_UK_EQ": "📈 WisdomTree Semiconductor 3x Bull (GBP)",
                    "3NVD_UK_EQ": "📈 Leverage Shares 3x NVIDIA Bull (GBP)",
                    "3TSL_UK_EQ": "📈 Leverage Shares 3x Tesla Bull (GBP)",
                    "3LGO_UK_EQ": "📈 WisdomTree Physical Gold 3x Bull (GBP)",
                    "QQQS_UK_EQ": "📉 WisdomTree NASDAQ 100 3x Short Hedge (GBP)",
                    "3USS_UK_EQ": "📉 WisdomTree S&P 500 3x Short Hedge (GBP)",
                }
                uk_open = self._is_uk_market_open()
                uk_status = "🟢 LSE OPEN (08:00–16:30 UK)" if uk_open else "🔴 LSE CLOSED (Opens 08:00 UK)"

                rec_path = Path("logs/recommendations.json")
                all_recs = []
                if rec_path.exists():
                    data = json.loads(rec_path.read_text(encoding="utf-8"))
                    all_recs = data.get("recommendations", [])

                uk_recs = [r for r in all_recs if str(r.get("symbol", "")).endswith("_UK_EQ")]
                total_scanned = len(all_recs) or len(self.config.universe)

                lines = [
                    "🇬🇧 <b>UK 3x Bull &amp; Bear ETP Sleeve (GBP)</b>",
                    f"🏛️ <b>Session:</b> {uk_status}",
                    "💸 <b>Fees:</b> 0% Stamp Duty • 0% FX Fee",
                    "━━━━━━━━━━━━━━━━━━━━",
                ]

                if not uk_recs:
                    lines.append("ℹ️ UK ETP data is currently refreshing; please try again in a few seconds.")
                else:
                    for r in uk_recs:
                        raw_sym = str(r.get("symbol", ""))
                        disp_sym = raw_sym.replace("_UK_EQ", ".L")
                        desc_name = uk_names.get(raw_sym, "UK 3x Leveraged ETP")
                        rank = r.get("rank", 0)
                        score = float(r.get("score", 0.0))
                        rating = r.get("rating", "WATCH")
                        price = float(r.get("close_price", 0.0))
                        roc = float(r.get("roc_10_pct", 0.0))
                        rsi = float(r.get("rsi", 50.0))
                        rvol = float(r.get("rvol", 1.0))
                        sl = float(r.get("suggested_stop_loss", 0.0))
                        tp = float(r.get("suggested_take_profit", 0.0))
                        blocker = r.get("blocker") or ""

                        rating_icon = "🟢" if "BUY" in rating else ("🟡" if rating == "WATCH" else "🔴")
                        entry_Block = (
                            f"{rating_icon} <b>{disp_sym}</b> — {desc_name}\n"
                            f"  • <b>Rank:</b> #{rank}/{total_scanned} | <b>Score:</b> {score:.1f}/100 (<b>{rating}</b>)\n"
                            f"  • <b>Price:</b> £{price:.2f} ({roc:+.2f}% 10-bar)\n"
                            f"  • <b>RSI:</b> {rsi:.1f} | <b>RVOL:</b> {rvol:.2f}x\n"
                            f"  • <b>Brackets:</b> SL £{sl:.2f} | TP £{tp:.2f}"
                        )
                        if blocker:
                            entry_Block += f"\n  • ⚠️ <i>{blocker}</i>"
                        lines.append(entry_Block + "\n")

                lines.append("💡 <i>Tip: Send <code>/chart QQQ3</code>, <code>/chart 3TSL</code>, <code>/chart 3NVD</code>, etc. for a live 15m chart.</i>")
                await asyncio.to_thread(self.telegram_notifier.send_message, "\n".join(lines))
            except Exception as exc:
                await asyncio.to_thread(self.telegram_notifier.send_message, f"❌ UK ETP lookup error: {exc}")

        elif cmd in {"/screener", "/top", "/recommendations", "/recommend", "/recs", "/rec", "/leaderboard"}:
            try:
                rec_path = Path("logs/recommendations.json")
                if rec_path.exists():
                    data = json.loads(rec_path.read_text(encoding="utf-8"))
                    recs = data.get("recommendations", [])[:5]
                    lines = ["🔍 <b>Top 5 Screener Recommendations (US + UK)</b>", "━━━━━━━━━━━━━━━━━━━━"]
                    for r in recs:
                        raw_sym = str(r.get("symbol", ""))
                        is_uk = raw_sym.endswith("_UK_EQ")
                        sym = raw_sym.replace("_UK_EQ", ".L") if is_uk else raw_sym.replace("_US_EQ", "")
                        ccy = "£" if is_uk else "$"
                        lines.append(
                            f"#{r.get('rank', 0)} <b>{sym}</b> • {r.get('score', 0):.1f}/100 ({r.get('rating')})\n"
                            f"  Price: {ccy}{r.get('close_price', 0):.2f} | RVOL: {r.get('rvol', 1.0):.2f}x\n"
                        )
                    lines.append("🇬🇧 <i>Send <code>/uk</code> to view the 8 UK 3x Bull &amp; Short ETPs.</i>")
                    await asyncio.to_thread(self.telegram_notifier.send_message, "\n".join(lines))
                else:
                    await asyncio.to_thread(self.telegram_notifier.send_message, "ℹ️ Screener running; data updating.")
            except Exception as exc:
                await asyncio.to_thread(self.telegram_notifier.send_message, f"❌ Screener lookup error: {exc}")

        elif cmd == "/chart":
            target_sym = None
            uk_aliases = {
                "QQQ3": "QQQ3_UK_EQ",
                "QQQ3.L": "QQQ3_UK_EQ",
                "LQQ3": "QQQ3_UK_EQ",
                "LQQ3.L": "QQQ3_UK_EQ",
                "3LUS": "3LUS_UK_EQ",
                "3LUS.L": "3LUS_UK_EQ",
                "3LSE": "3LSE_UK_EQ",
                "3LSE.L": "3LSE_UK_EQ",
                "3SMC": "3LSE_UK_EQ",
                "3SMC.L": "3LSE_UK_EQ",
                "3NVD": "3NVD_UK_EQ",
                "3NVD.L": "3NVD_UK_EQ",
                "3TSL": "3TSL_UK_EQ",
                "3TSL.L": "3TSL_UK_EQ",
                "3LGO": "3LGO_UK_EQ",
                "3LGO.L": "3LGO_UK_EQ",
                "QQQS": "QQQS_UK_EQ",
                "QQQS.L": "QQQS_UK_EQ",
                "LQQS": "QQQS_UK_EQ",
                "LQQS.L": "QQQS_UK_EQ",
                "3USS": "3USS_UK_EQ",
                "3USS.L": "3USS_UK_EQ",
                "3ULS": "3USS_UK_EQ",
                "3ULS.L": "3USS_UK_EQ",
            }
            if arg:
                if arg in uk_aliases:
                    target_sym = uk_aliases[arg]
                elif arg.endswith(".L"):
                    target_sym = f"{arg[:-2]}_UK_EQ"
                elif "_UK" in arg or "_US" in arg:
                    target_sym = arg
                else:
                    target_sym = f"{arg}_US_EQ"
            elif self.order_executor.positions:
                target_sym = list(self.order_executor.positions.keys())[0]

            if not target_sym:
                await asyncio.to_thread(
                    self.telegram_notifier.send_message,
                    "ℹ️ Please specify a ticker (e.g. <code>/chart QQQ3</code>, <code>/chart 3LUS</code>, or <code>/chart NVDA</code>)."
                )
                return

            try:
                df = await asyncio.to_thread(self.data_handler.fetch_closed_ohlcv, target_sym)
                pos = self.order_executor.positions.get(target_sym)
                entry_p = pos.entry_price if pos else None
                sl_p = pos.stop_loss if pos else None
                tp_p = pos.take_profit if pos else None

                photo = self.telegram_notifier.generate_candlestick_chart(
                    symbol=target_sym,
                    df=df,
                    entry_price=entry_p,
                    stop_loss=sl_p,
                    take_profit=tp_p,
                    title_suffix="Live 15m Chart",
                )
                is_uk = target_sym.endswith("_UK_EQ")
                clean_sym = target_sym.replace("_UK_EQ", ".L") if is_uk else target_sym.replace("_US_EQ", "")
                ccy = "£" if is_uk else "$"
                curr_c = float(df["close"].iloc[-1])
                caption = f"📈 <b>{clean_sym}</b> • Current Price: <b>{ccy}{curr_c:.2f}</b> (15m Timeframe)"
                if pos:
                    pnl = (curr_c - pos.entry_price) * pos.quantity
                    pnl_sign = "+" if pnl >= 0 else "-"
                    caption += f"\nPosition: {pos.quantity:.4f} shares | PnL: <b>{pnl_sign}{ccy}{abs(pnl):.2f}</b>"

                if photo:
                    await asyncio.to_thread(self.telegram_notifier.send_photo, photo, caption)
                else:
                    await asyncio.to_thread(self.telegram_notifier.send_message, f"❌ Could not render chart for {clean_sym}.")
            except Exception as exc:
                await asyncio.to_thread(self.telegram_notifier.send_message, f"❌ Chart error for {target_sym}: {exc}")

        else:
            await asyncio.to_thread(
                self.telegram_notifier.send_message,
                f"❓ <b>Unrecognized command:</b> <code>{cmd}</code>\n\n"
                "Available commands:\n"
                "• <b>/recommendations</b> (or <b>/screener</b>) — Top ranked picks\n"
                "• <b>/positions</b> — Active open positions &amp; live PnL\n"
                "• <b>/status</b> — Portfolio equity &amp; market regime\n"
                "• <b>/uk</b> — 8 UK 3x Leveraged ETPs (0% FX fee)\n"
                "• <b>/chart [TICKER]</b> — 15m Candlestick chart\n"
                "• <b>/summary</b> — Executive Daily Summary\n"
                "• <b>/help</b> — Show full command menu"
            )

    async def _dispatch_daily_summary(self, is_manual: bool = False) -> None:
        """Collect end-of-day performance stats and dispatch daily summary to Telegram."""
        if not self.telegram_notifier or not self.telegram_notifier.enabled:
            return

        try:
            from zoneinfo import ZoneInfo
            now_et = datetime.now(ZoneInfo("America/New_York"))
            date_str = now_et.strftime("%A, %b %d, %Y")
            today_iso = now_et.strftime("%Y-%m-%d")

            total_equity, free_cash = await asyncio.to_thread(
                self.order_executor.get_account_equity_and_cash, {}
            )

            # Filter trades closed today
            closed_today = [
                t for t in self.order_executor.closed_trades
                if t.get("closed_at", "").startswith(today_iso)
            ]
            daily_realized_pnl = sum(float(t.get("net_pnl", 0.0)) for t in closed_today)

            # Gather open positions details
            open_pos_list = []
            unrealized_pnl = 0.0
            for sym, pos in self.order_executor.positions.items():
                try:
                    ob = await asyncio.to_thread(self.data_handler.fetch_order_book_snapshot, sym)
                    cur_price = ob.mid_price
                except Exception:
                    cur_price = pos.entry_price

                pnl = (cur_price - pos.entry_price) * pos.quantity
                pnl_pct = (cur_price - pos.entry_price) / pos.entry_price * 100.0 if pos.entry_price > 0 else 0.0
                init_sl = pos.initial_stop_loss or pos.stop_loss
                r_mult = (cur_price - pos.entry_price) / max(pos.entry_price - init_sl, 0.001)
                unrealized_pnl += pnl

                open_pos_list.append({
                    "symbol": sym,
                    "side": pos.side.value,
                    "quantity": pos.quantity,
                    "entry_price": pos.entry_price,
                    "current_price": cur_price,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                    "unrealized_pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "r_multiple": r_mult,
                })

            # Read top picks from recommendations.json
            top_picks = []
            try:
                rec_path = Path("logs/recommendations.json")
                if rec_path.exists():
                    rec_data = json.loads(rec_path.read_text(encoding="utf-8"))
                    top_picks = rec_data.get("recommendations", [])[:3]
            except Exception:
                pass

            await asyncio.to_thread(
                self.telegram_notifier.send_daily_summary,
                date_str=date_str,
                total_equity=total_equity,
                free_cash=free_cash,
                daily_realized_pnl=daily_realized_pnl,
                unrealized_pnl=unrealized_pnl,
                closed_trades_today=closed_today,
                open_positions=open_pos_list,
                market_regime=self._market_regime,
                top_picks=top_picks,
            )
            logger.info("Daily summary dispatched to Telegram (%s)", date_str)
        except Exception as exc:
            logger.error("Failed to dispatch daily summary: %s", exc)
            if is_manual:
                await asyncio.to_thread(
                    self.telegram_notifier.send_message,
                    f"❌ Could not compile daily summary: {exc}"
                )

    async def _run_telegram_listener(self) -> None:
        """Background loop that listens for remote commands sent from Telegram."""
        if not self.telegram_notifier or not self.telegram_notifier.enabled:
            return
        await asyncio.to_thread(self.telegram_notifier.register_bot_commands)
        offset = 0
        logger.info("Telegram interactive command listener started (chat_id=%s)", self.telegram_notifier.chat_id)
        while not self._stop_event.is_set():
            try:
                updates = await asyncio.to_thread(self._fetch_telegram_updates, offset)
                for update in updates:
                    offset = max(offset, update["update_id"] + 1)
                    msg = update.get("message") or {}
                    chat = msg.get("chat") or {}
                    if str(chat.get("id")) != self.telegram_notifier.chat_id:
                        continue
                    text = (msg.get("text") or "").strip()
                    if text.startswith("/"):
                        await self._handle_telegram_command(text)
            except Exception as exc:
                logger.debug("Telegram polling error: %s", exc)
            await asyncio.sleep(2)


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
