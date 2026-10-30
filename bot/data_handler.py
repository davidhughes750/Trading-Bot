"""Data acquisition and technical indicator module for Trading 212 Equities.

Because Trading 212's Public API v0 (`/api/v0/equity/...`) is an account and
order-execution API that does not expose historical OHLCV candle bars, this
module:
1. Maps Trading 212 instrument tickers (e.g., `AAPL_US_EQ`, `NVDA_US_EQ`,
   `VUAG_UK_EQ`) to standard market feed tickers (`AAPL`, `NVDA`, `VUAG.L`).
2. Fetches historical closed OHLCV bars and real-time bid/ask top-of-book
   snapshots via Yahoo Finance (`yfinance`), cross-referenced with Trading 212
   portfolio prices when available.
3. Computes vectorized 20 EMA, 50 EMA, 14 RSI (Wilder's), and 14 ATR (Wilder's).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from bot.config import Config
from bot.models import OrderBookSnapshot
from bot.t212_client import Trading212Client

logger = logging.getLogger(__name__)


TIMEFRAME_SECONDS = {
    "1m": 60,
    "2m": 120,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "60m": 3600,
    "1h": 3600,
    "1d": 86400,
    "1D": 86400,
}

# Lookback period required by yfinance for intraday vs daily intervals
YFINANCE_PERIOD_BY_TIMEFRAME = {
    "1m": "5d",
    "2m": "10d",
    "5m": "30d",
    "15m": "30d",
    "30m": "60d",
    "60m": "60d",
    "1h": "60d",
    "1d": "2y",
    "1D": "2y",
}


# Trading 212 API v0 uses legacy/pre-merger SPAC instrument IDs for several modern US equities
# even though their shortName in the T212 app is the modern ticker. This table normalizes any
# legacy T212 ticker ('DEAC_US_EQ') or modern ticker ('DKNG_US_EQ') into ('DKNG_US_EQ', 'DKNG'),
# while Trading212Client translates 'DKNG_US_EQ' <-> 'DEAC_US_EQ' at the broker HTTP boundary.
T212_LEGACY_TICKER_MAP = {
    "DEAC_US_EQ": ("DKNG_US_EQ", "DKNG"),
    "FB_US_EQ": ("META_US_EQ", "META"),
    "AAXN_US_EQ": ("AXON_US_EQ", "AXON"),
    "IPOE_US_EQ": ("SOFI_US_EQ", "SOFI"),
    "OAC_US_EQ": ("HIMS_US_EQ", "HIMS"),
    "VACQ_US_EQ": ("RKLB_US_EQ", "RKLB"),
    "NPA_US_EQ": ("ASTS_US_EQ", "ASTS"),
    "IPAX_US_EQ": ("LUNR_US_EQ", "LUNR"),
    "DMYI_US_EQ": ("IONQ_US_EQ", "IONQ"),
    "SNII_US_EQ": ("RGTI_US_EQ", "RGTI"),
    "ALCC1_US_EQ": ("OKLO_US_EQ", "OKLO"),
    # UK 3x Leveraged ETP Sleeve (LSE GBP-denominated / 0% Stamp Duty / 0% FX fee)
    "QQQ3_UK_EQ": ("QQQ3_UK_EQ", "LQQ3.L"),
    "LQQ3l_EQ": ("QQQ3_UK_EQ", "LQQ3.L"),
    "3LUS_UK_EQ": ("3LUS_UK_EQ", "3LUS.L"),
    "3LUS1l_EQ": ("3LUS_UK_EQ", "3LUS.L"),
    "3LSE_UK_EQ": ("3LSE_UK_EQ", "3SMC.L"),
    "3SMCl_EQ": ("3LSE_UK_EQ", "3SMC.L"),
    "3NVD_UK_EQ": ("3NVD_UK_EQ", "3NVD.L"),
    "3NVDl_EQ": ("3NVD_UK_EQ", "3NVD.L"),
    "3TSL_UK_EQ": ("3TSL_UK_EQ", "3TSL.L"),
    "3TSLl_EQ": ("3TSL_UK_EQ", "3TSL.L"),
    "3LGO_UK_EQ": ("3LGO_UK_EQ", "3LGO.L"),
    "3LGO1l_EQ": ("3LGO_UK_EQ", "3LGO.L"),
    "3UKL_UK_EQ": ("3UKL_UK_EQ", "3UKL.L"),
    "3UKLl_EQ": ("3UKL_UK_EQ", "3UKL.L"),
    # UK 3x Inverse / Short ETPs (LSE GBP-denominated Bear Hedge / 0% Stamp Duty / 0% FX fee)
    "QQQS_UK_EQ": ("QQQS_UK_EQ", "LQQS.L"),
    "LQQSl_EQ": ("QQQS_UK_EQ", "LQQS.L"),
    "3USS_UK_EQ": ("3USS_UK_EQ", "3ULS.L"),
    "3ULSl_EQ": ("3USS_UK_EQ", "3ULS.L"),
}

# Yahoo Finance quotes certain London Stock Exchange ETPs in GBp (pence, 1/100th of £1 GBP).
# Dividing by 100.0 normalizes OHLC and live bid/ask/last quotes into GBP (£) so position sizing
# and risk management match the GBP account balance 1:1.
GBX_PENCE_YF_SYMBOLS = {
    "LQQ3.L",
    "3LUS.L",
    "3SMH.L",
    "3NVD.L",
    "3TSL.L",
    "3LGO.L",
    "3UKL.L",
    "LQQS.L",
    "3ULS.L",
}


class DataHandler:
    """Fetches equity OHLCV bars, computes indicators, and retrieves bid/ask spreads."""

    def __init__(
        self,
        config: Config,
        t212_client: Optional[Trading212Client] = None,
    ) -> None:
        self.config = config
        self.t212_client = t212_client

    @staticmethod
    def resolve_ticker_pair(raw_symbol: str) -> Tuple[str, str]:
        """Convert a configured symbol into `(t212_ticker, market_data_symbol)`.

        Examples:
            'AAPL_US_EQ'         -> ('AAPL_US_EQ', 'AAPL')
            'NVDA_US_EQ'         -> ('NVDA_US_EQ', 'NVDA')
            'DEAC_US_EQ'         -> ('DKNG_US_EQ', 'DKNG')
            'VUAG_UK_EQ'         -> ('VUAG_UK_EQ', 'VUAG.L')
            'VUAG_UK_EQ:VUAG.L'  -> ('VUAG_UK_EQ', 'VUAG.L')
            'SPY'                -> ('SPY_US_EQ',  'SPY')
        """
        cleaned = raw_symbol.strip()
        if ":" in cleaned:
            t212_tkr, yf_tkr = cleaned.split(":", 1)
            return t212_tkr.strip(), yf_tkr.strip()

        if cleaned in T212_LEGACY_TICKER_MAP:
            return T212_LEGACY_TICKER_MAP[cleaned]

        if cleaned.endswith("_US_EQ"):
            base = cleaned[: -len("_US_EQ")].replace("_", "-")
            return cleaned, base

        if cleaned.endswith("_UK_EQ"):
            base = cleaned[: -len("_UK_EQ")]
            # Trading 212 sometimes appends 'l' or 'a' to LSE short codes; allow explicit ':TICKER.L' override
            return cleaned, f"{base}.L"

        if cleaned.endswith("_EQ"):
            base = cleaned.split("_")[0]
            return cleaned, base

        # Plain ticker like 'AAPL' -> default to US Equity on Trading 212
        return f"{cleaned}_US_EQ", cleaned

    def timeframe_to_seconds(self, timeframe: Optional[str] = None) -> int:
        tf = timeframe or self.config.timeframe
        if tf not in TIMEFRAME_SECONDS:
            raise ValueError(
                f"Unsupported timeframe '{tf}'. Supported: {sorted(TIMEFRAME_SECONDS.keys())}"
            )
        return TIMEFRAME_SECONDS[tf]

    def download_ohlcv(
        self, symbol: str, period: str, interval: Optional[str] = None, auto_adjust: bool = False
    ) -> pd.DataFrame:
        """Download raw OHLCV bars from Yahoo Finance (GBX normalised to GBP).

        Returns columns `timestamp` (UTC), open, high, low, close, volume. The
        last bar may still be forming; callers decide whether to drop it.
        `auto_adjust=True` returns prices adjusted for dividends and splits
        (total return), which long-horizon research needs.
        """
        import yfinance as yf

        t212_ticker, yf_symbol = self.resolve_ticker_pair(symbol)
        tf = (interval or self.config.timeframe).lower()
        hist = yf.Ticker(yf_symbol).history(period=period, interval=tf, auto_adjust=auto_adjust)

        if hist is None or hist.empty:
            raise RuntimeError(
                f"Empty OHLCV history for Trading 212 ticker {t212_ticker} (market symbol '{yf_symbol}')."
            )

        df = hist.reset_index()
        ts_col = "Datetime" if "Datetime" in df.columns else "Date"
        df["timestamp"] = pd.to_datetime(df[ts_col], utc=True)
        df = df.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)

        if yf_symbol in GBX_PENCE_YF_SYMBOLS:
            for col in ("open", "high", "low", "close"):
                df[col] = df[col] / 100.0
        return df.reset_index(drop=True)

    def fetch_closed_ohlcv(self, symbol: str, limit: Optional[int] = None) -> pd.DataFrame:
        """Fetch recent closed OHLCV bars for a Trading 212 symbol and compute indicators."""
        period = YFINANCE_PERIOD_BY_TIMEFRAME.get(self.config.timeframe, "30d")
        df = self.download_ohlcv(symbol, period=period)

        # Drop any currently forming (unclosed) candle
        tf_sec = self.timeframe_to_seconds()
        now_utc = datetime.now(timezone.utc)
        last_bar_open = df["timestamp"].iloc[-1].to_pydatetime()
        if (now_utc - last_bar_open).total_seconds() < tf_sec:
            df = df.iloc[:-1].copy()

        max_rows = limit or self.config.ohlcv_limit
        if len(df) > max_rows:
            df = df.iloc[-max_rows:].copy()

        df.reset_index(drop=True, inplace=True)
        return self.compute_indicators(df)

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute EMA(20), EMA(50), RSI(14), and ATR(14) on an OHLCV DataFrame."""
        out = df.copy()
        close = out["close"]
        high = out["high"]
        low = out["low"]

        # 1. Fast & Slow Exponential Moving Averages
        out["ema_fast"] = close.ewm(
            span=self.config.ema_fast_period, adjust=False
        ).mean()
        out["ema_slow"] = close.ewm(
            span=self.config.ema_slow_period, adjust=False
        ).mean()

        # 2. Wilder's Relative Strength Index (RSI)
        delta = close.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain = gain.ewm(
            alpha=1.0 / self.config.rsi_period,
            min_periods=self.config.rsi_period,
            adjust=False,
        ).mean()
        avg_loss = loss.ewm(
            alpha=1.0 / self.config.rsi_period,
            min_periods=self.config.rsi_period,
            adjust=False,
        ).mean()
        rs = avg_gain / avg_loss.replace(0.0, np.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi = np.where((avg_loss == 0.0) & (avg_gain > 0.0), 100.0, rsi)
        rsi = np.where((avg_loss == 0.0) & (avg_gain == 0.0), 50.0, rsi)
        out["rsi"] = pd.Series(rsi, index=out.index)

        # 3. Wilder's Average True Range (ATR)
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        out["atr"] = true_range.ewm(
            alpha=1.0 / self.config.atr_period,
            min_periods=self.config.atr_period,
            adjust=False,
        ).mean()

        return out

    def fetch_order_book_snapshot(self, symbol: str) -> OrderBookSnapshot:
        """Fetch live top-of-book bid, ask, and last price for spread & slippage verification."""
        import yfinance as yf

        t212_ticker, yf_symbol = self.resolve_ticker_pair(symbol)
        ticker_obj = yf.Ticker(yf_symbol)

        bid = 0.0
        ask = 0.0
        last = 0.0

        try:
            info = ticker_obj.info or {}
            bid = float(info.get("bid") or 0.0)
            ask = float(info.get("ask") or 0.0)
            last = float(
                info.get("regularMarketPrice")
                or info.get("currentPrice")
                or info.get("previousClose")
                or 0.0
            )
        except Exception as exc:
            logger.debug("yfinance .info fallback for %s: %s", yf_symbol, exc)

        if last <= 0:
            fast = getattr(ticker_obj, "fast_info", None)
            if fast is not None:
                last = float(getattr(fast, "last_price", 0.0) or 0.0)

        if last <= 0:
            raise RuntimeError(f"Unable to retrieve live quote for {t212_ticker} ({yf_symbol}).")

        if yf_symbol in GBX_PENCE_YF_SYMBOLS:
            last = last / 100.0
            if bid > 0:
                bid = bid / 100.0
            if ask > 0:
                ask = ask / 100.0

        # Yahoo bid/ask is often missing or a stale stub (e.g. MSFT bid=$531 / ask=$536 when
        # last=$534.24). When it cannot be trusted, estimate a tight spread around the last
        # price but mark the snapshot as unverified so the risk check and logs say so.
        raw_spread_invalid = (
            bid <= 0
            or ask <= 0
            or ask < bid
            or abs(bid - last) / last > 0.0007
            or abs(ask - last) / last > 0.0007
        )
        if raw_spread_invalid:
            half_tick = max(0.005, last * 0.0002)
            bid = round(last - half_tick, 4)
            ask = round(last + half_tick, 4)

        return OrderBookSnapshot(
            symbol=t212_ticker,
            bid=bid,
            ask=ask,
            last=last,
            timestamp=datetime.now(timezone.utc),
            spread_verified=not raw_spread_invalid,
        )
