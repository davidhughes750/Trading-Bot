"""Domain models and value objects for the Trading 212 automated trading system."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ExecutionMode(str, Enum):
    PAPER = "paper"  # Local simulation (no T212 API key required)
    DEMO = "demo"    # Trading 212 Practice / Paper Trading API (https://demo.trading212.com/api/v0)
    LIVE = "live"    # Trading 212 Real Money API (https://live.trading212.com/api/v0)


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class OrderBookSnapshot:
    """Top-of-book quote snapshot with computed bid-ask spread."""

    symbol: str
    bid: float
    ask: float
    last: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # False when the quote source gave no usable bid/ask and the spread was estimated.
    spread_verified: bool = True

    @property
    def mid_price(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread_abs(self) -> float:
        return max(0.0, self.ask - self.bid)

    @property
    def spread_pct(self) -> float:
        mid = self.mid_price
        if mid <= 0:
            return float("inf")
        return self.spread_abs / mid


@dataclass(frozen=True)
class Signal:
    """Unambiguous output from StrategyEngine."""

    symbol: str
    action: SignalAction  # 'BUY', 'SELL', or 'HOLD'
    candle_timestamp: Any
    close_price: float
    ema_fast: float
    ema_slow: float
    rsi: float
    atr: float
    reason: str
    target_side: Optional[Side] = None
    is_exit: bool = False


@dataclass
class Position:
    """Represents an active open position with dynamic stop-loss and take-profit levels."""

    symbol: str
    side: Side
    quantity: float
    entry_price: float
    initial_stop_loss: float
    stop_loss: float
    take_profit: float
    atr_at_entry: float
    entry_order_id: str
    opened_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    highest_price: float = 0.0
    lowest_price: float = 0.0
    trailing_active: bool = False
    tp_extensions: int = 0  # Number of times the take-profit was extended on a strong run
    entry_fee_paid: float = 0.0  # Currency conversion / execution fee paid on entry
    price_history: List[Dict[str, Any]] = field(default_factory=list)  # Trade journey points [{'ts': ..., 'price': ...}]
    entry_context: Dict[str, Any] = field(default_factory=dict)  # Screener score, AI decision & regime at entry (for the trade journal)
    # Account-currency units per 1 unit of the price currency at entry (e.g. GBP per USD).
    # 0.0 means unknown (positions saved before FX tracking); filled in on load.
    fx_rate_at_entry: float = 0.0
    entry_reference_price: float = 0.0  # Quote the entry was sized on (for slippage stats)
    entry_price_source: str = ""  # 'broker_fill' | 'broker_avg' | 'estimated'
    backup_stop_order_id: str = ""  # Broker-side backup stop order, if one is working

    def __post_init__(self) -> None:
        if self.highest_price <= 0.0:
            self.highest_price = self.entry_price
        if self.lowest_price <= 0.0:
            self.lowest_price = self.entry_price
        if not self.price_history and self.entry_price > 0.0:
            self.price_history = [
                {"ts": self.opened_at, "price": round(float(self.entry_price), 4)}
            ]

    def record_price_point(
        self,
        price: float,
        ts: Optional[str] = None,
        min_interval_sec: int = 180,
        max_points: int = 120,
    ) -> bool:
        """Record a price waypoint along the position's open journey.

        Returns True if a new waypoint was appended so the caller can persist state.
        """
        if price <= 0.0:
            return False
        now_dt = datetime.now(timezone.utc)
        ts_iso = ts or now_dt.isoformat()
        rounded = round(float(price), 4)

        if not self.price_history:
            self.price_history = [
                {"ts": self.opened_at, "price": round(float(self.entry_price), 4)}
            ]

        last_pt = self.price_history[-1]
        last_price = float(last_pt.get("price") or self.entry_price)
        pct_change = abs(rounded - last_price) / max(last_price, 0.0001)

        elapsed_sec = float(min_interval_sec)
        last_ts_str = str(last_pt.get("ts") or "")
        if last_ts_str:
            try:
                last_dt = datetime.fromisoformat(last_ts_str.replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                elapsed_sec = max(0.0, (now_dt - last_dt).total_seconds())
            except Exception:
                elapsed_sec = float(min_interval_sec)

        is_new_extreme = (rounded > self.highest_price) or (rounded < self.lowest_price)
        if (
            len(self.price_history) < 2
            or elapsed_sec >= min_interval_sec
            or pct_change >= 0.0025
            or is_new_extreme
        ):
            self.price_history.append({"ts": ts_iso, "price": rounded})
            if len(self.price_history) > max_points:
                anchor = self.price_history[0]
                tail = self.price_history[1:]
                step = max(2, len(tail) // (max_points // 2))
                downsampled = [pt for idx, pt in enumerate(tail) if idx % step == 0 or idx == len(tail) - 1]
                self.price_history = [anchor] + downsampled
            return True
        return False

    @property
    def initial_risk_per_unit(self) -> float:
        """1R distance in price units."""
        return abs(self.entry_price - self.initial_stop_loss)

    def current_r_multiple(self, current_price: float) -> float:
        """Return unrealized profit/loss expressed as a multiple of initial risk (R)."""
        one_r = self.initial_risk_per_unit
        if one_r <= 0:
            return 0.0
        if self.side == Side.LONG:
            return (current_price - self.entry_price) / one_r
        return (self.entry_price - current_price) / one_r

    def unrealized_pnl(self, current_price: float) -> float:
        """Unrealised P&L in the instrument's price currency."""
        if self.side == Side.LONG:
            return (current_price - self.entry_price) * self.quantity
        return (self.entry_price - current_price) * self.quantity

    def unrealized_pnl_account(self, current_price: float, fx_now: float) -> float:
        """Unrealised P&L in account currency, including exchange-rate movement."""
        fx_entry = self.fx_rate_at_entry or fx_now
        sign = 1.0 if self.side == Side.LONG else -1.0
        return sign * self.quantity * (current_price * fx_now - self.entry_price * fx_entry)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["side"] = self.side.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Position":
        copy = dict(data)
        copy["side"] = Side(copy["side"])
        valid_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in copy.items() if k in valid_fields}
        return cls(**filtered)


@dataclass(frozen=True)
class TradePlan:
    """Validated trade execution plan approved by RiskManager."""

    symbol: str
    side: Side
    order_side: str  # 'buy' or 'sell'
    quantity: float
    reference_price: float
    stop_loss: float
    take_profit: float
    atr: float
    risk_amount: float  # Account currency
    notional: float  # Account currency
    spread_pct: float
    reason: str
    score: float = 0.0
    rating: str = "STRONG BUY"
    rvol: float = 1.0
    thesis: str = ""
    fx_rate: float = 1.0  # Account-currency units per 1 unit of the price currency
    risk_pct_of_equity: float = 0.0
    spread_verified: bool = True


@dataclass(frozen=True)
class OrderResult:
    """Standardized order execution receipt."""

    success: bool
    order_id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    order_type: str
    filled_qty: float
    avg_fill_price: float
    fee_paid: float
    status: str
    message: str = ""
    # Where avg_fill_price came from: 'broker_fill' (order history), 'broker_avg'
    # (position average price), 'estimated' (quote at order time) or 'simulated'.
    price_source: str = "estimated"
    fees_actual: bool = False  # True if fee_paid came from the broker's fill record
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class StockRecommendation:
    """Quantitative stock screening and recommendation result."""

    symbol: str
    score: float  # 0.0 to 100.0 composite quantitative score
    rating: str   # 'STRONG BUY' | 'BUY' | 'WATCH' | 'HOLD' | 'AVOID'
    actionable: bool
    close_price: float
    ema_fast: float
    ema_slow: float
    rsi: float
    atr: float
    rvol: float
    roc_10_pct: float
    suggested_stop_loss: float
    suggested_take_profit: float
    thesis: str
    signal: Signal
    blocker: str = ""  # Why a high-scoring stock is NOT rated BUY (empty if n/a)
    trend_strong: bool = False  # Trend still intact: eligible for take-profit extension
    sparkline: List[float] = field(default_factory=list)  # Recent close prices for Apple-style sparkline
    candles: List[Dict[str, Any]] = field(default_factory=list)  # Recent 15m OHLCV bars for modal chart


