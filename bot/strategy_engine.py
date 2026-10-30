"""Pure strategy calculation engine.

Consumes indicator-enriched OHLCV DataFrames and active position state to emit
unambiguous trading signals ('BUY', 'SELL', 'HOLD') and update trailing stops.
Has zero side effects and zero network calls.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import pandas as pd

from bot.config import Config
from bot.models import Position, Side, Signal, SignalAction

logger = logging.getLogger(__name__)


class StrategyEngine:
    """Stateless, pure calculation module for entry/exit signal generation and trailing stops."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def generate_signal(
        self,
        symbol: str,
        df: pd.DataFrame,
        open_position: Optional[Position] = None,
    ) -> Signal:
        """Evaluate the latest two closed candles and return 'BUY', 'SELL', or 'HOLD'.

        Entry Rules (when flat):
          - LONG ('BUY'):  20 EMA crosses above 50 EMA (prev_fast <= prev_slow and curr_fast > curr_slow)
                           AND RSI > 50
          - SHORT ('SELL'): 20 EMA crosses below 50 EMA (prev_fast >= prev_slow and curr_fast < curr_slow)
                           AND RSI < 50 (only if ALLOW_SHORT=true)

        Opposite-Signal Exit Rules (when in position):
          - If LONG and 20 EMA crosses below 50 EMA -> emit 'SELL' (is_exit=True)
          - If SHORT and 20 EMA crosses above 50 EMA -> emit 'BUY' (is_exit=True)
        """
        required_cols = {"timestamp", "close", "ema_fast", "ema_slow", "rsi", "atr"}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame is missing required indicator columns: {missing}")

        if len(df) < 2:
            raise ValueError("At least 2 closed candles are required to detect crossovers.")

        prev = df.iloc[-2]
        curr = df.iloc[-1]

        ts = curr["timestamp"]
        close_price = float(curr["close"])
        ema_fast = float(curr["ema_fast"])
        ema_slow = float(curr["ema_slow"])
        rsi = float(curr["rsi"])
        atr = float(curr["atr"])

        prev_fast = float(prev["ema_fast"])
        prev_slow = float(prev["ema_slow"])

        if pd.isna(ema_fast) or pd.isna(ema_slow) or pd.isna(rsi) or pd.isna(atr) or atr <= 0:
            return Signal(
                symbol=symbol,
                action=SignalAction.HOLD,
                candle_timestamp=ts,
                close_price=close_price,
                ema_fast=ema_fast,
                ema_slow=ema_slow,
                rsi=rsi,
                atr=atr,
                reason="Indicators warming up or invalid ATR",
            )

        bullish_cross = (prev_fast <= prev_slow) and (ema_fast > ema_slow)
        bearish_cross = (prev_fast >= prev_slow) and (ema_fast < ema_slow)

        # Case 1: Already holding an open position on this symbol -> check for reversal exit
        if open_position is not None:
            if open_position.side == Side.LONG and bearish_cross:
                return Signal(
                    symbol=symbol,
                    action=SignalAction.SELL,
                    candle_timestamp=ts,
                    close_price=close_price,
                    ema_fast=ema_fast,
                    ema_slow=ema_slow,
                    rsi=rsi,
                    atr=atr,
                    reason="Bearish EMA crossover while LONG (reversal exit)",
                    is_exit=True,
                )
            if open_position.side == Side.SHORT and bullish_cross:
                return Signal(
                    symbol=symbol,
                    action=SignalAction.BUY,
                    candle_timestamp=ts,
                    close_price=close_price,
                    ema_fast=ema_fast,
                    ema_slow=ema_slow,
                    rsi=rsi,
                    atr=atr,
                    reason="Bullish EMA crossover while SHORT (reversal exit)",
                    is_exit=True,
                )
            return Signal(
                symbol=symbol,
                action=SignalAction.HOLD,
                candle_timestamp=ts,
                close_price=close_price,
                ema_fast=ema_fast,
                ema_slow=ema_slow,
                rsi=rsi,
                atr=atr,
                reason=f"Holding {open_position.side.value} position; no reversal crossover",
            )

        # Case 2: Flat on this symbol -> evaluate entry conditions
        if bullish_cross and rsi > self.config.rsi_long_threshold:
            return Signal(
                symbol=symbol,
                action=SignalAction.BUY,
                candle_timestamp=ts,
                close_price=close_price,
                ema_fast=ema_fast,
                ema_slow=ema_slow,
                rsi=rsi,
                atr=atr,
                reason=(
                    f"Bullish EMA({self.config.ema_fast_period}/{self.config.ema_slow_period}) "
                    f"crossover + RSI({rsi:.2f}) > {self.config.rsi_long_threshold}"
                ),
                target_side=Side.LONG,
                is_exit=False,
            )

        if (
            bearish_cross
            and rsi < self.config.rsi_short_threshold
            and self.config.allow_short
        ):
            return Signal(
                symbol=symbol,
                action=SignalAction.SELL,
                candle_timestamp=ts,
                close_price=close_price,
                ema_fast=ema_fast,
                ema_slow=ema_slow,
                rsi=rsi,
                atr=atr,
                reason=(
                    f"Bearish EMA({self.config.ema_fast_period}/{self.config.ema_slow_period}) "
                    f"crossover + RSI({rsi:.2f}) < {self.config.rsi_short_threshold}"
                ),
                target_side=Side.SHORT,
                is_exit=False,
            )

        return Signal(
            symbol=symbol,
            action=SignalAction.HOLD,
            candle_timestamp=ts,
            close_price=close_price,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            rsi=rsi,
            atr=atr,
            reason="No qualifying crossover signal",
        )

    def compute_initial_stops(
        self, entry_price: float, atr: float, side: Side
    ) -> Tuple[float, float]:
        """Compute initial stop-loss (1.5x ATR) and profit target (2.0x ATR)."""
        if atr <= 0:
            raise ValueError(f"ATR must be positive, got {atr}")

        sl_dist = self.config.stop_loss_atr_mult * atr
        tp_dist = self.config.take_profit_atr_mult * atr

        if side == Side.LONG:
            stop_loss = entry_price - sl_dist
            take_profit = entry_price + tp_dist
        else:
            stop_loss = entry_price + sl_dist
            take_profit = entry_price - tp_dist

        return stop_loss, take_profit

    def _try_extend_take_profit(
        self,
        position: Position,
        current_price: float,
        atr_ref: float,
        trend_strong: Optional[bool],
    ) -> bool:
        """Extend the take-profit instead of selling when the run is still strong.

        When the target is hit and the latest closed-bar trend is still strong
        (`trend_strong` True), lock in profit by raising the stop to
        `target - tp_extension_lock_atr * ATR` (never lowering it), push the
        target out by `tp_extension_atr_mult * ATR`, and keep holding. If the
        trend flag is unknown/False or the extension cap is reached, return
        False so the caller sells at the target as before.
        """
        if (
            not self.config.tp_extension_enabled
            or not trend_strong
            or position.tp_extensions >= self.config.tp_extension_max
        ):
            return False

        ext = self.config.tp_extension_atr_mult * atr_ref
        lock = self.config.tp_extension_lock_atr * atr_ref
        old_tp = position.take_profit
        if position.side == Side.LONG:
            new_sl = max(position.stop_loss, old_tp - lock)
            position.stop_loss = min(new_sl, current_price - 0.1 * atr_ref)
            position.take_profit = max(old_tp, current_price) + ext
        else:
            new_sl = min(position.stop_loss, old_tp + lock)
            position.stop_loss = max(new_sl, current_price + 0.1 * atr_ref)
            position.take_profit = min(old_tp, current_price) - ext
        position.trailing_active = True
        position.tp_extensions += 1
        logger.info(
            "[%s] Strong trend at target %.4f — take-profit EXTENDED #%d: new target %.4f, "
            "stop locked at %.4f",
            position.symbol,
            old_tp,
            position.tp_extensions,
            position.take_profit,
            position.stop_loss,
        )
        return True

    def _breakeven_floor_price(self, position: Position) -> float:
        """Return the fee-adjusted breakeven floor price for a trailing stop.

        UK GBP ETPs (`_UK_EQ`) trade with 0% FX fee, so their breakeven floor is
        `entry_price`. US equities (`_US_EQ`) incur a round-trip FX fee (`2 * fx_fee_rate`,
        typically 0.30%) plus a 0.05% exit spread cushion (+0.35% total), ensuring a +1R
        winner never closes at a net loss after Trading 212 currency conversion fees.
        """
        if str(position.symbol).endswith("_UK_EQ"):
            fee_cushion_pct = 0.0
        else:
            fx_rate = float(self.config.fx_fee_rate)
            fee_cushion_pct = (2.0 * fx_rate + 0.0005) if fx_rate > 0 else 0.0

        if position.side == Side.LONG:
            return position.entry_price * (1.0 + fee_cushion_pct)
        return position.entry_price * (1.0 - fee_cushion_pct)

    def evaluate_position_exit_and_trail(
        self,
        position: Position,
        current_price: float,
        current_atr: Optional[float] = None,
        is_candle_close: bool = True,
        trend_strong: Optional[bool] = None,
    ) -> Tuple[SignalAction, str]:
        """Update trailing stop if >= 1R in profit and check if SL or TP has been hit.

        Trailing Stop Rule:
          Once unrealized profit reaches >= 1.0R (`trailing_stop_activate_r`),
          trail the stop-loss at `1.5 * ATR` behind the highest price (for LONG)
          or above the lowest price (for SHORT), with a hard floor at the fee-adjusted
          `entry_price` (breakeven + round-trip FX fee cushion) so a +1R winner never
          turns back into a net losing trade.

        Two-Tier Anti-Whipsaw Stop Rule:
          When `is_candle_close=False` (15-second intra-bar polling), take-profits and
          active trailing stops trigger immediately, while initial stop-losses include
          an `INTRABAR_STOP_BUFFER_ATR` (default 0.35) x ATR buffer against brief wicks.
        """
        atr_ref = (
            current_atr
            if (current_atr is not None and current_atr > 0)
            else position.atr_at_entry
        )

        # 1. Update high/low watermarks and ratchet trailing stop if enabled
        if position.side == Side.LONG:
            if current_price > position.highest_price:
                position.highest_price = current_price

            r_mult = position.current_r_multiple(position.highest_price)
            if (
                self.config.trailing_stop_enabled
                and r_mult >= self.config.trailing_stop_activate_r
            ):
                position.trailing_active = True
                be_floor = self._breakeven_floor_price(position)
                trail_start_r = float(self.config.trailing_stop_start_r)
                if r_mult >= trail_start_r:
                    candidate_sl = max(
                        be_floor,
                        position.highest_price - self.config.trailing_stop_atr_mult * atr_ref,
                    )
                else:
                    candidate_sl = be_floor
                if candidate_sl > position.stop_loss:
                    logger.info(
                        "[%s] Trailing stop ratcheted UP: %.4f -> %.4f (high=%.4f, R=%.2f)",
                        position.symbol,
                        position.stop_loss,
                        candidate_sl,
                        position.highest_price,
                        r_mult,
                    )
                    position.stop_loss = candidate_sl

            # Check Stop-Loss & Take-Profit triggers
            effective_sl = (
                position.stop_loss
                if (is_candle_close or position.trailing_active)
                else (position.stop_loss - self.config.intrabar_stop_buffer_atr * atr_ref)
            )
            if current_price <= effective_sl:
                kind = "Trailing Stop-Loss" if position.trailing_active else "Stop-Loss"
                return (
                    SignalAction.SELL,
                    f"{kind} hit at {current_price:.4f} (stop={position.stop_loss:.4f})",
                )
            if current_price >= position.take_profit:
                if self._try_extend_take_profit(position, current_price, atr_ref, trend_strong):
                    return SignalAction.HOLD, "Take-profit extended (strong trend)"
                return (
                    SignalAction.SELL,
                    f"Take-Profit hit at {current_price:.4f} (target={position.take_profit:.4f})",
                )

        else:  # Side.SHORT
            if current_price < position.lowest_price:
                position.lowest_price = current_price

            r_mult = position.current_r_multiple(position.lowest_price)
            if (
                self.config.trailing_stop_enabled
                and r_mult >= self.config.trailing_stop_activate_r
            ):
                position.trailing_active = True
                be_floor = self._breakeven_floor_price(position)
                trail_start_r = float(self.config.trailing_stop_start_r)
                if r_mult >= trail_start_r:
                    candidate_sl = min(
                        be_floor,
                        position.lowest_price + self.config.trailing_stop_atr_mult * atr_ref,
                    )
                else:
                    candidate_sl = be_floor
                if candidate_sl < position.stop_loss:
                    logger.info(
                        "[%s] Trailing stop ratcheted DOWN: %.4f -> %.4f (low=%.4f, R=%.2f)",
                        position.symbol,
                        position.stop_loss,
                        candidate_sl,
                        position.lowest_price,
                        r_mult,
                    )
                    position.stop_loss = candidate_sl

            effective_sl = (
                position.stop_loss
                if (is_candle_close or position.trailing_active)
                else (position.stop_loss + self.config.intrabar_stop_buffer_atr * atr_ref)
            )
            if current_price >= effective_sl:
                kind = "Trailing Stop-Loss" if position.trailing_active else "Stop-Loss"
                return (
                    SignalAction.BUY,
                    f"{kind} hit at {current_price:.4f} (stop={position.stop_loss:.4f})",
                )
            if current_price <= position.take_profit:
                if self._try_extend_take_profit(position, current_price, atr_ref, trend_strong):
                    return SignalAction.HOLD, "Take-profit extended (strong trend)"
                return (
                    SignalAction.BUY,
                    f"Take-Profit hit at {current_price:.4f} (target={position.take_profit:.4f})",
                )

        return SignalAction.HOLD, "Within stop/target bounds"


def classify_market_regime(bar: "pd.Series", base_min_score: float, bench: str = "QQQ") -> Tuple[str, str, float]:
    """Classify the market from the benchmark's latest closed bar.

    Returns `(state, summary, min_entry_score)`:
      BULLISH  close > EMA20 >= EMA50 and RSI >= 50 -> base threshold
      CAUTIOUS close >= EMA50 or RSI >= 46         -> at least 80
      BEARISH  otherwise                            -> at least 86
    Shared by the live bot and the backtester so both apply identical rules.
    """
    close_p = float(bar["close"])
    ema20 = float(bar["ema_fast"])
    ema50 = float(bar["ema_slow"])
    rsi = float(bar["rsi"])

    if close_p > ema20 and ema20 >= ema50 and rsi >= 50.0:
        summary = f"BULLISH ({bench} {close_p:.2f} > EMA20 {ema20:.2f} > EMA50 {ema50:.2f}, RSI {rsi:.1f})"
        return "BULLISH", summary, base_min_score
    if close_p >= ema50 or rsi >= 46.0:
        cautious_min = max(base_min_score, 80.0)
        summary = (
            f"CAUTIOUS / MIXED ({bench} {close_p:.2f}, EMA20 {ema20:.2f}, EMA50 {ema50:.2f}, "
            f"RSI {rsi:.1f} -> requiring score >= {cautious_min:.0f})"
        )
        return "CAUTIOUS", summary, cautious_min
    bearish_min = max(base_min_score, 86.0)
    summary = (
        f"BEARISH RISK-OFF ({bench} {close_p:.2f} < EMA20 {ema20:.2f} < EMA50 {ema50:.2f}, "
        f"RSI {rsi:.1f} -> only scores >= {bearish_min:.0f} allowed)"
    )
    return "BEARISH", summary, bearish_min
