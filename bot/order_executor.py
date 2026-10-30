"""Order execution and portfolio management module for Trading 212.

Supports three execution modes:
- 'demo'  : Trading 212 Practice API (`https://demo.trading212.com/api/v0`)
- 'live'  : Trading 212 Real Money API (`https://live.trading212.com/api/v0`)
- 'paper' : Local simulation against live quotes (no Trading 212 API key needed)

Trading 212 conventions:
- BUY orders send a positive `quantity`, SELL orders a negative one.
- Placing an order is never retried automatically (a retry could duplicate it).

How an order is confirmed (demo/live):
1. Read the broker's position quantity for the ticker before sending.
2. Send the order and poll its status.
3. Read the position again. Only the change in quantity counts as filled.
4. Take the fill price and fees from GET /equity/history/orders when available,
   otherwise fall back to the position's average price (entries) or the quote
   used for the order (exits), and record which source was used.

All money amounts (equity, cash, fees, P&L) are in the account currency.
Prices, stops and targets stay in the instrument's own currency.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from bot.config import Config
from bot.fx import FxConverter
from bot.models import OrderBookSnapshot, OrderResult, Position, Side, TradePlan
from bot.t212_client import Trading212APIError, Trading212Client
from bot.utils import append_jsonl, atomic_write_json, read_jsonl

logger = logging.getLogger(__name__)

QTY_EPS = 1e-6
# A broker fill price this far from the quote we traded on is treated as a units
# error (e.g. pence vs pounds) and ignored.
MAX_FILL_PRICE_DEVIATION = 0.10
ACTIVE_ORDER_STATUSES = {
    "LOCAL", "UNCONFIRMED", "CONFIRMED", "NEW", "PENDING", "WORKING",
    "PARTIALLY_FILLED", "CANCELLING", "REPLACING",
}
DEAD_ORDER_STATUSES = {"CANCELLED", "REJECTED", "REPLACED"}


class OrderExecutor:
    """Routes orders to Trading 212 (Demo or Live) or local paper simulator and tracks positions."""

    def __init__(
        self,
        config: Config,
        t212_client: Optional[Trading212Client] = None,
        telegram_notifier: Optional[Any] = None,
        data_handler: Optional[Any] = None,
        fx: Optional[FxConverter] = None,
    ) -> None:
        self.config = config
        self.t212_client = t212_client or (
            Trading212Client(config)
            if config.execution_mode in {"demo", "live"}
            else None
        )
        self.telegram_notifier = telegram_notifier
        self.data_handler = data_handler
        self.fx = fx or FxConverter(config)
        self.positions: Dict[str, Position] = {}
        self.cooldown_until: Dict[str, str] = {}
        self.closed_trades: List[Dict[str, Any]] = []
        self.paper_quote_balance: float = config.paper_initial_equity
        self.realized_pnl: float = 0.0
        self.last_closed_record: Optional[Dict[str, Any]] = None
        self.on_trade_closed: Optional[Callable[[Dict[str, Any]], None]] = None
        # Latest Trading 212 price per held symbol (from the portfolio sync)
        self.broker_prices: Dict[str, float] = {}
        self._ignored_unmanaged: set[str] = set()
        self.journal_file: Path = Path(self.config.state_file).parent / "trade_journal.jsonl"
        self._load_state()
        self._backfill_journal_if_missing()

    # -------------------------------------------------------------------------
    # Permanent Trade Journal (append-only JSONL; never truncated)
    # -------------------------------------------------------------------------
    def _append_journal(self, record: Dict[str, Any]) -> None:
        try:
            append_jsonl(self.journal_file, record)
        except Exception as exc:
            logger.warning("Could not append to trade journal %s: %s", self.journal_file, exc)

    def _backfill_journal_if_missing(self) -> None:
        """Seed the journal from the (capped) closed_trades list the first time it is created."""
        if self.journal_file.exists() or not self.closed_trades:
            return
        for trade in reversed(self.closed_trades):  # oldest first
            rec = {k: v for k, v in trade.items() if k != "price_history"}
            rec["backfilled"] = True
            self._append_journal(rec)
        logger.info("Seeded trade journal %s with %d historical trades.", self.journal_file, len(self.closed_trades))

    def read_journal(self) -> List[Dict[str, Any]]:
        return read_jsonl(self.journal_file)

    @staticmethod
    def classify_trade_outcome(rec: Dict[str, Any]) -> str:
        """Deterministic failure-mode tag for a closed trade (used by the postmortem engine)."""
        net = float(rec.get("net_pnl", 0.0))
        if net > 0:
            return "WIN"
        reason = str(rec.get("reason", ""))
        r_mult = float(rec.get("r_multiple", 0.0))
        mfe_r = rec.get("mfe_r")
        gross = float(rec.get("gross_pnl", 0.0))
        if reason.startswith("AI Slot Rotation"):
            return "ROTATION_EXIT"
        if rec.get("overnight") and r_mult <= -1.5:
            return "OVERNIGHT_GAP"
        if gross > 0 >= net:
            return "FX_FEE_DRAG"
        if mfe_r is not None and float(mfe_r) >= 1.0:
            return "GAVE_BACK_WINNER"
        if mfe_r is not None and float(mfe_r) < 0.25:
            return "NEVER_WORKED"
        return "STOPPED_OUT"

    # -------------------------------------------------------------------------
    # Local State Persistence (stores stop-loss, take-profit, and trailing watermarks)
    # -------------------------------------------------------------------------
    def _load_state(self) -> None:
        path = Path(self.config.state_file)
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error(
                "Could not read state file %s (%s). Starting without saved stops/targets; "
                "open broker positions will be re-adopted with fresh levels.",
                path,
                exc,
            )
            return
        self.paper_quote_balance = float(
            raw.get("paper_quote_balance", self.config.paper_initial_equity)
        )
        self.realized_pnl = float(raw.get("realized_pnl", 0.0))
        self.positions = {
            sym: Position.from_dict(pdata) for sym, pdata in raw.get("positions", {}).items()
        }
        cd_map = raw.get("cooldown_until", {})
        if isinstance(cd_map, dict):
            self.cooldown_until = {str(k): str(v) for k, v in cd_map.items()}
        closed_list = raw.get("closed_trades", [])
        if isinstance(closed_list, list):
            self.closed_trades = [item for item in closed_list if isinstance(item, dict)][:25]
        logger.info("Loaded state from %s: open_positions=%d", path, len(self.positions))

    def save_state(self) -> None:
        payload = {
            "account_currency": self.config.account_currency,
            "paper_quote_balance": round(self.paper_quote_balance, 6),
            "realized_pnl": round(self.realized_pnl, 6),
            "positions": {sym: pos.to_dict() for sym, pos in self.positions.items()},
            "cooldown_until": self.cooldown_until,
            "closed_trades": self.closed_trades[:25],
        }
        atomic_write_json(self.config.state_file, payload)

    def _effective_fee_rate(self, symbol: str) -> float:
        """Per-leg fee rate: 0% for GBP-priced UK ETPs, the FX fee rate for US shares."""
        if str(symbol).endswith("_UK_EQ"):
            return 0.0
        return float(self.config.fx_fee_rate)

    def _fx_for(self, symbol: str, fallback: Optional[float] = None) -> float:
        """Account-currency units per unit of `symbol`'s price currency.

        Falls back to `fallback` (e.g. the rate at entry) and finally to 1.0 with
        a warning, so that recording a closed trade never fails.
        """
        rate = self.fx.try_rate_for_symbol(symbol, fallback=fallback if fallback else None)
        if rate is None or rate <= 0:
            logger.warning("[%s] No FX rate available; recording amounts unconverted.", symbol)
            return 1.0
        return rate

    def _position_fx(self, pos: Position) -> float:
        """Exchange rate at entry, filling it in for positions saved before FX tracking."""
        if pos.fx_rate_at_entry <= 0:
            rate = self.fx.try_rate_for_symbol(pos.symbol)
            if rate:
                pos.fx_rate_at_entry = rate
                return rate
            return 1.0
        return pos.fx_rate_at_entry

    def is_in_cooldown(self, symbol: str, now: Optional[datetime] = None) -> bool:
        """Return True if `symbol` is currently in post-loss cooldown."""
        exp_str = self.cooldown_until.get(symbol)
        if not exp_str:
            return False
        try:
            exp_dt = datetime.fromisoformat(exp_str)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            ref = now or datetime.now(timezone.utc)
            if ref < exp_dt:
                return True
            self.cooldown_until.pop(symbol, None)
            return False
        except Exception:
            self.cooldown_until.pop(symbol, None)
            return False

    # -------------------------------------------------------------------------
    # Account Equity & Cash Synchronization
    # -------------------------------------------------------------------------
    def get_account_equity_and_cash(
        self, latest_prices: Optional[Dict[str, float]] = None
    ) -> Tuple[float, float]:
        """Return `(total_equity, available_free_cash)` in account currency."""
        prices = latest_prices or {}
        if self.config.execution_mode == "paper":
            position_value = 0.0
            for sym, pos in self.positions.items():
                mark = prices.get(sym, pos.entry_price)
                fx_entry = self._position_fx(pos)
                fx_now = self._fx_for(sym, fallback=fx_entry)
                locked = pos.quantity * pos.entry_price * fx_entry
                position_value += locked + pos.unrealized_pnl_account(mark, fx_now)
            total_equity = self.paper_quote_balance + position_value
            return total_equity, self.paper_quote_balance

        if self.t212_client is None:
            raise RuntimeError("Trading212Client is not initialized for demo/live mode.")

        cash_data = self.t212_client.get_account_cash()
        free_cash = float(cash_data.get("free") or 0.0)
        total_equity = float(cash_data.get("total") or free_cash)
        return total_equity, free_cash

    def sync_positions_with_t212(
        self,
        atr_lookup: Optional[Callable[[str], Optional[float]]] = None,
        managed_symbols: Optional[Iterable[str]] = None,
    ) -> None:
        """Two-way reconciliation between local positions and Trading 212's portfolio.

        1. Records the broker's current price for each held symbol.
        2. Removes local positions that no longer exist at the broker. If the bot's
           backup stop order filled, the close is journaled with the broker's fill.
        3. Adopts broker positions missing locally (e.g. after a crash mid-order),
           but only for symbols in `managed_symbols` unless
           `adopt_unmanaged_positions` is enabled. Holdings you bought yourself
           are left alone.
        4. Updates quantities after partial fills.
        """
        if self.config.execution_mode == "paper" or self.t212_client is None:
            return

        try:
            remote_positions = self.t212_client.get_portfolio()
        except Exception as exc:
            logger.warning("Failed to sync portfolio from Trading 212: %s", exc)
            return

        remote_by_ticker = {
            str(item.get("ticker")): item
            for item in remote_positions
            if float(item.get("quantity") or 0.0) > 0
        }
        self.broker_prices = {
            sym: float(item.get("currentPrice") or 0.0)
            for sym, item in remote_by_ticker.items()
            if float(item.get("currentPrice") or 0.0) > 0
        }
        managed = set(managed_symbols) if managed_symbols is not None else None

        state_changed = False

        # 1. Local positions that disappeared at the broker
        pending_orders: Optional[List[Dict[str, Any]]] = None
        for sym in list(self.positions.keys()):
            if sym in remote_by_ticker:
                continue
            if pending_orders is None:
                try:
                    pending_orders = self.t212_client.get_orders()
                except Exception:
                    pending_orders = []
            # A queued (non-stop) order for this ticker means the position may still be
            # opening, e.g. an order waiting for the market to open.
            if any(
                str(o.get("ticker")) == sym and str(o.get("type", "")).upper() != "STOP"
                for o in pending_orders
            ):
                continue
            pos = self.positions[sym]
            if pos.backup_stop_order_id and self._close_from_backup_stop_fill(pos):
                state_changed = True
                continue
            if pos.backup_stop_order_id:
                self._cancel_order_quietly(pos.backup_stop_order_id)
            logger.info(
                "[%s] Position no longer present in Trading 212 portfolio; removing local record.",
                sym,
            )
            self.positions.pop(sym, None)
            state_changed = True

        # 2. Adopt broker positions missing locally (or update quantity)
        for sym, item in remote_by_ticker.items():
            remote_qty = round(
                float(item.get("quantity") or 0.0), self.config.fractional_decimals
            )
            avg_price = float(
                item.get("averagePrice") or item.get("currentPrice") or 0.0
            )
            curr_price = float(item.get("currentPrice") or avg_price)
            if remote_qty <= 0 or avg_price <= 0:
                continue

            if sym not in self.positions:
                if managed is not None and sym not in managed and not self.config.adopt_unmanaged_positions:
                    if sym not in self._ignored_unmanaged:
                        self._ignored_unmanaged.add(sym)
                        logger.info(
                            "[%s] Holding found at Trading 212 that is not in the bot's trading list; "
                            "leaving it alone (set ADOPT_UNMANAGED_POSITIONS=true to manage it).",
                            sym,
                        )
                    continue

                atr_val: Optional[float] = None
                if atr_lookup is not None:
                    try:
                        atr_val = atr_lookup(sym)
                    except Exception as exc:
                        logger.warning("[%s] ATR lookup during catch-up sync failed: %s", sym, exc)

                if atr_val is None or atr_val <= 0:
                    atr_val = max(0.01, avg_price * 0.012)

                stop_loss = avg_price - self.config.stop_loss_atr_mult * atr_val
                take_profit = avg_price + self.config.take_profit_atr_mult * atr_val

                fx_rate = self.fx.try_rate_for_symbol(sym) or 0.0
                adopted_fee = remote_qty * avg_price * (fx_rate or 1.0) * self._effective_fee_rate(sym)
                adopted = Position(
                    symbol=sym,
                    side=Side.LONG,
                    quantity=remote_qty,
                    entry_price=avg_price,
                    initial_stop_loss=stop_loss,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    atr_at_entry=atr_val,
                    highest_price=max(avg_price, curr_price),
                    lowest_price=min(avg_price, curr_price),
                    entry_order_id="t212-recovered",
                    entry_fee_paid=adopted_fee,
                    fx_rate_at_entry=fx_rate,
                    entry_price_source="broker_avg",
                )
                self.positions[sym] = adopted
                state_changed = True
                logger.info(
                    "[%s] CATCH-UP SYNC: Adopted open Trading 212 position | "
                    "qty=%.4f @ %.4f | SL=%.4f | TP=%.4f",
                    sym,
                    remote_qty,
                    avg_price,
                    stop_loss,
                    take_profit,
                )
            else:
                existing = self.positions[sym]
                if existing.fx_rate_at_entry <= 0 and self._position_fx(existing) != 1.0:
                    # Positions saved before FX tracking: record today's rate as the best estimate
                    state_changed = True
                if abs(existing.quantity - remote_qty) > 1e-5:
                    logger.info(
                        "[%s] Synced share quantity with Trading 212 portfolio: %.4f -> %.4f",
                        sym,
                        existing.quantity,
                        remote_qty,
                    )
                    existing.quantity = remote_qty
                    state_changed = True

        if state_changed:
            self.save_state()

    # -------------------------------------------------------------------------
    # High-Level Entry & Exit Execution
    # -------------------------------------------------------------------------
    def execute_entry(
        self, plan: TradePlan, order_book: OrderBookSnapshot
    ) -> Optional[Position]:
        """Place an entry order and register the Position from the confirmed fill."""
        rounded_qty = round(plan.quantity, self.config.fractional_decimals)
        if rounded_qty <= 0:
            logger.warning("[%s] Rounded quantity is zero; aborting entry.", plan.symbol)
            return None

        if self.config.execution_mode != "paper":
            pending = self._has_pending_order(plan.symbol)
            if pending is None or pending:
                logger.warning(
                    "[%s] Entry skipped: %s",
                    plan.symbol,
                    "an order for this ticker is already working at Trading 212"
                    if pending
                    else "could not check Trading 212 for working orders",
                )
                return None

        result = self._place_and_verify_order(
            symbol=plan.symbol,
            side=plan.order_side,
            quantity=rounded_qty,
            reference_price=plan.reference_price,
            order_book=order_book,
            is_exit=False,
            fx_rate=plan.fx_rate,
        )
        if not result.success or result.filled_qty <= 0:
            logger.error(
                "[%s] Entry order failed or unfilled: %s", plan.symbol, result.message
            )
            return None

        sl_dist = self.config.stop_loss_atr_mult * plan.atr
        tp_dist = self.config.take_profit_atr_mult * plan.atr
        if plan.side == Side.LONG:
            stop_loss = result.avg_fill_price - sl_dist
            take_profit = result.avg_fill_price + tp_dist
        else:
            stop_loss = result.avg_fill_price + sl_dist
            take_profit = result.avg_fill_price - tp_dist

        entry_fee = (
            result.fee_paid
            if result.fees_actual or self.config.execution_mode == "paper"
            else result.filled_qty * result.avg_fill_price * plan.fx_rate * self._effective_fee_rate(plan.symbol)
        )

        position = Position(
            symbol=plan.symbol,
            side=plan.side,
            quantity=result.filled_qty,
            entry_price=result.avg_fill_price,
            initial_stop_loss=stop_loss,
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr_at_entry=plan.atr,
            entry_order_id=result.order_id,
            entry_fee_paid=entry_fee,
            fx_rate_at_entry=plan.fx_rate,
            entry_reference_price=plan.reference_price,
            entry_price_source=result.price_source,
        )
        self.positions[plan.symbol] = position
        if self.config.broker_backup_stop_enabled and self.t212_client is not None:
            self._place_backup_stop(position)
        self.save_state()

        if self.telegram_notifier and getattr(self.telegram_notifier, "enabled", False):
            try:
                chart_df = None
                if self.data_handler is not None:
                    try:
                        chart_df = self.data_handler.fetch_closed_ohlcv(plan.symbol)
                    except Exception:
                        pass
                self.telegram_notifier.send_trade_opened_alert(
                    symbol=position.symbol,
                    side=position.side.value,
                    qty=position.quantity,
                    entry_price=position.entry_price,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    risk_amount=plan.risk_amount,
                    risk_pct=plan.risk_pct_of_equity,
                    score=plan.score,
                    rating=plan.rating,
                    rvol=plan.rvol,
                    spread_pct=plan.spread_pct,
                    thesis=plan.thesis,
                    df=chart_df,
                    notional=position.quantity * position.entry_price * plan.fx_rate,
                )
            except Exception as exc:
                logger.warning("[%s] Failed to dispatch Telegram entry alert: %s", position.symbol, exc)

        logger.info(
            "[%s] POSITION OPENED (%s on %s): order_id=%s qty=%.4f @ %.4f (%s) | SL=%.4f | TP=%.4f",
            position.symbol,
            position.side.value,
            self.config.execution_mode.upper(),
            result.order_id,
            position.quantity,
            position.entry_price,
            result.price_source,
            position.stop_loss,
            position.take_profit,
        )
        return position

    def execute_exit(
        self,
        position: Position,
        order_book: OrderBookSnapshot,
        reason: str,
    ) -> Optional[OrderResult]:
        """Close an open position with a market order and record the trade."""
        exit_order_side = "sell" if position.side == Side.LONG else "buy"
        ref_price = order_book.bid if exit_order_side == "sell" else order_book.ask

        backup_cancelled = False
        if self.config.execution_mode != "paper":
            if self._has_pending_order(position.symbol) is True:
                logger.warning(
                    "[%s] Exit skipped (%s): an order for this ticker is already working at Trading 212.",
                    position.symbol,
                    reason,
                )
                return None
            if position.backup_stop_order_id:
                outcome = self._cancel_backup_stop(position)
                if outcome == "filled":
                    return OrderResult(
                        success=True,
                        order_id=self.last_closed_record.get("exit_order_id", "") if self.last_closed_record else "",
                        symbol=position.symbol,
                        side=exit_order_side,
                        order_type="stop",
                        filled_qty=position.quantity,
                        avg_fill_price=float(self.last_closed_record.get("exit_price", ref_price)) if self.last_closed_record else ref_price,
                        fee_paid=0.0,
                        status="filled",
                        message="Closed by broker backup stop before the bot's exit",
                        price_source="broker_fill",
                    )
                backup_cancelled = outcome == "cleared"

        result = self._place_and_verify_order(
            symbol=position.symbol,
            side=exit_order_side,
            quantity=position.quantity,
            reference_price=ref_price,
            order_book=order_book,
            is_exit=True,
            fx_rate=self._fx_for(position.symbol, fallback=self._position_fx(position)),
        )
        if not result.success or result.filled_qty <= 0:
            logger.error(
                "[%s] Exit order failed (%s): %s",
                position.symbol,
                reason,
                result.message,
            )
            if backup_cancelled and self.config.broker_backup_stop_enabled:
                self._place_backup_stop(position)
                self.save_state()
            return None

        self._finalize_close(
            position=position,
            filled_qty=result.filled_qty,
            exit_price=result.avg_fill_price,
            reason=reason,
            exit_fee=result.fee_paid if (result.fees_actual or self.config.execution_mode == "paper") else None,
            price_source=result.price_source,
            exit_reference_price=ref_price,
            order_id=result.order_id,
        )
        if position.symbol in self.positions and self.config.broker_backup_stop_enabled:
            # Partial exit: protect what is left
            self._place_backup_stop(self.positions[position.symbol])
            self.save_state()
        return result

    def _finalize_close(
        self,
        position: Position,
        filled_qty: float,
        exit_price: float,
        reason: str,
        exit_fee: Optional[float] = None,
        price_source: str = "estimated",
        exit_reference_price: Optional[float] = None,
        order_id: str = "",
    ) -> Dict[str, Any]:
        """Record a (full or partial) close: P&L, journal, cooldown, alerts.

        P&L is in account currency and includes exchange-rate movement between
        entry and exit. If `filled_qty` is less than the position, the remainder
        stays open.
        """
        symbol = position.symbol
        fx_entry = self._position_fx(position)
        fx_exit = self._fx_for(symbol, fallback=fx_entry)
        total_qty = position.quantity
        is_partial = filled_qty < total_qty - QTY_EPS
        filled_qty = min(filled_qty, total_qty)
        share = filled_qty / total_qty if total_qty > 0 else 1.0

        sign = 1.0 if position.side == Side.LONG else -1.0
        gross_pnl = sign * filled_qty * (exit_price * fx_exit - position.entry_price * fx_entry)
        fee_rate = self._effective_fee_rate(symbol)
        if exit_fee is None:
            exit_fee = filled_qty * exit_price * fx_exit * fee_rate
        entry_fee = position.entry_fee_paid * share
        if position.entry_fee_paid <= 0.0 and fee_rate > 0.0:
            entry_fee = filled_qty * position.entry_price * fx_entry * fee_rate
        total_fee = entry_fee + exit_fee

        net_pnl = gross_pnl - total_fee
        r_mult = position.current_r_multiple(exit_price)
        self.realized_pnl += net_pnl

        now_utc = datetime.now(timezone.utc)
        held_mins = 0
        try:
            opened_dt = datetime.fromisoformat(position.opened_at)
            if opened_dt.tzinfo is None:
                opened_dt = opened_dt.replace(tzinfo=timezone.utc)
            held_mins = max(0, int((now_utc - opened_dt).total_seconds() // 60))
        except Exception:
            held_mins = 0

        notional_entry = filled_qty * position.entry_price * fx_entry
        net_pnl_pct = (net_pnl / notional_entry * 100.0) if notional_entry > 0 else 0.0
        gross_pnl_pct = (
            sign * ((exit_price - position.entry_price) / position.entry_price) * 100.0
            if position.entry_price > 0
            else 0.0
        )

        journey_pts = list(position.price_history or [])
        if not journey_pts and position.entry_price > 0:
            journey_pts = [{"ts": position.opened_at, "price": round(float(position.entry_price), 4)}]
        journey_pts.append({"ts": now_utc.isoformat(), "price": round(float(exit_price), 4)})

        if is_partial:
            reason = f"{reason} (partial fill {filled_qty:.4f}/{total_qty:.4f})"

        self.closed_trades.insert(
            0,
            {
                "symbol": symbol,
                "side": position.side.value,
                "quantity": round(filled_qty, 4),
                "entry_price": round(position.entry_price, 4),
                "exit_price": round(exit_price, 4),
                "currency": self.config.account_currency,
                "gross_pnl": round(gross_pnl, 2),
                "fee_paid": round(total_fee, 2),
                "net_pnl": round(net_pnl, 2),
                "pnl_pct": round(net_pnl_pct, 2),
                "gross_pnl_pct": round(gross_pnl_pct, 2),
                "r_multiple": round(r_mult, 2),
                "held_minutes": held_mins,
                "reason": reason,
                "opened_at": position.opened_at,
                "closed_at": now_utc.isoformat(),
                "price_history": journey_pts,
            },
        )
        self.closed_trades = self.closed_trades[:25]

        # Permanent journal record with excursion analytics (MFE / MAE), slippage and entry context
        one_r = position.initial_risk_per_unit
        if position.side == Side.LONG:
            best_px = max(position.highest_price, position.entry_price, exit_price)
            worst_px = min(position.lowest_price, position.entry_price, exit_price)
            mfe_abs, mae_abs = best_px - position.entry_price, position.entry_price - worst_px
        else:
            best_px = min(position.lowest_price, position.entry_price, exit_price)
            worst_px = max(position.highest_price, position.entry_price, exit_price)
            mfe_abs, mae_abs = position.entry_price - best_px, worst_px - position.entry_price

        def _slippage_pct(actual: float, reference: Optional[float], buying: bool) -> Optional[float]:
            # Positive = worse than the quote we traded on
            if not reference or reference <= 0 or actual <= 0:
                return None
            diff = (actual - reference) if buying else (reference - actual)
            return round(diff / reference * 100.0, 4)

        opened_date = str(position.opened_at)[:10]
        journal_rec = {k: v for k, v in self.closed_trades[0].items() if k != "price_history"}
        journal_rec.update(
            {
                "market": "UK" if str(symbol).endswith("_UK_EQ") else "US",
                "initial_stop_loss": round(position.initial_stop_loss, 4),
                "final_stop_loss": round(position.stop_loss, 4),
                "take_profit": round(position.take_profit, 4),
                "atr_at_entry": round(position.atr_at_entry, 4),
                "trailing_active": bool(position.trailing_active),
                "tp_extensions": int(position.tp_extensions),
                "mfe_pct": round(mfe_abs / position.entry_price * 100.0, 3) if position.entry_price else 0.0,
                "mae_pct": round(mae_abs / position.entry_price * 100.0, 3) if position.entry_price else 0.0,
                "mfe_r": round(mfe_abs / one_r, 3) if one_r > 0 else None,
                "mae_r": round(mae_abs / one_r, 3) if one_r > 0 else None,
                "overnight": bool(opened_date and opened_date != now_utc.date().isoformat()),
                "fx_rate_entry": round(fx_entry, 6),
                "fx_rate_exit": round(fx_exit, 6),
                "entry_price_source": position.entry_price_source or "estimated",
                "exit_price_source": price_source,
                "entry_slippage_pct": _slippage_pct(
                    position.entry_price, position.entry_reference_price, position.side == Side.LONG
                ),
                "exit_slippage_pct": _slippage_pct(
                    exit_price, exit_reference_price, position.side != Side.LONG
                ),
                "exit_order_id": order_id,
                "entry_context": dict(position.entry_context or {}),
            }
        )
        journal_rec["outcome_tag"] = self.classify_trade_outcome(journal_rec)
        self.closed_trades[0]["outcome_tag"] = journal_rec["outcome_tag"]
        self._append_journal(journal_rec)
        self.last_closed_record = journal_rec
        if self.on_trade_closed is not None:
            try:
                self.on_trade_closed(journal_rec)
            except Exception as exc:
                logger.warning("[%s] on_trade_closed hook failed: %s", symbol, exc)

        if net_pnl < 0 and self.config.cooldown_minutes_after_loss > 0:
            until_dt = now_utc + timedelta(minutes=self.config.cooldown_minutes_after_loss)
            self.cooldown_until[symbol] = until_dt.isoformat()
            logger.info(
                "[%s] Placed on %d-minute post-loss cooldown until %s UTC",
                symbol,
                self.config.cooldown_minutes_after_loss,
                until_dt.strftime("%H:%M:%S"),
            )

        if is_partial:
            position.quantity = round(total_qty - filled_qty, 8)
            position.entry_fee_paid = max(0.0, position.entry_fee_paid - entry_fee)
            logger.warning(
                "[%s] Partial exit: %.4f of %.4f filled; %.4f remains open.",
                symbol,
                filled_qty,
                total_qty,
                position.quantity,
            )
        else:
            self.positions.pop(symbol, None)
        self.save_state()

        if self.telegram_notifier and getattr(self.telegram_notifier, "enabled", False):
            try:
                chart_df = None
                if self.data_handler is not None:
                    try:
                        chart_df = self.data_handler.fetch_closed_ohlcv(symbol)
                    except Exception:
                        pass
                self.telegram_notifier.send_trade_closed_alert(
                    symbol=symbol,
                    side=position.side.value,
                    qty=filled_qty,
                    entry_price=position.entry_price,
                    exit_price=exit_price,
                    net_pnl=net_pnl,
                    pnl_pct=net_pnl_pct,
                    r_multiple=r_mult,
                    held_minutes=held_mins,
                    reason=reason,
                    df=chart_df,
                    fee_paid=total_fee,
                    gross_pnl=gross_pnl,
                )
            except Exception as exc:
                logger.warning("[%s] Failed to dispatch Telegram exit alert: %s", symbol, exc)

        logger.info(
            "[%s] POSITION CLOSED (%s): order_id=%s qty=%.4f @ %.4f (%s, entry=%.4f) | "
            "Net PnL=%.2f %s (%.2fR) | Reason: %s",
            symbol,
            position.side.value,
            order_id,
            filled_qty,
            exit_price,
            price_source,
            position.entry_price,
            net_pnl,
            self.config.account_currency,
            r_mult,
            reason,
        )
        return journal_rec

    # -------------------------------------------------------------------------
    # Broker-side backup stop (optional, BROKER_BACKUP_STOP_ENABLED)
    # -------------------------------------------------------------------------
    def _backup_stop_price(self, pos: Position) -> float:
        extra = self.config.broker_backup_stop_atr_mult * pos.atr_at_entry
        if pos.side == Side.LONG:
            return max(0.01, pos.initial_stop_loss - extra)
        return pos.initial_stop_loss + extra

    def _place_backup_stop(self, pos: Position) -> None:
        """Place a good-till-cancelled stop at Trading 212 below the bot's own stop.

        The bot still manages exits itself. This order only matters if the bot is
        offline when the price falls through it.
        """
        if self.t212_client is None or pos.backup_stop_order_id:
            return
        stop_price = self._backup_stop_price(pos)
        signed_qty = -abs(pos.quantity) if pos.side == Side.LONG else abs(pos.quantity)
        try:
            resp = self.t212_client.place_stop_order(
                ticker=pos.symbol,
                signed_quantity=signed_qty,
                stop_price=stop_price,
                time_validity="GOOD_TILL_CANCEL",
            )
            pos.backup_stop_order_id = str(resp.get("id", ""))
            logger.info(
                "[%s] Broker backup stop placed: id=%s stop=%.4f (bot stop=%.4f)",
                pos.symbol,
                pos.backup_stop_order_id,
                stop_price,
                pos.stop_loss,
            )
        except Trading212APIError as exc:
            logger.warning(
                "[%s] Could not place broker backup stop (position is protected by the bot only): %s",
                pos.symbol,
                exc,
            )

    def _cancel_order_quietly(self, order_id: str) -> None:
        if self.t212_client is None or not order_id:
            return
        try:
            self.t212_client.cancel_order(order_id)
        except Trading212APIError as exc:
            if exc.status_code != 404:
                logger.warning("Could not cancel order %s: %s", order_id, exc)

    def _cancel_backup_stop(self, pos: Position) -> str:
        """Cancel the backup stop before the bot exits.

        Returns 'cleared' (cancelled or gone without filling), 'filled' (the stop
        already closed the position; the close has been recorded) or 'failed'.
        """
        order_id = pos.backup_stop_order_id
        if not order_id or self.t212_client is None:
            return "cleared"
        self._cancel_order_quietly(order_id)
        try:
            state = self.t212_client.get_order_by_id(order_id)
        except Trading212APIError as exc:
            logger.warning("[%s] Could not confirm backup stop cancel: %s", pos.symbol, exc)
            return "failed"
        status = str((state or {}).get("status", "")).upper()
        if state is not None and status not in DEAD_ORDER_STATUSES:
            logger.warning("[%s] Backup stop %s still working (status=%s).", pos.symbol, order_id, status)
            return "failed"
        if state is None and self._broker_qty(pos.symbol) == 0.0:
            # The stop disappeared and so did the shares: it filled.
            if self._close_from_backup_stop_fill(pos):
                return "filled"
        pos.backup_stop_order_id = ""
        return "cleared"

    def _close_from_backup_stop_fill(self, pos: Position) -> bool:
        """If the backup stop filled, record the close from the broker's fill."""
        if self.t212_client is None:
            return False
        try:
            fill = self.t212_client.get_order_fill(pos.backup_stop_order_id, pos.symbol)
        except Trading212APIError as exc:
            logger.warning("[%s] Could not read backup stop fill: %s", pos.symbol, exc)
            fill = None
        if not fill or not fill.get("price") or fill.get("status") not in {"FILLED", "PARTIALLY_FILLED", ""}:
            return False
        logger.warning(
            "[%s] Broker backup stop %s FILLED at %.4f while the bot was not managing it.",
            pos.symbol,
            pos.backup_stop_order_id,
            fill["price"],
        )
        fees = self._fees_in_account_ccy(fill)
        order_id = pos.backup_stop_order_id
        pos.backup_stop_order_id = ""
        self._finalize_close(
            position=pos,
            filled_qty=min(pos.quantity, float(fill.get("quantity") or pos.quantity)),
            exit_price=float(fill["price"]),
            reason="Broker backup stop filled (bot was offline or slow)",
            exit_fee=fees,
            price_source="broker_fill",
            exit_reference_price=self._backup_stop_price(pos),
            order_id=order_id,
        )
        return True

    # -------------------------------------------------------------------------
    # Low-Level Execution: Local Paper Simulator vs Trading 212 API v0
    # -------------------------------------------------------------------------
    def _place_and_verify_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        reference_price: float,
        order_book: OrderBookSnapshot,
        is_exit: bool = False,
        fx_rate: float = 1.0,
    ) -> OrderResult:
        if self.config.execution_mode == "paper":
            return self._simulate_paper_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_book=order_book,
                is_exit=is_exit,
                fx_rate=fx_rate,
            )
        return self._execute_t212_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            reference_price=reference_price,
            is_exit=is_exit,
        )

    def _simulate_paper_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_book: OrderBookSnapshot,
        is_exit: bool = False,
        fx_rate: float = 1.0,
    ) -> OrderResult:
        """Simulate a top-of-book fill in local paper mode (balance in account currency)."""
        fill_price = order_book.ask if side == "buy" else order_book.bid
        notional = quantity * fill_price * fx_rate
        fee = notional * self._effective_fee_rate(symbol)
        order_id = f"paper-{uuid.uuid4().hex[:10]}"

        if not is_exit:
            total_cost = notional + fee
            if total_cost > self.paper_quote_balance:
                return OrderResult(
                    success=False,
                    order_id=order_id,
                    symbol=symbol,
                    side=side,
                    order_type=self.config.entry_order_type,
                    filled_qty=0.0,
                    avg_fill_price=0.0,
                    fee_paid=0.0,
                    status="rejected",
                    message=(
                        f"Insufficient paper balance: need {total_cost:.2f}, "
                        f"have {self.paper_quote_balance:.2f} {self.config.account_currency}"
                    ),
                    price_source="simulated",
                )
            self.paper_quote_balance -= total_cost
        else:
            pos = self.positions.get(symbol)
            if pos is not None and pos.side == Side.SHORT:
                fx_entry = self._position_fx(pos)
                locked = pos.quantity * pos.entry_price * fx_entry
                self.paper_quote_balance += locked + pos.unrealized_pnl_account(fill_price, fx_rate) - fee
            else:
                self.paper_quote_balance += notional - fee

        return OrderResult(
            success=True,
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=self.config.entry_order_type if not is_exit else "market",
            filled_qty=quantity,
            avg_fill_price=fill_price,
            fee_paid=fee,
            status="filled",
            message="Simulated paper fill against live top-of-book",
            price_source="simulated",
            fees_actual=True,
        )

    # --- Trading 212 helpers -------------------------------------------------
    def _broker_qty(self, symbol: str) -> Optional[float]:
        """Current broker quantity for `symbol` (0.0 if none), or None if the lookup failed."""
        assert self.t212_client is not None
        try:
            pos = self.t212_client.get_position(symbol)
        except Trading212APIError as exc:
            logger.warning("[%s] Could not read Trading 212 position: %s", symbol, exc)
            return None
        if not pos:
            return 0.0
        return float(pos.get("quantity") or 0.0)

    def _has_pending_order(self, symbol: str, include_stops: bool = False) -> Optional[bool]:
        """True if Trading 212 has a working order for `symbol`; None if the lookup failed.

        The bot's own backup stop orders are ignored unless `include_stops`.
        """
        if self.t212_client is None:
            return False
        try:
            orders = self.t212_client.get_orders()
        except Trading212APIError as exc:
            logger.warning("[%s] Could not list working orders: %s", symbol, exc)
            return None
        for o in orders:
            if str(o.get("ticker")) != symbol:
                continue
            if not include_stops and str(o.get("type", "")).upper() == "STOP":
                continue
            return True
        return False

    def _await_qty_change(
        self, symbol: str, pre_qty: float, is_exit: bool, target: float, attempts: int = 3
    ) -> Tuple[float, Optional[Dict[str, Any]]]:
        """Poll the broker position until the expected change appears.

        Returns `(filled_qty, last_position_payload)`.
        """
        assert self.t212_client is not None
        delta = 0.0
        payload: Optional[Dict[str, Any]] = None
        for attempt in range(attempts):
            try:
                payload = self.t212_client.get_position(symbol)
            except Trading212APIError as exc:
                logger.warning("[%s] Position check failed (attempt %d): %s", symbol, attempt + 1, exc)
                payload = None
                continue
            now_qty = float((payload or {}).get("quantity") or 0.0)
            delta = (pre_qty - now_qty) if is_exit else (now_qty - pre_qty)
            if delta >= target - QTY_EPS:
                break
            if attempt < attempts - 1:
                time.sleep(1.0)
        return max(0.0, delta), payload

    def _poll_order(self, order_id: str, initial: Optional[Dict[str, Any]]) -> str:
        """Poll an order until it leaves the working state or the timeout passes.

        Returns 'GONE' (no longer listed: filled or cancelled), a terminal status
        such as 'FILLED' / 'CANCELLED' / 'REJECTED', 'WORKING' on timeout, or
        'UNKNOWN' if polling failed.
        """
        assert self.t212_client is not None
        status = str((initial or {}).get("status", "")).upper()
        deadline = time.time() + self.config.order_fill_timeout_sec
        while True:
            if status == "FILLED" or status in DEAD_ORDER_STATUSES:
                return status
            if time.time() >= deadline:
                return "WORKING"
            time.sleep(1.0)
            try:
                state = self.t212_client.get_order_by_id(order_id)
            except Trading212APIError as exc:
                logger.warning("Order %s status check failed: %s", order_id, exc)
                return "UNKNOWN"
            if state is None:
                return "GONE"
            status = str(state.get("status", "")).upper()

    def _fees_in_account_ccy(self, fill: Dict[str, Any]) -> float:
        fees = float(fill.get("fees") or 0.0)
        ccy = str(fill.get("fees_currency") or "").upper()
        if fees and ccy and ccy != self.config.account_currency:
            fees *= self.fx.rate(ccy) if ccy else 1.0
        return fees

    def _fail(self, symbol: str, side: str, order_type: str, message: str, status: str = "error", order_id: str = "") -> OrderResult:
        return OrderResult(
            success=False,
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            filled_qty=0.0,
            avg_fill_price=0.0,
            fee_paid=0.0,
            status=status,
            message=message,
        )

    def _execute_t212_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        reference_price: float,
        is_exit: bool = False,
    ) -> OrderResult:
        """Submit an order to Trading 212 and confirm what actually filled."""
        client = self.t212_client
        if client is None:
            raise RuntimeError("Trading212Client is not initialized.")

        target = abs(quantity)
        direction = 1.0 if side.lower() == "buy" else -1.0
        order_type = "market" if is_exit else self.config.entry_order_type

        pre_qty = self._broker_qty(symbol)
        if pre_qty is None:
            return self._fail(symbol, side, order_type, "Could not read the position before ordering; not sending.")

        order_ids: List[str] = []

        def _send(kind: str, qty: float) -> Dict[str, Any]:
            if kind == "limit":
                return client.place_limit_order(
                    ticker=symbol,
                    signed_quantity=direction * qty,
                    limit_price=reference_price,
                    time_validity=self.config.t212_time_validity,
                )
            return client.place_market_order(ticker=symbol, signed_quantity=direction * qty)

        try:
            try:
                resp = _send(order_type, target)
            except Trading212APIError as exc:
                if order_type == "limit" and exc.status_code == 400 and not exc.outcome_unknown:
                    # Rejected outright (e.g. fractional limit orders), so nothing is working.
                    logger.warning(
                        "[%s] Limit order rejected (HTTP 400: %s); sending a MARKET order instead.",
                        symbol,
                        exc,
                    )
                    order_type = "market"
                    resp = _send("market", target)
                else:
                    raise
            order_ids.append(str(resp.get("id", "")))
            logger.info(
                "[%s] Trading 212 %s %s order submitted: id=%s qty=%.4f",
                symbol, order_type.upper(), side.upper(), order_ids[-1], direction * target,
            )

            status = self._poll_order(order_ids[-1], resp)
            if status in {"CANCELLED", "REJECTED", "REPLACED"}:
                return self._fail(
                    symbol, side, order_type, f"Trading 212 order ended with status={status}",
                    status=status.lower(), order_id=order_ids[-1],
                )

            if status == "WORKING" and order_type == "limit":
                logger.warning(
                    "[%s] Limit order %s unfilled after %ds; cancelling before any market order.",
                    symbol, order_ids[-1], self.config.order_fill_timeout_sec,
                )
                self._cancel_order_quietly(order_ids[-1])
                try:
                    state = client.get_order_by_id(order_ids[-1])
                except Trading212APIError as exc:
                    state = {"status": f"UNCONFIRMED ({exc})"}
                state_status = str((state or {}).get("status", "")).upper()
                if state is not None and state_status not in DEAD_ORDER_STATUSES:
                    return self._fail(
                        symbol, side, order_type,
                        f"Limit order {order_ids[-1]} could not be confirmed cancelled (status={state_status}); "
                        "not sending a market order to avoid a double fill.",
                        status="pending", order_id=order_ids[-1],
                    )
                filled_so_far, _ = self._await_qty_change(symbol, pre_qty, is_exit, target, attempts=1)
                remaining = round(target - filled_so_far, self.config.fractional_decimals)
                if remaining > QTY_EPS:
                    order_type = "market"
                    mkt = _send("market", remaining)
                    order_ids.append(str(mkt.get("id", "")))
                    self._poll_order(order_ids[-1], mkt)
        except Trading212APIError as exc:
            if exc.status_code == 403:
                logger.error(
                    "[%s] Trading 212 returned HTTP 403 Forbidden. Check the API key permissions "
                    "in the Trading 212 app (Settings -> API): 'Orders - Execute' and 'Orders - Read'.",
                    symbol,
                )
            if not exc.outcome_unknown:
                logger.error("[%s] Trading 212 order error: %s", symbol, exc)
                return self._fail(symbol, side, order_type, str(exc), order_id=order_ids[-1] if order_ids else "")
            logger.error(
                "[%s] Order request failed with an UNKNOWN outcome (%s); checking the account instead of retrying.",
                symbol, exc,
            )

        # Confirm what actually filled from the position change
        filled_qty, pos_payload = self._await_qty_change(symbol, pre_qty, is_exit, target)
        if filled_qty <= QTY_EPS:
            pending = self._has_pending_order(symbol)
            if pending:
                return self._fail(
                    symbol, side, order_type,
                    "Order accepted but not filled yet (still working at Trading 212, e.g. market closed).",
                    status="pending", order_id=order_ids[-1] if order_ids else "",
                )
            return self._fail(
                symbol, side, order_type, "No fill observed in the Trading 212 position.",
                order_id=order_ids[-1] if order_ids else "",
            )
        filled_qty = min(filled_qty, target) if is_exit else filled_qty

        # Fill price and fees: order history first, then position average, then the quote
        fill_price: Optional[float] = None
        fees: Optional[float] = None
        price_source = "estimated"
        fills = []
        for oid in order_ids:
            if not oid:
                continue
            try:
                info = client.get_order_fill(oid, symbol)
            except Exception as exc:
                logger.warning("[%s] Order history lookup failed for %s: %s", symbol, oid, exc)
                info = None
            if info and info.get("price") and float(info.get("quantity") or 0.0) > 0:
                fills.append(info)
        if fills:
            fqty = sum(float(f["quantity"]) for f in fills)
            fill_price = sum(float(f["price"]) * float(f["quantity"]) for f in fills) / fqty
            fees = sum(self._fees_in_account_ccy(f) for f in fills)
            price_source = "broker_fill"
        elif not is_exit and pre_qty <= QTY_EPS and pos_payload and pos_payload.get("averagePrice"):
            fill_price = float(pos_payload["averagePrice"])
            price_source = "broker_avg"

        if fill_price is not None and reference_price > 0:
            if abs(fill_price / reference_price - 1.0) > MAX_FILL_PRICE_DEVIATION:
                logger.error(
                    "[%s] Broker fill price %.4f is >%.0f%% from quote %.4f (likely a units mismatch); "
                    "using the quote instead.",
                    symbol, fill_price, MAX_FILL_PRICE_DEVIATION * 100, reference_price,
                )
                fill_price, fees, price_source = None, None, "estimated"
        if fill_price is None:
            fill_price = reference_price
            logger.warning(
                "[%s] Using the quote %.4f as the fill price (broker fill not available).",
                symbol, reference_price,
            )

        return OrderResult(
            success=True,
            order_id=order_ids[-1] if order_ids else "",
            symbol=symbol,
            side=side,
            order_type=order_type,
            filled_qty=filled_qty,
            avg_fill_price=fill_price,
            fee_paid=fees if fees is not None else 0.0,
            status="filled" if filled_qty >= target - QTY_EPS else "partially_filled",
            message="Executed and confirmed against the Trading 212 position",
            price_source=price_source,
            fees_actual=fees is not None,
        )
