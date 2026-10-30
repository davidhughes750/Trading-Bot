"""Risk management and pre-trade validation module.

Enforces:
1. 24-hour drawdown circuit breaker (MAX_DAILY_DRAWDOWN_PCT, default 5%).
2. Maximum concurrent open positions (MAX_OPEN_POSITIONS).
3. Bid-ask spread guard (MAX_SPREAD_PCT). Estimated spreads are flagged.
4. Position sizing that risks RISK_PER_TRADE_PCT of equity on the ATR stop,
   converted into the account currency.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Deque, List, Optional, Tuple

from bot.config import Config
from bot.models import OrderBookSnapshot, Side, Signal, SignalAction, TradePlan
from bot.strategy_engine import StrategyEngine
from bot.utils import atomic_write_json

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
        self.circuit_breaker_tripped_at: Optional[datetime] = None
        state_file = config.state_file or "logs/t212_state.json"
        self.risk_state_file: Path = Path(state_file).parent / "risk_state.json"
        self._persist_enabled: bool = (
            config.execution_mode in {"demo", "live"}
            or state_file != "logs/t212_state.json"
        )
        self._last_persist: Optional[datetime] = None
        if self._persist_enabled:
            self._load_risk_state()

    # -------------------------------------------------------------------------
    # Persistence: survive process / systemd restarts without losing the 24h peak
    # -------------------------------------------------------------------------
    def _load_risk_state(self) -> None:
        if not self.risk_state_file.exists():
            return
        try:
            raw = json.loads(self.risk_state_file.read_text(encoding="utf-8"))
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            for ts_str, eq in raw.get("equity_history", []):
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    self._equity_history.append((ts, float(eq)))
            if raw.get("circuit_breaker_tripped"):
                self.circuit_breaker_tripped = True
                self.circuit_breaker_reason = str(raw.get("circuit_breaker_reason", ""))
                tripped_at = raw.get("circuit_breaker_tripped_at")
                self.circuit_breaker_tripped_at = (
                    datetime.fromisoformat(tripped_at) if tripped_at else datetime.now(timezone.utc)
                )
                if self.circuit_breaker_tripped_at.tzinfo is None:
                    self.circuit_breaker_tripped_at = self.circuit_breaker_tripped_at.replace(tzinfo=timezone.utc)
            logger.info(
                "Loaded risk state: %d equity samples, circuit_breaker_tripped=%s",
                len(self._equity_history),
                self.circuit_breaker_tripped,
            )
        except Exception as exc:
            logger.warning("Could not load risk state %s: %s", self.risk_state_file, exc)

    def save_risk_state(self) -> None:
        if not self._persist_enabled:
            return
        try:
            self.risk_state_file.parent.mkdir(parents=True, exist_ok=True)
            # Down-sample to at most one sample per minute to keep the file small
            samples: List[List[Any]] = []
            last_min = None
            for ts, eq in self._equity_history:
                key = ts.strftime("%Y%m%d%H%M")
                if key != last_min:
                    samples.append([ts.isoformat(), round(eq, 4)])
                    last_min = key
            payload = {
                "equity_history": samples,
                "circuit_breaker_tripped": self.circuit_breaker_tripped,
                "circuit_breaker_reason": self.circuit_breaker_reason,
                "circuit_breaker_tripped_at": (
                    self.circuit_breaker_tripped_at.isoformat() if self.circuit_breaker_tripped_at else None
                ),
            }
            atomic_write_json(self.risk_state_file, payload, indent=None)
        except Exception as exc:
            logger.warning("Could not save risk state %s: %s", self.risk_state_file, exc)

    def reset_circuit_breaker(self, reason: str = "manual reset") -> None:
        """Clear the breaker and start a fresh 24h equity baseline."""
        logger.warning("Circuit breaker reset (%s).", reason)
        self.circuit_breaker_tripped = False
        self.circuit_breaker_reason = ""
        self.circuit_breaker_tripped_at = None
        self._equity_history.clear()
        self.save_risk_state()

    def circuit_breaker_resumes_at(self) -> Optional[datetime]:
        if not self.circuit_breaker_tripped or self.circuit_breaker_tripped_at is None:
            return None
        hours = float(self.config.circuit_breaker_cooldown_hours)
        return self.circuit_breaker_tripped_at + timedelta(hours=hours)

    def record_equity(
        self, total_equity: float, now: Optional[datetime] = None
    ) -> float:
        """Record current account equity and evaluate the 24-hour drawdown circuit breaker.

        Returns the current 24-hour drawdown fraction (e.g., 0.032 for 3.2%).
        A tripped breaker stays tripped (across restarts) until its cooldown elapses.
        """
        ts = now or datetime.now(timezone.utc)

        resume_at = self.circuit_breaker_resumes_at()
        if resume_at is not None and ts >= resume_at:
            self.reset_circuit_breaker(reason="cooldown elapsed")

        if total_equity <= 0:
            self.circuit_breaker_tripped = True
            self.circuit_breaker_reason = f"Non-positive account equity ({total_equity:.2f})"
            self.circuit_breaker_tripped_at = self.circuit_breaker_tripped_at or ts
            logger.critical("CIRCUIT BREAKER TRIPPED: %s", self.circuit_breaker_reason)
            self.save_risk_state()
            return 1.0

        cutoff = ts - timedelta(hours=24)

        # Prune equity samples older than 24 hours
        while self._equity_history and self._equity_history[0][0] < cutoff:
            self._equity_history.popleft()

        self._equity_history.append((ts, total_equity))

        # Compute drawdown relative to the 24-hour rolling peak (high-water mark)
        peak_24h = max(eq for _, eq in self._equity_history)
        drawdown_pct = max(0.0, (peak_24h - total_equity) / peak_24h) if peak_24h > 0 else 0.0

        if drawdown_pct >= self.config.max_daily_drawdown_pct and not self.circuit_breaker_tripped:
            self.circuit_breaker_tripped = True
            self.circuit_breaker_tripped_at = ts
            self.circuit_breaker_reason = (
                f"24h drawdown {drawdown_pct * 100:.2f}% breached limit "
                f"{self.config.max_daily_drawdown_pct * 100:.2f}% "
                f"(24h peak={peak_24h:.2f}, current={total_equity:.2f})"
            )
            logger.critical("HARD CIRCUIT BREAKER TRIPPED: %s", self.circuit_breaker_reason)
            self.save_risk_state()
        elif self._last_persist is None or (ts - self._last_persist).total_seconds() >= 60:
            self.save_risk_state()
            self._last_persist = ts

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
        fx_rate: float = 1.0,
    ) -> Tuple[float, float]:
        """Return `(quantity, risk_in_account_currency)` risking `risk_per_trade_pct` of equity.

        `total_equity` and `available_quote` are in account currency; `entry_price`
        and `stop_loss` are in the instrument's price currency. `fx_rate` converts
        one unit of price currency into account currency (e.g. GBP per USD).

        The size is also capped so no single trade exceeds `max_position_exposure_pct`
        of equity or takes more than its share of free cash across the open slots.
        """
        if total_equity <= 0 or entry_price <= 0 or fx_rate <= 0:
            return 0.0, 0.0

        stop_distance = abs(entry_price - stop_loss)
        if stop_distance <= 0:
            raise ValueError("Stop distance must be strictly positive.")

        stop_distance_acct = stop_distance * fx_rate
        price_acct = entry_price * fx_rate

        target_risk = total_equity * self.config.risk_per_trade_pct
        raw_qty = target_risk / stop_distance_acct

        fee_buffer = max(0.002, self.config.fx_fee_rate * 2.5)
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

        max_qty_by_balance = max_notional_for_trade / price_acct
        final_qty = min(raw_qty, max_qty_by_balance)
        actual_risk = final_qty * stop_distance_acct
        return final_qty, actual_risk

    def validate_and_build_trade_plan(
        self,
        signal: Signal,
        order_book: OrderBookSnapshot,
        total_equity: float,
        available_quote: float,
        open_positions_count: int,
        now: Optional[datetime] = None,
        fx_rate: float = 1.0,
    ) -> Optional[TradePlan]:
        """Run all pre-trade risk checks and return a validated TradePlan if approved.

        `total_equity` and `available_quote` are in account currency; `fx_rate`
        converts the instrument's price currency into account currency.
        """
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
        if not order_book.spread_verified:
            if self.config.require_verified_spread:
                logger.warning(
                    "[%s] Trade rejected: no usable bid/ask quote, spread could not be verified.",
                    signal.symbol,
                )
                return None
            logger.info(
                "[%s] Spread NOT verified (no usable bid/ask quote; using an estimate). "
                "Actual slippage is recorded in the trade journal.",
                signal.symbol,
            )

        # 5. Determine expected execution price and ATR-based Stop-Loss / Take-Profit
        side = signal.target_side
        reference_price = order_book.ask if side == Side.LONG else order_book.bid
        stop_loss, take_profit = self.strategy_engine.compute_initial_stops(
            entry_price=reference_price,
            atr=signal.atr,
            side=side,
        )

        # 6. Equity-risk position sizing + multi-slot diversification cap (account currency)
        qty, actual_risk = self.calculate_position_size(
            total_equity=total_equity,
            available_quote=available_quote,
            entry_price=reference_price,
            stop_loss=stop_loss,
            open_positions_count=open_positions_count,
            fx_rate=fx_rate,
        )
        notional = qty * reference_price * fx_rate

        if qty <= 0 or notional < 10.0:
            logger.warning(
                "[%s] Trade rejected: computed quantity=%.8f (notional=%.2f %s) is below the 10.00 minimum.",
                signal.symbol,
                qty,
                notional,
                self.config.account_currency,
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
            risk_amount=actual_risk,
            notional=notional,
            spread_pct=order_book.spread_pct,
            reason=signal.reason,
            fx_rate=fx_rate,
            risk_pct_of_equity=(actual_risk / total_equity) * 100.0,
            spread_verified=order_book.spread_verified,
        )
        logger.info(
            "[%s] TradePlan APPROVED: %s qty=%.6f @ %.4f | SL=%.4f | TP=%.4f | "
            "Risk=%.2f %s (%.2f%% eq) | Spread=%.4f%%%s",
            plan.symbol,
            plan.side.value,
            plan.quantity,
            plan.reference_price,
            plan.stop_loss,
            plan.take_profit,
            plan.risk_amount,
            self.config.account_currency,
            plan.risk_pct_of_equity,
            plan.spread_pct * 100.0,
            "" if plan.spread_verified else " (estimated)",
        )
        return plan


# UK 3x inverse ETPs that profit when US indices fall
INVERSE_ETP_SYMBOLS = frozenset({"QQQS_UK_EQ", "3USS_UK_EQ"})


def required_min_score(config: Config, symbol: str, regime_state: str, effective_min_score: float) -> float:
    """Regime-adjusted minimum screener score for an entry in `symbol`.

    Long equities/ETPs use `effective_min_score` (raised to 80 in CAUTIOUS and 86 in
    BEARISH regimes). Inverse ETPs profit in downturns, so they use the base threshold
    in BEARISH/CAUTIOUS markets and need >= 80 in a BULLISH one.
    """
    base = float(config.min_recommendation_score)
    if str(symbol) in INVERSE_ETP_SYMBOLS:
        return base if regime_state in {"BEARISH", "CAUTIOUS"} else max(base, 80.0)
    return effective_min_score


def has_open_slot(config: Config, symbol: str, held_symbols: List[str]) -> bool:
    """True if total capacity and the symbol's regional sleeve (US / UK) both have room."""
    if len(held_symbols) >= config.max_open_positions:
        return False
    is_uk = str(symbol).endswith("_UK_EQ")
    same_sleeve = sum(1 for s in held_symbols if str(s).endswith("_UK_EQ") == is_uk)
    cap = config.max_uk_positions if is_uk else config.max_us_positions
    return same_sleeve < min(config.max_open_positions, cap)
