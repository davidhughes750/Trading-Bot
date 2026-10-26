"""Risk management and pre-trade validation module.

Enforces:
1. Hard 24-hour drawdown circuit breaker (default: 5% max 24h drawdown).
2. Maximum concurrent open positions limit (default: max 1 open trade).
3. Bid-Ask spread / slippage guard (default: reject if spread > 0.15%).
4. Dynamic 1% equity risk position sizing based on ATR stop-loss distance.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Optional, Tuple

from bot.config import Config
from bot.models import OrderBookSnapshot, Side, Signal, SignalAction, TradePlan
from bot.strategy_engine import StrategyEngine

logger = logging.getLogger(__name__)


class RiskManager:
    """Validates account health, spread conditions, and position sizes before execution."""

    def __init__(self, config: Config, strategy_engine: StrategyEngine) -> None:
        self.config = config
        self.strategy_engine = strategy_engine
        # Rolling 24-hour history of (UTC datetime, total_equity)
        self._equity_history: Deque[Tuple[datetime, float]] = deque()
        self.circuit_breaker_tripped: bool = False
        self.circuit_breaker_reason: str = ""

    def record_equity(
        self, total_equity: float, now: Optional[datetime] = None
    ) -> float:
        """Record current account equity and evaluate the 24-hour drawdown circuit breaker.

        Returns the current 24-hour drawdown fraction (e.g., 0.032 for 3.2%).
        """
        if total_equity <= 0:
            self.circuit_breaker_tripped = True
            self.circuit_breaker_reason = f"Non-positive account equity ({total_equity:.2f})"
            logger.critical("CIRCUIT BREAKER TRIPPED: %s", self.circuit_breaker_reason)
            return 1.0

        ts = now or datetime.now(timezone.utc)
        cutoff = ts - timedelta(hours=24)

        # Prune equity samples older than 24 hours
        while self._equity_history and self._equity_history[0][0] < cutoff:
            self._equity_history.popleft()

        self._equity_history.append((ts, total_equity))

        # Compute drawdown relative to the 24-hour rolling peak (high-water mark)
        peak_24h = max(eq for _, eq in self._equity_history)
        drawdown_pct = max(0.0, (peak_24h - total_equity) / peak_24h) if peak_24h > 0 else 0.0

        if drawdown_pct >= self.config.max_daily_drawdown_pct:
            self.circuit_breaker_tripped = True
            self.circuit_breaker_reason = (
                f"24h drawdown {drawdown_pct * 100:.2f}% breached limit "
                f"{self.config.max_daily_drawdown_pct * 100:.2f}% "
                f"(24h peak={peak_24h:.2f}, current={total_equity:.2f})"
            )
            logger.critical("HARD CIRCUIT BREAKER TRIPPED: %s", self.circuit_breaker_reason)

        return drawdown_pct

    def check_spread_guard(self, order_book: OrderBookSnapshot) -> Tuple[bool, str]:
        """Verify bid-ask spread does not exceed MAX_SPREAD_PCT (e.g., 0.15%)."""
        spread = order_book.spread_pct
        if spread > self.config.max_spread_pct:
            msg = (
                f"[{order_book.symbol}] Spread guard rejected execution: "
                f"spread {spread * 100:.4f}% > max {self.config.max_spread_pct * 100:.4f}% "
                f"(bid={order_book.bid:.4f}, ask={order_book.ask:.4f})"
            )
            logger.warning(msg)
            return False, msg
        return True, "Spread OK"

    def calculate_position_size(
        self,
        total_equity: float,
        available_quote: float,
        entry_price: float,
        stop_loss: float,
        open_positions_count: int = 0,
    ) -> Tuple[float, float]:
        """Calculate position size risking strictly `risk_per_trade_pct` (1%) of total equity.

        Also enforces portfolio diversification when `max_open_positions > 1` so that
        no single trade exceeds `max_position_exposure_pct` (e.g., 20% of equity for 5 slots)
        or starves the remaining open position slots of available free cash.
        """
        if total_equity <= 0 or entry_price <= 0:
            return 0.0, 0.0

        stop_distance = abs(entry_price - stop_loss)
        if stop_distance <= 0:
            raise ValueError("Stop distance must be strictly positive.")

        target_risk_usd = total_equity * self.config.risk_per_trade_pct
        raw_qty = target_risk_usd / stop_distance

        fee_buffer = max(0.002, self.config.paper_fee_rate * 2.5)
        max_deployable_quote = max(0.0, available_quote * (1.0 - fee_buffer))

        if self.config.max_open_positions > 1:
            remaining_slots = max(1, self.config.max_open_positions - open_positions_count)
            slot_cap_by_equity = total_equity * self.config.max_position_exposure_pct
            slot_cap_by_cash = available_quote / remaining_slots
            max_notional_for_trade = min(
                slot_cap_by_equity, slot_cap_by_cash, max_deployable_quote
            )
        else:
            max_notional_for_trade = max_deployable_quote

        max_qty_by_balance = max_notional_for_trade / entry_price
        final_qty = min(raw_qty, max_qty_by_balance)
        actual_risk_usd = final_qty * stop_distance
        return final_qty, actual_risk_usd

    def validate_and_build_trade_plan(
        self,
        signal: Signal,
        order_book: OrderBookSnapshot,
        total_equity: float,
        available_quote: float,
        open_positions_count: int,
        now: Optional[datetime] = None,
    ) -> Optional[TradePlan]:
        """Run all pre-trade risk checks and return a validated TradePlan if approved."""
        # 1. Check 24-hour drawdown circuit breaker
        self.record_equity(total_equity, now=now)
        if self.circuit_breaker_tripped:
            logger.error(
                "[%s] Trade blocked by circuit breaker: %s",
                signal.symbol,
                self.circuit_breaker_reason,
            )
            return None

        # 2. Only process actionable entry signals
        if signal.action == SignalAction.HOLD or signal.is_exit or signal.target_side is None:
            return None

        # 3. Enforce Max Open Positions limit
        if open_positions_count >= self.config.max_open_positions:
            logger.info(
                "[%s] Entry signal (%s) skipped: open positions (%d) >= max_open_positions (%d).",
                signal.symbol,
                signal.action.value,
                open_positions_count,
                self.config.max_open_positions,
            )
            return None

        # 4. Enforce Bid-Ask Spread & Slippage Guard
        spread_ok, _ = self.check_spread_guard(order_book)
        if not spread_ok:
            return None

        # 5. Determine expected execution price and ATR-based Stop-Loss / Take-Profit
        side = signal.target_side
        reference_price = order_book.ask if side == Side.LONG else order_book.bid
        stop_loss, take_profit = self.strategy_engine.compute_initial_stops(
            entry_price=reference_price,
            atr=signal.atr,
            side=side,
        )

        # 6. Dynamic 1% equity risk position sizing + multi-slot diversification cap
        qty, actual_risk_usd = self.calculate_position_size(
            total_equity=total_equity,
            available_quote=available_quote,
            entry_price=reference_price,
            stop_loss=stop_loss,
            open_positions_count=open_positions_count,
        )
        notional_usd = qty * reference_price

        if qty <= 0 or notional_usd < 10.0:
            logger.warning(
                "[%s] Trade rejected: computed quantity=%.8f (notional=$%.2f) is below minimum threshold.",
                signal.symbol,
                qty,
                notional_usd,
            )
            return None

        order_side = "buy" if side == Side.LONG else "sell"
        plan = TradePlan(
            symbol=signal.symbol,
            side=side,
            order_side=order_side,
            quantity=qty,
            reference_price=reference_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr=signal.atr,
            risk_amount_usd=actual_risk_usd,
            notional_usd=notional_usd,
            spread_pct=order_book.spread_pct,
            reason=signal.reason,
        )
        logger.info(
            "[%s] TradePlan APPROVED: %s qty=%.6f @ %.4f | SL=%.4f | TP=%.4f | "
            "Risk=$%.2f (%.2f%% eq) | Spread=%.4f%%",
            plan.symbol,
            plan.side.value,
            plan.quantity,
            plan.reference_price,
            plan.stop_loss,
            plan.take_profit,
            plan.risk_amount_usd,
            (plan.risk_amount_usd / total_equity) * 100.0,
            plan.spread_pct * 100.0,
        )
        return plan
