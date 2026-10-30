#!/usr/bin/env python3
"""Main execution loop and CLI entry point for the Trading 212 Automated Trading Bot.

Usage:
    python main.py                        # Run the bot: scan the universe each candle and trade the best picks
    python main.py --recommend            # Scan the universe and print the ranked leaderboard only
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
import time
from dataclasses import replace
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bot import __version__
from bot.ai_manager import AIPortfolioManager
from bot.config import Config
from bot.data_handler import DataHandler
from bot.fx import FxConverter
from bot.market_calendar import (
    in_opening_window,
    in_pre_close_window,
    is_session_open,
    is_trading_day,
    market_close_minute,
)
from bot.models import OrderBookSnapshot, Side, Signal, SignalAction, TradePlan
from bot.order_executor import OrderExecutor
from bot.risk_manager import RiskManager, has_open_slot, required_min_score
from bot.screener import StockScreener
from bot.strategy_engine import StrategyEngine, classify_market_regime
from bot.t212_client import Trading212Client
from bot.telegram_notifier import TelegramNotifier
from bot.utils import append_jsonl, atomic_write_json

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
    """Asynchronous orchestrator coordinating the screener, Trading 212 API, strategy and risk.

    Each cycle (every POLL_INTERVAL_SEC):
      1. Sync positions with Trading 212 and fetch quotes for held symbols.
      2. Record equity and check the 24h drawdown circuit breaker.
      3. Apply the end-of-day flat rule and manage stops/targets intra-bar.
      4. On a newly closed candle: scan the universe, log every candidate,
         run candle-close exits, then look for new entries.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.t212_client: Optional[Trading212Client] = (
            Trading212Client(config)
            if config.execution_mode in {"demo", "live"}
            else None
        )
        self.fx = FxConverter(config)
        self.telegram_notifier = TelegramNotifier(config)
        self.data_handler = DataHandler(config, t212_client=self.t212_client)
        self.strategy_engine = StrategyEngine(config)
        self.risk_manager = RiskManager(config, self.strategy_engine)
        self.order_executor = OrderExecutor(
            config,
            t212_client=self.t212_client,
            telegram_notifier=self.telegram_notifier,
            data_handler=self.data_handler,
            fx=self.fx,
        )
        self.screener = StockScreener(config, self.data_handler, self.strategy_engine)
        self.ai_manager = AIPortfolioManager(config)
        self.order_executor.on_trade_closed = self.ai_manager.record_loss_postmortem_async
        self.ai_manager.backfill_postmortems_from_trades(self.order_executor.closed_trades)

        from bot.disk_monitor import DiskMonitor
        self.disk_monitor = DiskMonitor(
            target_path="/",
            alert_threshold_pct=self.config.disk_alert_threshold_pct,
            critical_threshold_pct=self.config.disk_critical_threshold_pct,
        )
        self._disk_check_counter: int = 0

        logs_dir = Path(config.state_file).parent
        self.scan_log_file = logs_dir / "scan_log.jsonl"
        self.ai_entry_log_file = logs_dir / "ai_entry_decisions.jsonl"

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
        self._price_warned_at: Dict[str, float] = {}

    @property
    def _ccy(self) -> str:
        return {"GBP": "£", "USD": "$", "EUR": "€"}.get(self.config.account_currency, "")

    def _update_runtime_status(self, state: str, detail: str) -> None:
        """Persist real-time bot operational state to `logs/bot_runtime.json` for the Web GUI."""
        try:
            atomic_write_json(
                "logs/bot_runtime.json",
                {
                    "state": state,
                    "detail": detail,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "last_candle_ts": self._last_scan_bar_ts or "",
                    "market_regime": self._market_regime,
                    "market_regime_summary": self._market_regime_summary,
                    "effective_min_score": self._effective_min_score,
                    "poll_interval_sec": self.config.poll_interval_sec,
                    "account_currency": self.config.account_currency,
                },
            )
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

        # Check disk storage on startup
        await asyncio.to_thread(self._check_disk_space_and_alert)

        cb_alerted = self.risk_manager.circuit_breaker_tripped  # don't re-alert after a restart
        while not self._stop_event.is_set():
            try:
                await self.run_cycle()
            except Exception as exc:
                logger.exception("Unhandled error in trading cycle: %s", exc)

            # Check disk storage periodically every ~10 minutes
            self._disk_check_counter += 1
            if self._disk_check_counter >= self.config.disk_check_interval_cycles:
                self._disk_check_counter = 0
                await asyncio.to_thread(self._check_disk_space_and_alert)

            # A tripped breaker does not exit the process (systemd would restart it and
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

    def _check_disk_space_and_alert(self) -> None:
        """Evaluate filesystem usage and dispatch Telegram + Email warnings if >= threshold."""
        try:
            telemetry = self.disk_monitor.get_disk_telemetry()
            should_alert, level = self.disk_monitor.should_alert(telemetry)
            if should_alert:
                logger.warning(
                    "Disk usage reached %s threshold: %.1f%% (%s GB / %s GB used)",
                    level,
                    telemetry["used_pct"],
                    telemetry["used_gb"],
                    telemetry["total_gb"],
                )
                if self.telegram_notifier and self.telegram_notifier.enabled:
                    msg = self.disk_monitor.format_telegram_alert(telemetry)
                    self.telegram_notifier.send_message(msg)

                if self.config.enable_email_alerts and self.config.smtp_host:
                    self.disk_monitor.send_email_alert(
                        telemetry=telemetry,
                        smtp_host=self.config.smtp_host,
                        smtp_port=self.config.smtp_port,
                        smtp_user=self.config.smtp_user,
                        smtp_password=self.config.smtp_password,
                        recipient=self.config.alert_email_recipient,
                    )
                self.disk_monitor.record_alert_dispatched(level)
        except Exception as exc:
            logger.debug("Disk monitor check error: %s", exc)

    def _lookup_atr_for_symbol(self, symbol: str) -> Optional[float]:
        """Return cached or freshly computed 14-period ATR for a recovered Trading 212 position."""
        if symbol in self._latest_atr and self._latest_atr[symbol] > 0:
            return self._latest_atr[symbol]
        df = self.data_handler.fetch_closed_ohlcv(symbol)
        atr_val = float(df["atr"].iloc[-1])
        self._latest_atr[symbol] = atr_val
        return atr_val

    def _managed_symbols(self) -> set:
        """Trading 212 tickers the bot trades (its scan universe)."""
        return {
            self.data_handler.resolve_ticker_pair(s)[0]
            for s in self.screener.get_scan_universe()
        }

    # -------------------------------------------------------------------------
    # Exchange session helpers (rules live in bot.market_calendar)
    # -------------------------------------------------------------------------
    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _is_us_market_open(self) -> bool:
        """Regular US session: Mon-Fri 09:30-16:00 ET (13:00 on early closes), excluding holidays."""
        return is_session_open("SPY_US_EQ", self._now())

    def _is_uk_market_open(self) -> bool:
        """Regular LSE session (08:00-16:30 UK, Mon-Fri) when the UK sleeve is enabled."""
        if not self.config.enable_uk_etp_sleeve:
            return False
        return is_session_open("QQQ3_UK_EQ", self._now())

    def _is_market_open_for_symbol(self, symbol: str) -> bool:
        if str(symbol).endswith("_UK_EQ"):
            return self._is_uk_market_open()
        return self._is_us_market_open()

    def _is_in_pre_close_window(self, symbol: str) -> bool:
        """True during the last `eod_flat_minutes_before_close` minutes of `symbol`'s session."""
        if not self._is_market_open_for_symbol(symbol):
            return False
        return in_pre_close_window(symbol, self._now(), self.config.eod_flat_minutes_before_close)

    def _is_in_opening_bell_window(self) -> bool:
        """First `skip_opening_minutes` of the US session."""
        return in_opening_window("SPY_US_EQ", self._now(), self.config.skip_opening_minutes)

    def _is_in_uk_opening_bell_window(self) -> bool:
        """First `skip_opening_minutes` of the LSE session."""
        return in_opening_window("QQQ3_UK_EQ", self._now(), self.config.skip_opening_minutes)

    def _is_in_opening_bell_for_symbol(self, symbol: str) -> bool:
        if str(symbol).endswith("_UK_EQ"):
            return self._is_in_uk_opening_bell_window()
        return self._is_in_opening_bell_window()

    # -------------------------------------------------------------------------
    # Slot & threshold helpers
    # -------------------------------------------------------------------------
    def _count_us_positions(self) -> int:
        return sum(1 for sym in self.order_executor.positions if not str(sym).endswith("_UK_EQ"))

    def _count_uk_positions(self) -> int:
        return sum(1 for sym in self.order_executor.positions if str(sym).endswith("_UK_EQ"))

    def _has_open_slot_for_symbol(self, symbol: str) -> bool:
        """True if both total capacity and the symbol's regional sleeve (US / UK) have a free slot."""
        return has_open_slot(self.config, symbol, list(self.order_executor.positions))

    def _required_min_score_for_symbol(
        self, symbol: str, regime_state: str, effective_min_score: float
    ) -> float:
        return required_min_score(self.config, symbol, regime_state, effective_min_score)

    def _evaluate_market_regime(self) -> tuple[str, str, float]:
        """Classify the US market regime from the benchmark (QQQ) and return the entry threshold."""
        base_min = self.config.min_recommendation_score
        if not self.config.market_regime_filter:
            return "BULLISH", "Regime filter disabled", base_min

        bench = self.config.market_benchmark_symbol or "QQQ"
        try:
            df = self.data_handler.fetch_closed_ohlcv(bench)
            return classify_market_regime(df.iloc[-1], base_min, bench)
        except Exception as exc:
            logger.warning("Could not evaluate %s market regime (%s); using default threshold.", bench, exc)
            return "BULLISH", f"{bench} regime unavailable", base_min

    def _mark_price(self, sym: str, pos: Any, ob: OrderBookSnapshot) -> float:
        """Price used to manage an open position.

        Prefers Trading 212's own price (where the order would actually execute) and
        falls back to Yahoo when the two disagree by more than
        MAX_BROKER_PRICE_DIVERGENCE_PCT, which usually means one feed is stale or
        in the wrong units.
        """
        yahoo_mark = ob.bid if pos.side == Side.LONG else ob.ask
        broker = self.order_executor.broker_prices.get(sym, 0.0)
        if broker <= 0 or yahoo_mark <= 0:
            return yahoo_mark
        divergence_pct = abs(broker / yahoo_mark - 1.0) * 100.0
        if divergence_pct > self.config.max_broker_price_divergence_pct:
            now = time.monotonic()
            if now - self._price_warned_at.get(sym, 0.0) > 900:
                self._price_warned_at[sym] = now
                logger.warning(
                    "[%s] Trading 212 price %.4f differs from Yahoo %.4f by %.1f%%; using Yahoo.",
                    sym, broker, yahoo_mark, divergence_pct,
                )
            return yahoo_mark
        return broker

    # -------------------------------------------------------------------------
    # Trading cycle
    # -------------------------------------------------------------------------
    async def run_cycle(self) -> None:
        """Run one evaluation cycle (see the class docstring for the steps)."""
        order_books, latest_prices = await self._sync_and_fetch_quotes()

        if not await self._check_equity_and_circuit_breaker(order_books, latest_prices):
            return

        if self.config.eod_flat_enabled:
            await self._apply_end_of_day_flat(order_books)
        await self._manage_positions_intrabar(order_books)

        recommendations = await self._scan_on_new_candle()
        if recommendations is None:
            return

        await self._manage_positions_on_candle_close(recommendations, order_books)

        us_open = self._is_us_market_open()
        uk_open = self._is_uk_market_open()
        if not us_open:
            await self._maybe_send_daily_summary()

        if not self._entries_allowed_now(us_open, uk_open):
            return

        regime_state, regime_summary, min_score = await asyncio.to_thread(self._evaluate_market_regime)
        self._market_regime = regime_state
        self._market_regime_summary = regime_summary
        self._effective_min_score = min_score
        logger.info("Market Regime Check: %s", regime_summary)

        picks = self._select_entry_candidates(recommendations, regime_state, min_score)
        if not picks:
            top_rec = recommendations[0] if recommendations else None
            top_desc = f"{top_rec.symbol} ({top_rec.score:.1f}/100, {top_rec.rating})" if top_rec else "N/A"
            held_syms = ", ".join(self.order_executor.positions.keys()) or "None"
            status_msg = (
                f"Scanned {len(recommendations)} stocks ({regime_summary}) • "
                f"Open Slots: {len(self.order_executor.positions)}/{self.config.max_open_positions} ({held_syms}) • "
                f"Top candidate {top_desc} below entry criteria (min score {min_score:.0f}); standing pat."
            )
            self.ai_manager.record_scan_status(status_msg)
            self._update_runtime_status("MONITORING", status_msg)
            logger.info(
                "No stocks met the regime-adjusted BUY threshold (score >= %.1f, RVOL >= %.2fx, not overextended) on this bar.",
                min_score,
                self.config.min_rvol_for_entry,
            )
            return

        pre_approved = await self._maybe_rotate_slot(picks[0], recommendations, order_books, latest_prices)

        if not any(self._has_open_slot_for_symbol(p.symbol) for p in picks):
            held_syms = ", ".join(self.order_executor.positions.keys())
            status_msg = (
                f"Portfolio sleeve slots full ({len(self.order_executor.positions)}/{self.config.max_open_positions}: "
                f"US {self._count_us_positions()}/{self.config.max_us_positions}, "
                f"UK {self._count_uk_positions()}/{self.config.max_uk_positions} — {held_syms}) • "
                f"Market: {regime_state} • No slot rotation on this candle."
            )
            self.ai_manager.record_scan_status(status_msg)
            self._update_runtime_status("MONITORING", status_msg)
            return

        self.ai_manager.record_scan_status(
            f"Scanned {len(recommendations)} stocks ({regime_summary}) • "
            f"Evaluating {len(picks)} actionable BUY candidate(s) for open portfolio slot(s)."
        )
        await self._enter_candidates(picks, pre_approved, order_books, latest_prices, regime_state, regime_summary)

        open_cnt = len(self.order_executor.positions)
        held_str = ", ".join(self.order_executor.positions.keys()) if open_cnt > 0 else "100% Cash"
        self._update_runtime_status(
            "MONITORING",
            f"Intra-bar SL/TP & trailing stop guard active ({open_cnt}/{self.config.max_open_positions} slots: {held_str}) • "
            f"Waiting for next {self.config.timeframe} candle close.",
        )

    async def _sync_and_fetch_quotes(self) -> Tuple[Dict[str, OrderBookSnapshot], Dict[str, float]]:
        """Step 1: reconcile positions with Trading 212 and quote every held symbol."""
        had_positions_before_sync = len(self.order_executor.positions) > 0
        await asyncio.to_thread(
            self.order_executor.sync_positions_with_t212,
            self._lookup_atr_for_symbol,
            self._managed_symbols(),
        )
        if (
            had_positions_before_sync
            and len(self.order_executor.positions) == 0
            and self.config.execution_mode in {"demo", "live"}
        ):
            logger.info(
                "All open positions were closed outside the bot; resetting the candle scan "
                "lock and 24h equity watermark to re-scan immediately."
            )
            self._last_scan_bar_ts = None
            if not self.risk_manager.circuit_breaker_tripped:
                # Fresh equity baseline (e.g. demo account reset). A tripped breaker is NOT cleared here.
                self.risk_manager._equity_history.clear()

        order_books: Dict[str, OrderBookSnapshot] = {}
        latest_prices: Dict[str, float] = {}
        for sym in list(self.order_executor.positions.keys()):
            try:
                ob = await asyncio.to_thread(self.data_handler.fetch_order_book_snapshot, sym)
                order_books[sym] = ob
                latest_prices[sym] = ob.mid_price
            except Exception as exc:
                logger.error("[%s] Failed to fetch quote for open position: %s", sym, exc)

        if latest_prices:
            atomic_write_json("logs/live_quotes.json", latest_prices)
        return order_books, latest_prices

    async def _check_equity_and_circuit_breaker(
        self, order_books: Dict[str, OrderBookSnapshot], latest_prices: Dict[str, float]
    ) -> bool:
        """Step 2: record equity; if the breaker is tripped, flatten and return False."""
        total_equity, available_cash = await asyncio.to_thread(
            self.order_executor.get_account_equity_and_cash, latest_prices
        )
        dd_pct = self.risk_manager.record_equity(total_equity)
        logger.info(
            "Trading 212 Portfolio | Total Equity=%s%.2f | Free Cash=%s%.2f | Open Positions=%d/%d | 24h DD=%.2f%%",
            self._ccy,
            total_equity,
            self._ccy,
            available_cash,
            len(self.order_executor.positions),
            self.config.max_open_positions,
            dd_pct * 100.0,
        )

        if not self.risk_manager.circuit_breaker_tripped:
            return True

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
        return False

    async def _apply_end_of_day_flat(self, order_books: Dict[str, OrderBookSnapshot]) -> None:
        """Step 3a: close positions shortly before their exchange shuts.

        UK 3x ETPs are never held overnight; US stocks are kept only if >= EOD_HOLD_MIN_R.
        """
        for sym, pos in list(self.order_executor.positions.items()):
            ob = order_books.get(sym)
            if ob is None or not self._is_in_pre_close_window(sym):
                continue
            r_now = pos.current_r_multiple(self._mark_price(sym, pos, ob))
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

    async def _manage_positions_intrabar(self, order_books: Dict[str, OrderBookSnapshot]) -> None:
        """Step 3b: every poll, ratchet trailing stops and check stop / target hits."""
        for sym, pos in list(self.order_executor.positions.items()):
            ob = order_books.get(sym)
            if ob is None:
                continue
            if self.config.require_market_open_for_entries and not self._is_market_open_for_symbol(sym):
                continue

            mark_price = self._mark_price(sym, pos, ob)
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
                # Only notify Telegram when the stop first reaches breakeven, not on every tick.
                crossed_breakeven = prev_sl < pos.entry_price <= pos.stop_loss
                if crossed_breakeven and self.telegram_notifier.enabled:
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
                await asyncio.to_thread(self.order_executor.execute_exit, pos, ob, exit_reason)

    async def _scan_on_new_candle(self) -> Optional[List[Any]]:
        """Step 4: if a new candle has closed, scan the universe and log every candidate.

        Returns the recommendations, or None when there is no new candle.
        """
        universe = self.screener.get_scan_universe()
        probe_symbol = universe[0]
        if self._is_uk_market_open() and not self._is_us_market_open():
            uk_candidates = [s for s in universe if str(s).endswith("_UK_EQ")]
            if uk_candidates:
                probe_symbol = uk_candidates[0]
        try:
            probe_df = await asyncio.to_thread(self.data_handler.fetch_closed_ohlcv, probe_symbol)
        except Exception as exc:
            logger.error("[%s] Failed to fetch probe OHLCV data: %s", probe_symbol, exc)
            return None

        latest_candle_ts = str(probe_df["timestamp"].iloc[-1])
        if self._last_scan_bar_ts == latest_candle_ts:
            open_cnt = len(self.order_executor.positions)
            held_str = ", ".join(self.order_executor.positions.keys()) if open_cnt > 0 else "100% Cash"
            self._update_runtime_status(
                "MONITORING",
                f"Intra-bar SL/TP & trailing stop guard active ({open_cnt}/{self.config.max_open_positions} slots: {held_str}) • "
                f"Waiting for next {self.config.timeframe} candle close.",
            )
            return None

        self._last_scan_bar_ts = latest_candle_ts
        probe_t212, _ = self.data_handler.resolve_ticker_pair(probe_symbol)
        ohlcv_cache = {probe_t212: probe_df}

        self._update_runtime_status(
            "SCANNING_UNIVERSE",
            f"Scanning {len(universe)} symbols on closed {self.config.timeframe} candle ({latest_candle_ts})...",
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

        self._log_scan_candidates(recommendations, latest_candle_ts)
        logger.info("%s", self.screener.format_leaderboard(recommendations, top_n=self.config.screener_top_n))
        return recommendations

    def _log_scan_candidates(self, recommendations: List[Any], candle_ts: str) -> None:
        """Append every scored symbol to logs/scan_log.jsonl.

        Used by `python analyze.py scans` to test whether higher scores really lead
        to better forward returns, including for symbols the bot did not trade.
        """
        scanned_at = datetime.now(timezone.utc).isoformat()
        try:
            self.scan_log_file.parent.mkdir(parents=True, exist_ok=True)
            with self.scan_log_file.open("a", encoding="utf-8") as fh:
                for r in recommendations:
                    fh.write(json.dumps({
                        "candle_ts": candle_ts,
                        "scanned_at": scanned_at,
                        "symbol": r.symbol,
                        "score": r.score,
                        "rating": r.rating,
                        "actionable": r.actionable,
                        "close": round(r.close_price, 4),
                        "atr": round(r.atr, 4),
                        "rsi": round(r.rsi, 2),
                        "rvol": r.rvol,
                        "roc_10_pct": r.roc_10_pct,
                        "blocker": r.blocker,
                        "regime": self._market_regime,
                        "held": r.symbol in self.order_executor.positions,
                    }) + "\n")
        except Exception as exc:
            logger.warning("Could not write scan log: %s", exc)

    async def _manage_positions_on_candle_close(
        self, recommendations: List[Any], order_books: Dict[str, OrderBookSnapshot]
    ) -> None:
        """Step 5: candle-close stop checks and bearish-crossover exits for held symbols."""
        for rec in recommendations:
            open_pos = self.order_executor.positions.get(rec.symbol)
            if open_pos is None:
                continue
            self._backfill_journey(open_pos, rec)
            if self.config.require_market_open_for_entries and not self._is_market_open_for_symbol(rec.symbol):
                continue
            if rec.signal.is_exit:
                ob = order_books.get(rec.symbol) or await asyncio.to_thread(
                    self.data_handler.fetch_order_book_snapshot, rec.symbol
                )
                await asyncio.to_thread(self.order_executor.execute_exit, open_pos, ob, rec.signal.reason)
                continue

            prev_tp = open_pos.take_profit
            action, reason = self.strategy_engine.evaluate_position_exit_and_trail(
                position=open_pos,
                current_price=rec.close_price,
                current_atr=rec.atr,
                is_candle_close=True,
                trend_strong=rec.trend_strong,
            )
            if open_pos.take_profit != prev_tp:
                self.order_executor.save_state()
            if action != SignalAction.HOLD:
                logger.info("[%s] Candle-close protective exit triggered: %s", rec.symbol, reason)
                ob = order_books.get(rec.symbol) or await asyncio.to_thread(
                    self.data_handler.fetch_order_book_snapshot, rec.symbol
                )
                await asyncio.to_thread(self.order_executor.execute_exit, open_pos, ob, reason)

    def _backfill_journey(self, open_pos: Any, rec: Any) -> None:
        """Fill a position's price journey from closed candles if it has few points."""
        if len(open_pos.price_history) > 2 or not rec.candles:
            return
        try:
            opened_dt = datetime.fromisoformat(str(open_pos.opened_at).replace("Z", "+00:00"))
            if opened_dt.tzinfo is None:
                opened_dt = opened_dt.replace(tzinfo=timezone.utc)
            backfilled = [{"ts": open_pos.opened_at, "price": round(float(open_pos.entry_price), 4)}]
            for c in rec.candles:
                c_iso = str(c.get("ts_iso") or "")
                if not c_iso:
                    continue
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

    async def _maybe_send_daily_summary(self) -> None:
        """Send the Telegram daily summary once, after the US close on trading days."""
        if not self.telegram_notifier.enabled:
            return
        try:
            from zoneinfo import ZoneInfo

            now_et = datetime.now(ZoneInfo("America/New_York"))
            today_str = now_et.strftime("%Y-%m-%d")
            current_min = now_et.hour * 60 + now_et.minute
            if (
                is_trading_day(now_et.date())
                and current_min >= market_close_minute(now_et.date())
                and self._last_daily_summary_date != today_str
            ):
                self._last_daily_summary_date = today_str
                await self._dispatch_daily_summary()
        except Exception as exc:
            logger.warning("Error checking daily summary trigger: %s", exc)

    def _entries_allowed_now(self, us_open: bool, uk_open: bool) -> bool:
        """Block entries while both markets are shut or the only open market is in its opening bell."""
        if self.config.require_market_open_for_entries and not (us_open or uk_open):
            msg = (
                "US & UK markets closed — scan complete, new entries paused until the next "
                "regular session (08:00 London / 09:30 ET). Open positions remain protected."
            )
            logger.info("%s", msg)
            self.ai_manager.record_scan_status(msg)
            self._update_runtime_status("MARKET_CLOSED", msg)
            return False

        us_bell = us_open and self._is_in_opening_bell_window()
        uk_bell = uk_open and self._is_in_uk_opening_bell_window()
        if (us_open and not uk_open and us_bell) or (uk_open and not us_open and uk_bell) or (us_bell and uk_bell):
            bell_label = "UK LSE (08:00 UK)" if (uk_bell and not us_bell) else "US (09:30 ET)"
            msg = (
                f"{bell_label} opening-bell guard active (first {self.config.skip_opening_minutes}m) — "
                "deferring new entries until opening volatility settles."
            )
            logger.info("%s", msg)
            self.ai_manager.record_scan_status(msg)
            self._update_runtime_status("OPENING_BELL_GUARD", msg)
            self._last_scan_bar_ts = None
            return False
        return True

    def _select_entry_candidates(
        self, recommendations: List[Any], regime_state: str, min_score: float
    ) -> List[Any]:
        """Actionable recommendations that pass session, cooldown and regime-score filters."""
        picks = []
        for r in recommendations:
            if not r.actionable or r.symbol in self.order_executor.positions:
                continue
            if self.config.require_market_open_for_entries and not self._is_market_open_for_symbol(r.symbol):
                continue
            if self._is_in_opening_bell_for_symbol(r.symbol):
                logger.info("[%s] Deferring pick during the opening-bell guard window.", r.symbol)
                continue
            if self.config.eod_flat_enabled and self._is_in_pre_close_window(r.symbol):
                logger.info("[%s] Skipping pick during the pre-close window.", r.symbol)
                continue
            if self.order_executor.is_in_cooldown(r.symbol):
                logger.info("[%s] Skipping pick: post-loss cooldown.", r.symbol)
                continue
            req_score = self._required_min_score_for_symbol(r.symbol, regime_state, min_score)
            if r.score < req_score:
                logger.info(
                    "[%s] Skipping pick (score %.1f < regime-adjusted threshold %.1f for %s market).",
                    r.symbol, r.score, req_score, regime_state,
                )
                continue
            picks.append(r)
        return picks

    async def _maybe_rotate_slot(
        self,
        top_pick: Any,
        recommendations: List[Any],
        order_books: Dict[str, OrderBookSnapshot],
        latest_prices: Dict[str, float],
    ) -> Dict[str, Any]:
        """If the top pick's sleeve is full, ask the AI manager whether to swap out a laggard.

        Returns `{symbol: decision}` for picks pre-approved by a completed rotation.
        """
        pre_approved: Dict[str, Any] = {}
        if self._has_open_slot_for_symbol(top_pick.symbol):
            return pre_approved
        is_uk_pick = str(top_pick.symbol).endswith("_UK_EQ")
        eligible_held = {
            sym: pos
            for sym, pos in self.order_executor.positions.items()
            if (str(sym).endswith("_UK_EQ") == is_uk_pick) and self._is_market_open_for_symbol(sym)
        }
        if not (self.config.enable_ai_manager and top_pick.score >= 80.0 and eligible_held):
            return pre_approved
        rot_dec = await asyncio.to_thread(
            self.ai_manager.evaluate_slot_rotation,
            top_pick,
            eligible_held,
            recommendations,
            latest_prices,
        )
        if rot_dec is None or rot_dec.decision != "ROTATE" or rot_dec.replace_symbol not in eligible_held:
            return pre_approved
        stale_sym = rot_dec.replace_symbol
        logger.info(
            "[AI Portfolio Manager] SLOT ROTATION APPROVED (%s, conf=%d%%): Closing %s -> Buying %s | %s",
            rot_dec.engine, rot_dec.confidence, stale_sym, top_pick.symbol, rot_dec.reasoning,
        )
        stale_ob = order_books.get(stale_sym) or await asyncio.to_thread(
            self.data_handler.fetch_order_book_snapshot, stale_sym
        )
        exit_res = await asyncio.to_thread(
            self.order_executor.execute_exit,
            self.order_executor.positions[stale_sym],
            stale_ob,
            f"AI Slot Rotation -> {top_pick.symbol}: {rot_dec.reasoning}",
        )
        if exit_res is not None and exit_res.success:
            pre_approved[top_pick.symbol] = rot_dec
        return pre_approved

    def _log_ai_entry_decision(self, pick: Any, plan: TradePlan, ai_dec: Any) -> None:
        """Record every AI entry decision (approve or veto) with the trade it would have been.

        `python analyze.py ai` replays these to compare what approved and vetoed
        setups went on to do.
        """
        try:
            append_jsonl(self.ai_entry_log_file, {
                "decided_at": datetime.now(timezone.utc).isoformat(),
                "candle_ts": self._last_scan_bar_ts,
                "symbol": pick.symbol,
                "decision": ai_dec.decision,
                "confidence": ai_dec.confidence,
                "size_multiplier": ai_dec.size_multiplier,
                "engine": ai_dec.engine,
                "reasoning": ai_dec.reasoning,
                "score": pick.score,
                "reference_price": plan.reference_price,
                "stop_loss": plan.stop_loss,
                "take_profit": plan.take_profit,
                "atr": plan.atr,
                "regime": self._market_regime,
            })
        except Exception as exc:
            logger.warning("Could not write AI decision log: %s", exc)

    async def _enter_candidates(
        self,
        picks: List[Any],
        pre_approved: Dict[str, Any],
        order_books: Dict[str, OrderBookSnapshot],
        latest_prices: Dict[str, float],
        regime_state: str,
        regime_summary: str,
    ) -> None:
        """Step 6: size, vet and open positions for picks that have a free slot."""
        for pick in picks:
            if not self._has_open_slot_for_symbol(pick.symbol):
                continue

            logger.info(
                "Top Actionable Recommendation Selected: %s | Rating=%s | Score=%.1f/100 | Thesis: %s",
                pick.symbol, pick.rating, pick.score, pick.thesis,
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

            fx_rate = await asyncio.to_thread(self.fx.try_rate_for_symbol, pick.symbol)
            if not fx_rate:
                logger.error("[%s] Skipping entry: no exchange rate available to size the trade.", pick.symbol)
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
                fx_rate=fx_rate,
            )
            if plan is None:
                continue
            plan = replace(plan, score=pick.score, rating=pick.rating, rvol=pick.rvol, thesis=pick.thesis)

            ai_dec = None
            size_mult = 1.0
            if self.config.enable_ai_manager:
                if pick.symbol in pre_approved:
                    ai_dec = pre_approved[pick.symbol]
                    logger.info(
                        "[AI Portfolio Manager] %s -> PRE-APPROVED via slot rotation (Confidence=%d%%, SizeMult=%.2fx, Engine=%s)",
                        pick.symbol, ai_dec.confidence, ai_dec.size_multiplier, ai_dec.engine,
                    )
                else:
                    self._update_runtime_status(
                        "CONSULTING_AI",
                        f"Consulting AI on {pick.symbol} (Score {pick.score:.1f}/100, {pick.rating})...",
                    )
                    ai_dec = await asyncio.to_thread(
                        self.ai_manager.evaluate_entry_candidate,
                        pick,
                        self.order_executor.positions,
                        total_equity,
                        regime_summary,
                    )
                    self._log_ai_entry_decision(pick, plan, ai_dec)
                    logger.info(
                        "[AI Portfolio Manager] %s -> %s (Confidence=%d%%, SizeMult=%.2fx, Engine=%s) | %s",
                        pick.symbol, ai_dec.decision, ai_dec.confidence, ai_dec.size_multiplier,
                        ai_dec.engine, ai_dec.reasoning,
                    )
                    if ai_dec.decision == "VETO":
                        continue
                size_mult = ai_dec.size_multiplier

            if size_mult < 1.0:
                plan = replace(
                    plan,
                    quantity=round(plan.quantity * size_mult, self.config.fractional_decimals),
                    risk_amount=plan.risk_amount * size_mult,
                    notional=plan.notional * size_mult,
                    risk_pct_of_equity=plan.risk_pct_of_equity * size_mult,
                )
            self._update_runtime_status(
                "EXECUTING_ORDER",
                f"Submitting {plan.symbol} BUY order ({plan.quantity:.4f} shares) to Trading 212...",
            )
            opened_pos = await asyncio.to_thread(self.order_executor.execute_entry, plan, ob)
            if opened_pos is not None:
                opened_pos.entry_context = {
                    "score": round(float(pick.score), 1),
                    "rating": str(pick.rating),
                    "rsi": round(float(pick.rsi), 2),
                    "atr": round(float(pick.atr), 4),
                    "rvol": round(float(pick.rvol), 2),
                    "roc_10_pct": round(float(pick.roc_10_pct), 2),
                    "thesis": str(pick.thesis),
                    "market_regime": regime_state,
                    "spread_verified": plan.spread_verified,
                    "ai_confidence": int(ai_dec.confidence) if ai_dec is not None else None,
                    "ai_engine": str(ai_dec.engine) if ai_dec is not None else None,
                    "ai_reasoning": str(ai_dec.reasoning) if ai_dec is not None else "",
                }
                self.order_executor.save_state()

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
        fx_rate = await asyncio.to_thread(self.fx.rate_for_symbol, t212_ticker)
        plan = self.risk_manager.validate_and_build_trade_plan(
            signal=synthetic_signal,
            order_book=ob,
            total_equity=total_equity,
            available_quote=available_cash,
            open_positions_count=len(self.order_executor.positions),
            fx_rate=fx_rate,
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
        """Process remote commands sent from the configured Telegram chat (read-only)."""
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
                "• <b>/disk</b> - 💾 Proxmox node storage &amp; log directory usage\n"
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
                    f"💰 <b>Total Equity:</b> {self._ccy}{tot_eq:,.2f}\n"
                    f"💵 <b>Free Cash:</b> {self._ccy}{free_cash:,.2f}\n"
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

                fx_now = self.fx.try_rate_for_symbol(sym) or pos.fx_rate_at_entry or 1.0
                pnl = pos.unrealized_pnl_account(cur_price, fx_now)
                pnl_pct = (cur_price - pos.entry_price) / pos.entry_price * 100.0 if pos.entry_price > 0 else 0.0
                sign = "+" if pnl >= 0 else "-"
                init_sl = pos.initial_stop_loss or pos.stop_loss
                r_mult = (cur_price - pos.entry_price) / max(pos.entry_price - init_sl, 0.001)

                lines.append(
                    f"• <b>{clean_sym}</b> ({pos.side.value}): {pos.quantity:.4f} shares\n"
                    f"  Entry: {ccy}{pos.entry_price:.2f} ➔ Current: {ccy}{cur_price:.2f}\n"
                    f"  PnL: <b>{sign}{self._ccy}{abs(pnl):.2f}</b> ({pnl_pct:+.2f}%, {r_mult:+.2f}R)\n"
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
                total_scanned = len(all_recs) or len(self.screener.get_scan_universe())

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
                    fx_now = self.fx.try_rate_for_symbol(target_sym) or pos.fx_rate_at_entry or 1.0
                    pnl = pos.unrealized_pnl_account(curr_c, fx_now)
                    pnl_sign = "+" if pnl >= 0 else "-"
                    caption += f"\nPosition: {pos.quantity:.4f} shares | PnL: <b>{pnl_sign}{self._ccy}{abs(pnl):.2f}</b>"

                if photo:
                    await asyncio.to_thread(self.telegram_notifier.send_photo, photo, caption)
                else:
                    await asyncio.to_thread(self.telegram_notifier.send_message, f"❌ Could not render chart for {clean_sym}.")
            except Exception as exc:
                await asyncio.to_thread(self.telegram_notifier.send_message, f"❌ Chart error for {target_sym}: {exc}")

        elif cmd in {"/disk", "/storage"}:
            try:
                telemetry = self.disk_monitor.get_disk_telemetry()
                msg = self.disk_monitor.format_status_message(telemetry)
                await asyncio.to_thread(self.telegram_notifier.send_message, msg)
            except Exception as exc:
                await asyncio.to_thread(self.telegram_notifier.send_message, f"❌ Disk lookup error: {exc}")

        else:
            await asyncio.to_thread(
                self.telegram_notifier.send_message,
                f"❓ <b>Unrecognized command:</b> <code>{cmd}</code>\n\n"
                "Available commands:\n"
                "• <b>/recommendations</b> (or <b>/screener</b>) — Top ranked picks\n"
                "• <b>/positions</b> — Active open positions &amp; live PnL\n"
                "• <b>/status</b> — Portfolio equity &amp; market regime\n"
                "• <b>/disk</b> — Storage &amp; disk usage telemetry\n"
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

                fx_now = self.fx.try_rate_for_symbol(sym) or pos.fx_rate_at_entry or 1.0
                pnl = pos.unrealized_pnl_account(cur_price, fx_now)
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
