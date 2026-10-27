"""Domain models and value objects for the Trading 212 automated trading system."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


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

    def __post_init__(self) -> None:
        if self.highest_price <= 0.0:
            self.highest_price = self.entry_price
        if self.lowest_price <= 0.0:
            self.lowest_price = self.entry_price

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
        if self.side == Side.LONG:
            return (current_price - self.entry_price) * self.quantity
        return (self.entry_price - current_price) * self.quantity

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
    risk_amount_usd: float
    notional_usd: float
    spread_pct: float
    reason: str
    score: float = 0.0
    rating: str = "STRONG BUY"
    rvol: float = 1.0
    thesis: str = ""

    @property
    def risk_usd(self) -> float:
        return self.risk_amount_usd

    @property
    def risk_pct_of_equity(self) -> float:
        return (self.risk_amount_usd / max(1.0, self.notional_usd)) * 100.0 if self.notional_usd > 0 else 0.5


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


