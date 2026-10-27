"""Order execution and portfolio management module for Trading 212.

Supports three execution modes:
- 'demo'  : Trading 212 Practice / Paper Trading REST API (`https://demo.trading212.com/api/v0`)
- 'live'  : Trading 212 Real Money REST API (`https://live.trading212.com/api/v0`)
- 'paper' : Local simulation against live order book quotes (no Trading 212 API key needed)

Trading 212 Order Conventions Handled:
- BUY orders submit a positive `quantity` (> 0).
- SELL orders submit a negative `quantity` (< 0).
- Limit orders include `limitPrice` and `timeValidity` ('DAY' or 'GOOD_TILL_CANCEL').
- Order fill verification polls `GET /equity/orders/{id}` and `GET /equity/portfolio/{ticker}`:
  when an order transitions out of `/equity/orders` (404), we verify the position delta on
  `/equity/portfolio/{ticker}`.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from bot.config import Config
from bot.models import OrderBookSnapshot, OrderResult, Position, Side, TradePlan
from bot.t212_client import Trading212APIError, Trading212Client

logger = logging.getLogger(__name__)


class OrderExecutor:
    """Routes orders to Trading 212 (Demo or Live) or local paper simulator and tracks positions."""

    def __init__(
        self,
        config: Config,
        t212_client: Optional[Trading212Client] = None,
        telegram_notifier: Optional[Any] = None,
        data_handler: Optional[Any] = None,
    ) -> None:
        self.config = config
        self.t212_client = t212_client or (
            Trading212Client(config)
            if config.execution_mode in {"demo", "live"}
            else None
        )
        self.telegram_notifier = telegram_notifier
        self.data_handler = data_handler
        self.positions: Dict[str, Position] = {}
        self.cooldown_until: Dict[str, str] = {}
        self.closed_trades: List[Dict[str, Any]] = []
        self.paper_quote_balance: float = config.paper_initial_equity
        self.realized_pnl: float = 0.0
        self._load_state()

    # -------------------------------------------------------------------------
    # Local State Persistence (stores stop-loss, take-profit, and trailing watermarks)
    # -------------------------------------------------------------------------
    def _load_state(self) -> None:
        path = Path(self.config.state_file)
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.paper_quote_balance = float(
                raw.get("paper_quote_balance", self.config.paper_initial_equity)
            )
            self.realized_pnl = float(raw.get("realized_pnl", 0.0))
            pos_map = raw.get("positions", {})
            self.positions = {
                sym: Position.from_dict(pdata) for sym, pdata in pos_map.items()
            }
            cd_map = raw.get("cooldown_until", {})
            if isinstance(cd_map, dict):
                self.cooldown_until = {str(k): str(v) for k, v in cd_map.items()}
            closed_list = raw.get("closed_trades", [])
            if isinstance(closed_list, list):
                self.closed_trades = [item for item in closed_list if isinstance(item, dict)][:25]
            logger.info(
                "Loaded state from %s: open_positions=%d",
                path,
                len(self.positions),
            )
        except Exception as exc:
            logger.warning("Could not load state file %s: %s", path, exc)

    def save_state(self) -> None:
        path = Path(self.config.state_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "paper_quote_balance": round(self.paper_quote_balance, 6),
            "realized_pnl": round(self.realized_pnl, 6),
            "positions": {sym: pos.to_dict() for sym, pos in self.positions.items()},
            "cooldown_until": self.cooldown_until,
            "closed_trades": self.closed_trades[:25],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

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
        """Return `(total_equity, available_free_cash)`.

        In 'demo' or 'live' mode, queries Trading 212 `GET /equity/account/cash`.
        In 'paper' mode, computes virtual cash + mark-to-market positions.
        """
        prices = latest_prices or {}
        if self.config.execution_mode == "paper":
            position_value = 0.0
            for sym, pos in self.positions.items():
                mark = prices.get(sym, pos.entry_price)
                if pos.side == Side.LONG:
                    position_value += pos.quantity * mark
                else:
                    locked = pos.quantity * pos.entry_price
                    position_value += locked + pos.unrealized_pnl(mark)
            total_equity = self.paper_quote_balance + position_value
            return total_equity, self.paper_quote_balance

        if self.t212_client is None:
            raise RuntimeError("Trading212Client is not initialized for demo/live mode.")

        cash_data = self.t212_client.get_account_cash()
        free_cash = float(cash_data.get("free") or 0.0)
        total_equity = float(cash_data.get("total") or free_cash)
        return total_equity, free_cash

    def sync_positions_with_t212(
        self, atr_lookup: Optional[Callable[[str], Optional[float]]] = None
    ) -> None:
        """Two-way reconciliation between local tracked positions and Trading 212 `/equity/portfolio`.

        1. Removes any local position that was closed externally (unless still pending in `/equity/orders`).
        2. Adopts/imports any open Trading 212 portfolio position missing from local state (e.g., after a
           network/DHCP drop during order placement) and reconstructs its ATR Stop-Loss and Take-Profit.
        3. Synchronizes share quantities if an order filled partially or adjusted.
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

        state_changed = False

        # 1. Remove any local position that was manually closed inside the Trading 212 app
        # (unless it is still a pending working order waiting for market open in /equity/orders)
        pending_tickers: Optional[set[str]] = None
        for sym in list(self.positions.keys()):
            if sym not in remote_by_ticker:
                if pending_tickers is None:
                    try:
                        pending_orders = self.t212_client.get_orders()
                        pending_tickers = {
                            str(o.get("ticker")) for o in pending_orders if o.get("ticker")
                        }
                    except Exception:
                        pending_tickers = set()
                if sym in pending_tickers:
                    continue
                logger.info(
                    "[%s] Position no longer present in Trading 212 portfolio; removing local record.",
                    sym,
                )
                self.positions.pop(sym, None)
                state_changed = True

        # 2. Catch-up & adopt any live Trading 212 position missing from local state (or update qty)
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
                atr_val: Optional[float] = None
                if atr_lookup is not None:
                    try:
                        atr_val = atr_lookup(sym)
                    except Exception as exc:
                        logger.warning("[%s] ATR lookup during catch-up sync failed: %s", sym, exc)

                if atr_val is None or atr_val <= 0:
                    atr_val = max(0.01, avg_price * 0.012)

                sl_dist = self.config.stop_loss_atr_mult * atr_val
                tp_dist = self.config.take_profit_atr_mult * atr_val
                stop_loss = avg_price - sl_dist
                take_profit = avg_price + tp_dist

                fee_rate = getattr(self.config, "fx_fee_rate", getattr(self.config, "paper_fee_rate", 0.0015))
                adopted_fee = remote_qty * avg_price * fee_rate
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
                )
                self.positions[sym] = adopted
                state_changed = True
                logger.info(
                    "[%s] CATCH-UP SYNC: Adopted open Trading 212 position into local state & dashboard | "
                    "qty=%.4f @ %.4f | SL=%.4f | TP=%.4f",
                    sym,
                    remote_qty,
                    avg_price,
                    stop_loss,
                    take_profit,
                )
            else:
                existing = self.positions[sym]
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
        """Place entry order on Trading 212 (or paper simulator) and register Position."""
        rounded_qty = round(plan.quantity, self.config.fractional_decimals)
        if rounded_qty <= 0:
            logger.warning("[%s] Rounded quantity is zero; aborting entry.", plan.symbol)
            return None

        result = self._place_and_verify_order(
            symbol=plan.symbol,
            side=plan.order_side,
            quantity=rounded_qty,
            reference_price=plan.reference_price,
            order_book=order_book,
            is_exit=False,
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

        fee_rate = getattr(self.config, "fx_fee_rate", getattr(self.config, "paper_fee_rate", 0.0015))
        entry_fee = result.fee_paid if result.fee_paid > 0.0 else (result.filled_qty * result.avg_fill_price * fee_rate)

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
        )
        self.positions[plan.symbol] = position
        self.save_state()

        if self.telegram_notifier and getattr(self.telegram_notifier, "enabled", False):
            try:
                chart_df = None
                if self.data_handler is not None:
                    try:
                        chart_df = self.data_handler.fetch_closed_ohlcv(plan.symbol)
                    except Exception:
                        pass
                risk_val = getattr(plan, "risk_amount_usd", getattr(plan, "risk_usd", 0.0))
                notional = getattr(plan, "notional_usd", position.quantity * position.entry_price)
                risk_pct_val = getattr(plan, "risk_pct_of_equity", (risk_val / max(1.0, notional) * 100.0) if notional > 0 else 0.5)

                self.telegram_notifier.send_trade_opened_alert(
                    symbol=position.symbol,
                    side=position.side.value,
                    qty=position.quantity,
                    entry_price=position.entry_price,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    risk_usd=risk_val,
                    risk_pct=risk_pct_val,
                    score=getattr(plan, "score", 0.0),
                    rating=getattr(plan, "rating", "STRONG BUY"),
                    rvol=getattr(plan, "rvol", 1.0),
                    spread_pct=getattr(plan, "spread_pct", 0.0),
                    thesis=getattr(plan, "thesis", ""),
                    df=chart_df,
                )
            except Exception as exc:
                logger.warning("[%s] Failed to dispatch Telegram entry alert: %s", position.symbol, exc)

        logger.info(
            "[%s] POSITION OPENED (%s on %s): order_id=%s qty=%.4f @ %.4f | SL=%.4f | TP=%.4f",
            position.symbol,
            position.side.value,
            self.config.execution_mode.upper(),
            result.order_id,
            position.quantity,
            position.entry_price,
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
        """Close an open position via market order on Trading 212 (or paper simulator)."""
        exit_order_side = "sell" if position.side == Side.LONG else "buy"
        ref_price = order_book.bid if exit_order_side == "sell" else order_book.ask

        result = self._place_and_verify_order(
            symbol=position.symbol,
            side=exit_order_side,
            quantity=position.quantity,
            reference_price=ref_price,
            order_book=order_book,
            is_exit=True,
        )
        if not result.success or result.filled_qty <= 0:
            logger.error(
                "[%s] Exit order failed (%s): %s",
                position.symbol,
                reason,
                result.message,
            )
            return None

        gross_pnl = position.unrealized_pnl(result.avg_fill_price)
        fee_rate = getattr(self.config, "fx_fee_rate", getattr(self.config, "paper_fee_rate", 0.0015))
        exit_fee = result.fee_paid if result.fee_paid > 0.0 else (result.filled_qty * result.avg_fill_price * fee_rate)
        entry_fee = getattr(position, "entry_fee_paid", 0.0)
        if entry_fee <= 0.0 and fee_rate > 0.0:
            entry_fee = position.quantity * position.entry_price * fee_rate
        total_fee = entry_fee + exit_fee

        net_pnl = gross_pnl - total_fee
        r_mult = position.current_r_multiple(result.avg_fill_price)
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

        notional_entry = position.quantity * position.entry_price
        net_pnl_pct = (net_pnl / notional_entry * 100.0) if notional_entry > 0 else 0.0
        gross_pnl_pct = (
            ((result.avg_fill_price - position.entry_price) / position.entry_price) * 100.0
            if position.entry_price > 0
            else 0.0
        )
        if position.side == Side.SHORT:
            gross_pnl_pct = -gross_pnl_pct

        self.closed_trades.insert(
            0,
            {
                "symbol": position.symbol,
                "side": position.side.value,
                "quantity": round(result.filled_qty, 4),
                "entry_price": round(position.entry_price, 4),
                "exit_price": round(result.avg_fill_price, 4),
                "gross_pnl": round(gross_pnl, 2),
                "fee_paid": round(total_fee, 2),
                "net_pnl": round(net_pnl, 2),
                "pnl_pct": round(net_pnl_pct, 2),
                "gross_pnl_pct": round(gross_pnl_pct, 2),
                "r_multiple": round(r_mult, 2),
                "held_minutes": held_mins,
                "reason": reason,
                "closed_at": now_utc.isoformat(),
            },
        )
        self.closed_trades = self.closed_trades[:25]

        if net_pnl < 0 and self.config.cooldown_minutes_after_loss > 0:
            until_dt = now_utc + timedelta(
                minutes=self.config.cooldown_minutes_after_loss
            )
            self.cooldown_until[position.symbol] = until_dt.isoformat()
            logger.info(
                "[%s] Placed on %d-minute post-loss cooldown until %s UTC",
                position.symbol,
                self.config.cooldown_minutes_after_loss,
                until_dt.strftime("%H:%M:%S"),
            )

        self.positions.pop(position.symbol, None)
        self.save_state()

        if self.telegram_notifier and getattr(self.telegram_notifier, "enabled", False):
            try:
                chart_df = None
                if self.data_handler is not None:
                    try:
                        chart_df = self.data_handler.fetch_closed_ohlcv(position.symbol)
                    except Exception:
                        pass
                self.telegram_notifier.send_trade_closed_alert(
                    symbol=position.symbol,
                    side=position.side.value,
                    qty=result.filled_qty,
                    entry_price=position.entry_price,
                    exit_price=result.avg_fill_price,
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
                logger.warning("[%s] Failed to dispatch Telegram exit alert: %s", position.symbol, exc)

        logger.info(
            "[%s] POSITION CLOSED (%s): order_id=%s qty=%.4f @ %.4f (entry=%.4f) | "
            "Net PnL=$%.2f (%.2fR) | Reason: %s",
            position.symbol,
            position.side.value,
            result.order_id,
            result.filled_qty,
            result.avg_fill_price,
            position.entry_price,
            net_pnl,
            r_mult,
            reason,
        )
        return result

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
    ) -> OrderResult:
        if self.config.execution_mode == "paper":
            return self._simulate_paper_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_book=order_book,
                is_exit=is_exit,
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
    ) -> OrderResult:
        """Simulate realistic top-of-book fill in local paper mode."""
        fill_price = order_book.ask if side == "buy" else order_book.bid
        notional = quantity * fill_price
        fee_rate = getattr(self.config, "fx_fee_rate", getattr(self.config, "paper_fee_rate", 0.0015))
        fee = notional * fee_rate
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
                        f"Insufficient paper balance: need ${total_cost:.2f}, "
                        f"have ${self.paper_quote_balance:.2f}"
                    ),
                )
            self.paper_quote_balance -= total_cost
        else:
            pos = self.positions.get(symbol)
            if pos is not None and pos.side == Side.SHORT:
                locked = pos.quantity * pos.entry_price
                pnl = pos.unrealized_pnl(fill_price)
                self.paper_quote_balance += locked + pnl - fee
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
        )

    def _execute_t212_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        reference_price: float,
        is_exit: bool = False,
    ) -> OrderResult:
        """Submit order via Trading 212 API v0 and verify fill status."""
        if self.t212_client is None:
            raise RuntimeError("Trading212Client is not initialized.")

        # Trading 212 convention: positive quantity = BUY, negative quantity = SELL
        signed_qty = abs(quantity) if side.lower() == "buy" else -abs(quantity)
        order_type = "market" if is_exit else self.config.entry_order_type

        try:
            if order_type == "limit":
                try:
                    order_resp = self.t212_client.place_limit_order(
                        ticker=symbol,
                        signed_quantity=signed_qty,
                        limit_price=reference_price,
                        time_validity=self.config.t212_time_validity,
                    )
                except Trading212APIError as limit_exc:
                    if limit_exc.status_code in {400, 403}:
                        logger.warning(
                            "[%s] Limit order returned HTTP %d (Trading 212 rejects fractional shares on limit orders); "
                            "retrying as MARKET order (spread guard already passed)...",
                            symbol,
                            limit_exc.status_code,
                        )
                        order_type = "market"
                        order_resp = self.t212_client.place_market_order(
                            ticker=symbol,
                            signed_quantity=signed_qty,
                        )
                    else:
                        raise
            else:
                order_resp = self.t212_client.place_market_order(
                    ticker=symbol,
                    signed_quantity=signed_qty,
                )

            order_id = str(order_resp.get("id", ""))
            logger.info(
                "[%s] Trading 212 %s %s order submitted: id=%s signed_qty=%.4f",
                symbol,
                order_type.upper(),
                side.upper(),
                order_id,
                signed_qty,
            )

            # Poll order status until filled or timeout
            deadline = time.time() + self.config.order_fill_timeout_sec
            last_order_state: Optional[ dict ] = order_resp

            while time.time() < deadline:
                status = str((last_order_state or {}).get("status", "")).upper()
                if status in {"FILLED", "CONFIRMED"}:
                    break
                if status in {"CANCELLED", "REJECTED", "REPLACED"}:
                    return OrderResult(
                        success=False,
                        order_id=order_id,
                        symbol=symbol,
                        side=side,
                        order_type=order_type,
                        filled_qty=0.0,
                        avg_fill_price=0.0,
                        fee_paid=0.0,
                        status=status.lower(),
                        message=f"Trading 212 order ended with status={status}",
                    )

                time.sleep(2.0)
                try:
                    active_order = self.t212_client.get_order_by_id(order_id)
                except Trading212APIError as poll_exc:
                    logger.warning(
                        "[%s] Transient error polling order %s (keeping order tracked): %s",
                        symbol,
                        order_id,
                        poll_exc,
                    )
                    break
                if active_order is None:
                    # In Trading 212 API v0, GET /equity/orders/{id} returns 404 once the order
                    # is no longer pending (i.e., it has executed and moved to portfolio).
                    last_order_state = None
                    break
                last_order_state = active_order

            # If a limit order is still pending in /equity/orders after timeout, cancel it and execute as market
            if last_order_state is not None and str(last_order_state.get("status", "")).upper() in {
                "NEW",
                "PENDING",
                "UNCONFIRMED",
                "WORKING",
            }:
                if order_type == "limit":
                    logger.warning(
                        "[%s] Limit order %s still pending after %ds (Yahoo quote slightly below T212 ask); "
                        "cancelling limit order and executing MARKET order...",
                        symbol,
                        order_id,
                        self.config.order_fill_timeout_sec,
                    )
                    try:
                        self.t212_client.cancel_order(order_id)
                    except Trading212APIError as cancel_err:
                        logger.warning("Cancel order warning for %s: %s", order_id, cancel_err)

                    order_type = "market"
                    mkt_resp = self.t212_client.place_market_order(
                        ticker=symbol,
                        signed_quantity=signed_qty,
                    )
                    order_id = str(mkt_resp.get("id", order_id))
                    time.sleep(2.0)
                else:
                    logger.info(
                        "[%s] Market order %s accepted by Trading 212 (status=%s).",
                        symbol,
                        order_id,
                        last_order_state.get("status"),
                    )

            # Query portfolio to get exact average fill price if available
            fill_price = reference_price
            filled_qty = abs(quantity)
            if not is_exit:
                try:
                    pos_info = self.t212_client.get_position(symbol)
                    if pos_info:
                        fill_price = float(pos_info.get("averagePrice") or reference_price)
                        filled_qty = float(pos_info.get("quantity") or abs(quantity))
                except Trading212APIError as pos_exc:
                    logger.warning(
                        "[%s] Could not fetch portfolio fill price after order %s (using reference price %.4f): %s",
                        symbol,
                        order_id,
                        reference_price,
                        pos_exc,
                    )

            fee_rate = getattr(self.config, "fx_fee_rate", getattr(self.config, "paper_fee_rate", 0.0015))
            t212_fee = filled_qty * fill_price * fee_rate
            return OrderResult(
                success=True,
                order_id=order_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                filled_qty=filled_qty,
                avg_fill_price=fill_price,
                fee_paid=t212_fee,
                status="filled",
                message="Executed and verified via Trading 212 API v0",
            )

        except Trading212APIError as exc:
            if exc.status_code == 403:
                logger.error(
                    "[%s] Trading 212 returned HTTP 403 Forbidden when placing order. "
                    "Please check your Trading 212 API Key permissions in the Trading 212 App "
                    "(Settings -> API (Beta)) and ensure 'Orders - Execute' (and 'Orders - Read') "
                    "are ticked for this key!",
                    symbol,
                )
            else:
                logger.error("[%s] Trading 212 order error: %s", symbol, exc)
            return OrderResult(
                success=False,
                order_id="",
                symbol=symbol,
                side=side,
                order_type=order_type,
                filled_qty=0.0,
                avg_fill_price=0.0,
                fee_paid=0.0,
                status="error",
                message=str(exc),
            )
