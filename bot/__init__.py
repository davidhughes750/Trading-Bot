"""Production-grade modular automated trading bot for Trading 212."""

__version__ = "2.6.0"

from bot.config import Config
from bot.data_handler import DataHandler
from bot.models import (
    ExecutionMode,
    OrderBookSnapshot,
    OrderResult,
    Position,
    Side,
    Signal,
    SignalAction,
    StockRecommendation,
    TradePlan,
)
from bot.order_executor import OrderExecutor
from bot.risk_manager import RiskManager
from bot.screener import DEFAULT_T212_UNIVERSE, StockScreener
from bot.strategy_engine import StrategyEngine
from bot.t212_client import Trading212APIError, Trading212Client

__all__ = [
    "__version__",
    "Config",
    "DEFAULT_T212_UNIVERSE",
    "DataHandler",
    "ExecutionMode",
    "OrderBookSnapshot",
    "OrderResult",
    "OrderExecutor",
    "Position",
    "RiskManager",
    "Side",
    "Signal",
    "SignalAction",
    "StockRecommendation",
    "StockScreener",
    "StrategyEngine",
    "TradePlan",
    "Trading212APIError",
    "Trading212Client",
]
