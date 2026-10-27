"""Configuration management module for Trading 212 Automated Trading Bot.

Loads and validates all environment variables for Trading 212 API credentials
(Demo & Live environments), strategy parameters, and risk management controls.
Never hardcodes secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

try:
    from dotenv import load_dotenv
except ImportError:  # Graceful fallback if python-dotenv is not yet installed
    def load_dotenv(dotenv_path: str | Path | None = None, override: bool = False) -> bool:
        path = Path(dotenv_path) if dotenv_path else Path(".env")
        if not path.is_file():
            return False
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            if override or key not in os.environ:
                os.environ[key] = val
        return True


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_list(value: str | None, default: List[str]) -> List[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Config:
    """Immutable configuration container populated from environment variables."""

    # 1. Target Environment & Trading 212 Credentials
    # 'demo' (T212 Practice API), 'paper' (local sim without API keys), or 'live' (T212 Live API)
    execution_mode: str = "demo"
    live_trading_confirmed: bool = False
    t212_api_key: str = ""
    t212_api_secret: str = ""
    t212_base_url: str = ""
    paper_initial_equity: float = 10_000.0
    paper_fee_rate: float = 0.0015
    fx_fee_rate: float = 0.0015  # 0.15% per trade leg (0.30% round-trip) for T212 FX conversion

    # 2. Strategy Parameters (Trading 212 High-Beta Momentum Equities)
    symbols: List[str] = field(
        default_factory=lambda: [
            "PLTR_US_EQ",
            "COIN_US_EQ",
            "TSLA_US_EQ",
            "AMD_US_EQ",
            "NVDA_US_EQ",
        ]
    )
    timeframe: str = "15m"
    ohlcv_limit: int = 200
    ema_fast_period: int = 20
    ema_slow_period: int = 50
    rsi_period: int = 14
    atr_period: int = 14
    rsi_long_threshold: float = 50.0
    rsi_short_threshold: float = 50.0
    allow_short: bool = False  # Trading 212 Invest / ISA accounts are Long-Only

    # Exit & Trailing Stop Parameters
    take_profit_atr_mult: float = 2.0
    stop_loss_atr_mult: float = 1.5
    trailing_stop_enabled: bool = True
    trailing_stop_activate_r: float = 1.0
    trailing_stop_atr_mult: float = 1.5
    tp_extension_enabled: bool = True
    tp_extension_atr_mult: float = 1.5
    tp_extension_lock_atr: float = 1.0
    tp_extension_max: int = 3
    tp_extension_rsi_max: float = 75.0
    tp_extension_min_rvol: float = 1.0

    # 3. Risk Management & Execution Rules
    risk_per_trade_pct: float = 0.01
    max_open_positions: int = 3
    max_position_exposure_pct: float = 0.33
    max_daily_drawdown_pct: float = 0.05
    max_spread_pct: float = 0.0015
    entry_order_type: str = "limit"  # 'limit' | 'market'
    t212_time_validity: str = "DAY"  # 'DAY' | 'GOOD_TILL_CANCEL'
    fractional_decimals: int = 4
    order_fill_timeout_sec: int = 15

    # 4. Stock Screener & Recommendation Engine
    enable_screener: bool = True
    screener_universe: List[str] = field(default_factory=list)
    enable_uk_etp_sleeve: bool = True
    uk_etp_universe: List[str] = field(
        default_factory=lambda: [
            "QQQ3_UK_EQ",
            "3LUS_UK_EQ",
            "3LSE_UK_EQ",
        ]
    )
    trade_top_recommendation: bool = True
    min_recommendation_score: float = 70.0
    screener_top_n: int = 10
    min_rvol_for_entry: float = 1.0
    max_ema_extension_atr: float = 1.8
    cooldown_minutes_after_loss: int = 120
    market_regime_filter: bool = True
    market_benchmark_symbol: str = "QQQ"
    skip_opening_minutes: int = 15
    require_market_open_for_entries: bool = True
    min_hold_minutes_for_rotation: int = 45

    # 5. AI Portfolio Manager (Gemini LLM + Live News Gatekeeper)
    enable_ai_manager: bool = True
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    ai_slot_rotation_enabled: bool = True
    ai_decisions_file: str = "logs/ai_decisions.json"
    ai_decision_ttl_minutes: int = 60

    # 6. Telegram Mobile Push Notifications & Alerts
    enable_telegram: bool = True
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # 7. Runtime & Logging
    poll_interval_sec: int = 15
    log_level: str = "INFO"
    log_file: str = "logs/trading_bot.log"
    state_file: str = "logs/t212_state.json"

    @property
    def resolved_t212_base_url(self) -> str:
        """Return the active Trading 212 REST API v0 endpoint URL."""
        if self.t212_base_url:
            return self.t212_base_url.rstrip("/")
        if self.execution_mode == "live":
            return "https://live.trading212.com/api/v0"
        return "https://demo.trading212.com/api/v0"

    @classmethod
    def from_env(cls, env_path: str | Path | None = None) -> "Config":
        """Load configuration from `.env` file and process environment variables."""
        if env_path:
            load_dotenv(dotenv_path=env_path, override=False)
        else:
            load_dotenv(override=False)

        raw_mode = os.getenv("EXECUTION_MODE", "demo").strip().lower()
        if raw_mode == "sandbox":
            raw_mode = "demo"

        api_key = (
            os.getenv("T212_API_KEY") or os.getenv("API_KEY") or ""
        ).strip()
        api_secret = (
            os.getenv("T212_API_SECRET") or os.getenv("API_SECRET") or ""
        ).strip()

        fee_rate_env = float(os.getenv("FX_FEE_RATE", os.getenv("PAPER_FEE_RATE", "0.0015")))

        cfg = cls(
            execution_mode=raw_mode,
            live_trading_confirmed=_parse_bool(os.getenv("LIVE_TRADING_CONFIRMED"), False),
            t212_api_key=api_key,
            t212_api_secret=api_secret,
            t212_base_url=os.getenv("T212_BASE_URL", "").strip(),
            paper_initial_equity=float(os.getenv("PAPER_INITIAL_EQUITY", "10000.0")),
            paper_fee_rate=fee_rate_env,
            fx_fee_rate=fee_rate_env,
            symbols=_parse_list(
                os.getenv("SYMBOLS"),
                ["AAPL_US_EQ", "NVDA_US_EQ", "MSFT_US_EQ"],
            ),
            timeframe=os.getenv("TIMEFRAME", "15m").strip(),
            ohlcv_limit=int(os.getenv("OHLCV_LIMIT", "200")),
            ema_fast_period=int(os.getenv("EMA_FAST_PERIOD", "20")),
            ema_slow_period=int(os.getenv("EMA_SLOW_PERIOD", "50")),
            rsi_period=int(os.getenv("RSI_PERIOD", "14")),
            atr_period=int(os.getenv("ATR_PERIOD", "14")),
            rsi_long_threshold=float(os.getenv("RSI_LONG_THRESHOLD", "50.0")),
            rsi_short_threshold=float(os.getenv("RSI_SHORT_THRESHOLD", "50.0")),
            allow_short=_parse_bool(os.getenv("ALLOW_SHORT"), False),
            take_profit_atr_mult=float(os.getenv("TAKE_PROFIT_ATR_MULT", "2.0")),
            stop_loss_atr_mult=float(os.getenv("STOP_LOSS_ATR_MULT", "1.5")),
            trailing_stop_enabled=_parse_bool(os.getenv("TRAILING_STOP_ENABLED"), True),
            trailing_stop_activate_r=float(os.getenv("TRAILING_STOP_ACTIVATE_R", "1.0")),
            trailing_stop_atr_mult=float(os.getenv("TRAILING_STOP_ATR_MULT", "1.5")),
            tp_extension_enabled=_parse_bool(os.getenv("TP_EXTENSION_ENABLED"), True),
            tp_extension_atr_mult=float(os.getenv("TP_EXTENSION_ATR_MULT", "1.5")),
            tp_extension_lock_atr=float(os.getenv("TP_EXTENSION_LOCK_ATR", "1.0")),
            tp_extension_max=int(os.getenv("TP_EXTENSION_MAX", "3")),
            tp_extension_rsi_max=float(os.getenv("TP_EXTENSION_RSI_MAX", "75.0")),
            tp_extension_min_rvol=float(os.getenv("TP_EXTENSION_MIN_RVOL", "1.0")),
            risk_per_trade_pct=float(os.getenv("RISK_PER_TRADE_PCT", "0.015")),
            max_open_positions=int(os.getenv("MAX_OPEN_POSITIONS", "3")),
            max_position_exposure_pct=float(
                os.getenv("MAX_POSITION_EXPOSURE_PCT", "0.33")
            ),
            max_daily_drawdown_pct=float(os.getenv("MAX_DAILY_DRAWDOWN_PCT", "0.05")),
            max_spread_pct=float(os.getenv("MAX_SPREAD_PCT", "0.0015")),
            entry_order_type=os.getenv("ENTRY_ORDER_TYPE", "limit").strip().lower(),
            t212_time_validity=os.getenv("T212_TIME_VALIDITY", "DAY").strip().upper(),
            fractional_decimals=int(os.getenv("FRACTIONAL_DECIMALS", "4")),
            order_fill_timeout_sec=int(os.getenv("ORDER_FILL_TIMEOUT_SEC", "15")),
            enable_screener=_parse_bool(os.getenv("ENABLE_SCREENER"), True),
            screener_universe=_parse_list(os.getenv("SCREENER_UNIVERSE"), []),
            enable_uk_etp_sleeve=_parse_bool(os.getenv("ENABLE_UK_ETP_SLEEVE"), True),
            uk_etp_universe=_parse_list(
                os.getenv("UK_ETP_UNIVERSE"),
                ["QQQ3_UK_EQ", "3LUS_UK_EQ", "3LSE_UK_EQ"],
            ),
            trade_top_recommendation=_parse_bool(
                os.getenv("TRADE_TOP_RECOMMENDATION"), True
            ),
            min_recommendation_score=float(
                os.getenv("MIN_RECOMMENDATION_SCORE", "76.0")
            ),
            screener_top_n=int(os.getenv("SCREENER_TOP_N", "10")),
            min_rvol_for_entry=float(os.getenv("MIN_RVOL_FOR_ENTRY", "1.0")),
            max_ema_extension_atr=float(os.getenv("MAX_EMA_EXTENSION_ATR", "1.6")),
            cooldown_minutes_after_loss=int(
                os.getenv("COOLDOWN_MINUTES_AFTER_LOSS", "120")
            ),
            market_regime_filter=_parse_bool(os.getenv("MARKET_REGIME_FILTER"), True),
            market_benchmark_symbol=os.getenv(
                "MARKET_BENCHMARK_SYMBOL", "QQQ"
            ).strip(),
            skip_opening_minutes=int(os.getenv("SKIP_OPENING_MINUTES", "15")),
            require_market_open_for_entries=_parse_bool(
                os.getenv("REQUIRE_MARKET_OPEN_FOR_ENTRIES"), True
            ),
            min_hold_minutes_for_rotation=int(
                os.getenv("MIN_HOLD_MINUTES_FOR_ROTATION", "45")
            ),
            enable_ai_manager=_parse_bool(os.getenv("ENABLE_AI_MANAGER"), True),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
            ai_slot_rotation_enabled=_parse_bool(
                os.getenv("AI_SLOT_ROTATION_ENABLED"), True
            ),
            ai_decisions_file=os.getenv(
                "AI_DECISIONS_FILE", "logs/ai_decisions.json"
            ).strip(),
            ai_decision_ttl_minutes=int(
                os.getenv("AI_DECISION_TTL_MINUTES", "60")
            ),
            enable_telegram=_parse_bool(os.getenv("ENABLE_TELEGRAM"), True),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            poll_interval_sec=int(os.getenv("POLL_INTERVAL_SEC", "15")),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
            log_file=os.getenv("LOG_FILE", "logs/trading_bot.log").strip(),
            state_file=os.getenv("STATE_FILE", "logs/t212_state.json").strip(),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        """Validate configuration invariants and guard against accidental live execution."""
        if self.execution_mode not in {"paper", "demo", "live"}:
            raise ValueError(
                f"Invalid EXECUTION_MODE '{self.execution_mode}'. Must be 'demo', 'paper', or 'live'."
            )

        if self.execution_mode == "live":
            if not self.live_trading_confirmed:
                raise ValueError(
                    "EXECUTION_MODE='live' requires LIVE_TRADING_CONFIRMED=true in your environment."
                )
            if not self.t212_api_key or "your_" in self.t212_api_key:
                raise ValueError("Valid T212_API_KEY is required for 'live' mode.")
            if self.allow_short:
                raise ValueError(
                    "Trading 212 Invest / ISA Equity API does not support short-selling (set ALLOW_SHORT=false)."
                )

        if self.execution_mode == "demo":
            if not self.t212_api_key or "your_" in self.t212_api_key:
                raise ValueError(
                    "Valid Trading 212 Demo T212_API_KEY is required for EXECUTION_MODE='demo' "
                    "(or set EXECUTION_MODE='paper' to test without a Trading 212 API key)."
                )
            if self.allow_short:
                raise ValueError(
                    "Trading 212 Demo Equity API does not support short-selling (set ALLOW_SHORT=false)."
                )

        if self.ema_fast_period >= self.ema_slow_period:
            raise ValueError(
                f"EMA_FAST_PERIOD ({self.ema_fast_period}) must be strictly less than "
                f"EMA_SLOW_PERIOD ({self.ema_slow_period})."
            )

        min_bars = max(self.ema_slow_period, self.rsi_period, self.atr_period) + 10
        if self.ohlcv_limit < min_bars:
            raise ValueError(
                f"OHLCV_LIMIT ({self.ohlcv_limit}) must be at least {min_bars} to warm up indicators."
            )

        if not (0.0 < self.risk_per_trade_pct <= 0.10):
            raise ValueError(
                f"RISK_PER_TRADE_PCT ({self.risk_per_trade_pct}) must be in (0, 0.10]."
            )

        if not (0.0 < self.max_daily_drawdown_pct <= 0.50):
            raise ValueError(
                f"MAX_DAILY_DRAWDOWN_PCT ({self.max_daily_drawdown_pct}) must be in (0, 0.50]."
            )

        if not (0.0 <= self.fx_fee_rate <= 0.05):
            raise ValueError(
                f"FX_FEE_RATE ({self.fx_fee_rate}) must be in [0.0, 0.05]."
            )

        if not (0.0 < self.max_spread_pct <= 0.05):
            raise ValueError(
                f"MAX_SPREAD_PCT ({self.max_spread_pct}) must be in (0, 0.05]."
            )

        if self.entry_order_type not in {"limit", "market"}:
            raise ValueError("ENTRY_ORDER_TYPE must be either 'limit' or 'market'.")

        if self.t212_time_validity not in {"DAY", "GOOD_TILL_CANCEL", "GTC"}:
            raise ValueError(
                "T212_TIME_VALIDITY must be 'DAY' or 'GOOD_TILL_CANCEL'."
            )
