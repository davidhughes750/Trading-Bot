"""Currency conversion between instrument prices and the account currency.

US shares are priced in USD and UK ETPs in GBP, but the Trading 212 account
(and therefore equity, cash, risk budget and P&L) is in `config.account_currency`.
Every money amount that is compared with equity or cash must be converted first.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, Optional

from bot.config import Config

logger = logging.getLogger(__name__)


class FxUnavailableError(RuntimeError):
    """Raised when no exchange rate is known for a currency pair."""


def instrument_currency(symbol: str) -> str:
    """Currency a Trading 212 symbol is priced in (after GBX -> GBP normalisation)."""
    sym = str(symbol)
    if sym.endswith("_UK_EQ") or sym.endswith("l_EQ"):
        return "GBP"
    return "USD"


def _yahoo_rate(base: str, quote: str) -> float:
    """Units of `quote` per 1 unit of `base`, from Yahoo Finance (e.g. GBPUSD=X)."""
    import yfinance as yf

    fast = yf.Ticker(f"{base}{quote}=X").fast_info
    rate = float(getattr(fast, "last_price", 0.0) or 0.0)
    if rate <= 0:
        raise FxUnavailableError(f"Yahoo returned no {base}{quote} rate")
    return rate


class FxConverter:
    """Converts instrument-currency amounts into the account currency.

    Rates are cached for `ttl_sec`. If a refresh fails, the last good rate is
    reused (FX moves slowly relative to a 15-minute strategy). If no rate has
    ever been fetched, `FxUnavailableError` is raised so callers can refuse to
    size a trade rather than guess.
    """

    def __init__(
        self,
        config: Config,
        ttl_sec: float = 600.0,
        rate_source: Optional[Callable[[str, str], float]] = None,
    ) -> None:
        self.account_currency = config.account_currency.upper()
        self.ttl_sec = ttl_sec
        self._rate_source = rate_source or _yahoo_rate
        self._cache: Dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def set_rate(self, from_ccy: str, rate: float) -> None:
        """Pin a rate (account units per 1 unit of `from_ccy`). Used by tests and backtests."""
        with self._lock:
            self._cache[from_ccy.upper()] = (float(rate), float("inf"))

    def rate(self, from_ccy: str) -> float:
        """Account-currency units per 1 unit of `from_ccy`."""
        from_ccy = from_ccy.upper()
        if from_ccy == self.account_currency:
            return 1.0
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(from_ccy)
        if cached and (cached[1] == float("inf") or now - cached[1] < self.ttl_sec):
            return cached[0]
        try:
            # Yahoo quotes e.g. GBPUSD = USD per GBP, so account per USD = 1 / GBPUSD.
            rate = 1.0 / self._rate_source(self.account_currency, from_ccy)
        except Exception as exc:
            if cached:
                logger.warning(
                    "FX refresh %s->%s failed (%s); reusing last rate %.5f",
                    from_ccy, self.account_currency, exc, cached[0],
                )
                return cached[0]
            raise FxUnavailableError(
                f"No {from_ccy}->{self.account_currency} exchange rate available: {exc}"
            ) from exc
        with self._lock:
            self._cache[from_ccy] = (rate, now)
        return rate

    def rate_for_symbol(self, symbol: str) -> float:
        """Account-currency units per 1 unit of the symbol's price currency."""
        return self.rate(instrument_currency(symbol))

    def try_rate_for_symbol(self, symbol: str, fallback: Optional[float] = None) -> Optional[float]:
        try:
            return self.rate_for_symbol(symbol)
        except FxUnavailableError as exc:
            logger.warning("%s", exc)
            return fallback


class FixedFxConverter(FxConverter):
    """Converter with pinned rates and no network access (tests, paper sims, backtests)."""

    def __init__(self, config: Config, rates: Optional[Dict[str, float]] = None) -> None:
        super().__init__(config, rate_source=self._no_source)
        for ccy, rate in (rates or {}).items():
            self.set_rate(ccy, rate)

    @staticmethod
    def _no_source(base: str, quote: str) -> float:
        raise FxUnavailableError(f"No fixed rate configured for {quote}->{base}")
