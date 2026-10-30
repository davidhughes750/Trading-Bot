"""Trading 212 Public REST API (v0) client.

Supports both Trading 212 environments:
- Demo (Practice / Paper Trading): https://demo.trading212.com/api/v0
- Live (Real Money Invest / ISA) : https://live.trading212.com/api/v0

Key Trading 212 API v0 specifications handled here:
- Authentication via HTTP Basic Auth (`base64(API_KEY:API_SECRET)`) or direct
  `Authorization: <API_KEY>` header depending on whether a secret is supplied.
- Buy vs Sell convention: Positive `quantity` (> 0) for BUY orders;
  Negative `quantity` (< 0) for SELL orders.
- Per-endpoint rate-limit throttling and automatic HTTP 429 retry using
  Trading 212's `x-ratelimit-reset` header.
"""

from __future__ import annotations

import base64
import logging
import math
import time
from typing import Any, Dict, List, Optional

import requests

from bot.config import Config

logger = logging.getLogger(__name__)


class Trading212APIError(RuntimeError):
    """Raised when Trading 212 API returns a non-retryable error response."""

    def __init__(self, status_code: int, message: str, payload: Any = None) -> None:
        super().__init__(f"Trading 212 API Error [{status_code}]: {message}")
        self.status_code = status_code
        self.payload = payload


class Trading212Client:
    """Thread-safe HTTP client for Trading 212 Equity API v0."""

    DEMO_BASE_URL = "https://demo.trading212.com/api/v0"
    LIVE_BASE_URL = "https://live.trading212.com/api/v0"

    # Minimum spacing (seconds) between calls to respect T212 rate limits
    # (/equity/account/cash and /equity/portfolio allow 1 req per 5s; orders allow 50/min)
    ENDPOINT_MIN_INTERVALS: Dict[str, float] = {
        "/equity/account/cash": 5.2,
        "/equity/account/summary": 5.2,
        "/equity/portfolio": 5.2,
        "/equity/orders": 5.2,
        "/equity/orders/market": 1.3,
        "/equity/orders/limit": 1.3,
        "/equity/orders/stop": 1.3,
        "/equity/metadata/instruments": 50.0,
    }

    # Trading 212 API v0 uses legacy/pre-merger SPAC instrument IDs for several modern US equities
    # and internal LSE ticker IDs for UK 3x Leveraged ETPs. We translate transparently at the HTTP
    # boundary so the rest of the bot and dashboard use clean modern tickers.
    MODERN_TO_T212_API_TICKER: Dict[str, str] = {
        "DKNG_US_EQ": "DEAC_US_EQ",
        "META_US_EQ": "FB_US_EQ",
        "AXON_US_EQ": "AAXN_US_EQ",
        "SOFI_US_EQ": "IPOE_US_EQ",
        "HIMS_US_EQ": "OAC_US_EQ",
        "RKLB_US_EQ": "VACQ_US_EQ",
        "ASTS_US_EQ": "NPA_US_EQ",
        "LUNR_US_EQ": "IPAX_US_EQ",
        "IONQ_US_EQ": "DMYI_US_EQ",
        "RGTI_US_EQ": "SNII_US_EQ",
        "OKLO_US_EQ": "ALCC1_US_EQ",
        # UK 3x Leveraged ETPs (LSE GBP-native lines — 0% Stamp Duty, 0% FX fee)
        "QQQ3_UK_EQ": "LQQ3l_EQ",
        "3LUS_UK_EQ": "3LUS1l_EQ",
        "3LSE_UK_EQ": "3SMCl_EQ",
        "3NVD_UK_EQ": "3NVDl_EQ",
        "3TSL_UK_EQ": "3TSLl_EQ",
        "3LGO_UK_EQ": "3LGO1l_EQ",
        "3UKL_UK_EQ": "3UKLl_EQ",
        # UK 3x Inverse / Short ETPs (LSE GBP-denominated / 0% Stamp Duty / 0% FX fee)
        "QQQS_UK_EQ": "LQQSl_EQ",
        "3USS_UK_EQ": "3ULSl_EQ",
    }
    T212_API_TO_MODERN_TICKER: Dict[str, str] = {
        v: k for k, v in MODERN_TO_T212_API_TICKER.items()
    }

    # LSE instruments quoted in GBX (pence, 1/100th of £1 GBP) on Trading 212 API.
    # Normalized to GBP (£) at the client boundary so position sizing and P&L remain 1:1 with GBP cash.
    GBX_DENOMINATED_T212_TICKERS = {
        "LQQ3l_EQ",
        "3LUS1l_EQ",
        "3SMHl_EQ",
        "3NVDl_EQ",
        "3TSLl_EQ",
        "3LGO1l_EQ",
        "3UKLl_EQ",
        "LQQSl_EQ",
        "3ULSl_EQ",
    }

    @classmethod
    def to_broker_ticker(cls, ticker: str) -> str:
        """Translate a modern bot ticker (e.g. 'DKNG_US_EQ') to T212's internal API ticker ('DEAC_US_EQ')."""
        return cls.MODERN_TO_T212_API_TICKER.get(ticker, ticker)

    @classmethod
    def from_broker_ticker(cls, ticker: str) -> str:
        """Translate T212's internal API ticker ('DEAC_US_EQ') back to the modern bot ticker ('DKNG_US_EQ')."""
        return cls.T212_API_TO_MODERN_TICKER.get(ticker, ticker)

    def __init__(
        self,
        config: Config,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.config = config
        self.base_url = config.resolved_t212_base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers.update(self._build_auth_headers())
        self._last_call_ts: Dict[str, float] = {}
        # Learned max quantity decimals per ticker (from precision-mismatch errors)
        self._qty_decimals: Dict[str, int] = {}

    def _build_auth_headers(self) -> Dict[str, str]:
        """Construct Trading 212 Authorization header (Basic Auth if secret provided, else raw key)."""
        key = self.config.t212_api_key
        secret = self.config.t212_api_secret

        if key and secret and "your_" not in secret:
            raw_pair = f"{key}:{secret}".encode("utf-8")
            encoded = base64.b64encode(raw_pair).decode("ascii")
            auth_val = f"Basic {encoded}"
        else:
            auth_val = key

        return {
            "Authorization": auth_val,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # -------------------------------------------------------------------------
    # Account & Portfolio Endpoints
    # -------------------------------------------------------------------------
    def get_account_cash(self) -> Dict[str, Any]:
        """GET /equity/account/cash

        Returns:
            dict with keys: 'free', 'total', 'invested', 'ppl', 'result', 'blocked'
        """
        return self._request("GET", "/equity/account/cash")

    def get_portfolio(self) -> List[Dict[str, Any]]:
        """GET /equity/portfolio

        Returns:
            List of open position objects, each containing:
            'ticker', 'quantity', 'averagePrice', 'currentPrice', 'ppl', 'fxPpl'
        """
        data = self._request("GET", "/equity/portfolio")
        if not isinstance(data, list):
            return []
        out: List[Dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict) and item.get("ticker"):
                item = dict(item)
                raw_tkr = str(item["ticker"])
                if raw_tkr in self.GBX_DENOMINATED_T212_TICKERS:
                    if item.get("averagePrice") is not None:
                        item["averagePrice"] = float(item["averagePrice"]) / 100.0
                    if item.get("currentPrice") is not None:
                        item["currentPrice"] = float(item["currentPrice"]) / 100.0
                item["ticker"] = self.from_broker_ticker(raw_tkr)
            out.append(item)
        return out

    def get_position(self, ticker: str) -> Optional[Dict[str, Any]]:
        """GET /equity/portfolio/{ticker}

        Returns position dict if open, or None if 404 (no position).
        """
        broker_ticker = self.to_broker_ticker(ticker)
        try:
            res = self._request(
                "GET",
                f"/equity/portfolio/{broker_ticker}",
                rate_key="/equity/portfolio",
            )
            if isinstance(res, dict) and res.get("ticker"):
                res = dict(res)
                raw_tkr = str(res["ticker"])
                if raw_tkr in self.GBX_DENOMINATED_T212_TICKERS:
                    if res.get("averagePrice") is not None:
                        res["averagePrice"] = float(res["averagePrice"]) / 100.0
                    if res.get("currentPrice") is not None:
                        res["currentPrice"] = float(res["currentPrice"]) / 100.0
                res["ticker"] = self.from_broker_ticker(raw_tkr)
            return res
        except Trading212APIError as exc:
            if exc.status_code == 404:
                return None
            raise

    def get_instruments(self) -> List[Dict[str, Any]]:
        """GET /equity/metadata/instruments"""
        data = self._request("GET", "/equity/metadata/instruments")
        return list(data) if isinstance(data, list) else []

    # -------------------------------------------------------------------------
    # Order Management Endpoints
    # -------------------------------------------------------------------------
    def get_orders(self) -> List[Dict[str, Any]]:
        """GET /equity/orders - Fetch all currently pending/active orders."""
        data = self._request("GET", "/equity/orders")
        if not isinstance(data, list):
            return []
        out: List[Dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict) and item.get("ticker"):
                item = dict(item)
                item["ticker"] = self.from_broker_ticker(str(item["ticker"]))
            out.append(item)
        return out

    def get_order_by_id(self, order_id: str | int) -> Optional[Dict[str, Any]]:
        """GET /equity/orders/{id} - Returns None if order is no longer pending (404)."""
        try:
            return self._request(
                "GET",
                f"/equity/orders/{order_id}",
                rate_key="/equity/orders",
            )
        except Trading212APIError as exc:
            if exc.status_code == 404:
                # In Trading 212 API v0, once an order fills or is cancelled,
                # GET /equity/orders/{id} returns 404 because /equity/orders only holds active orders.
                return None
            raise

    def place_market_order(self, ticker: str, signed_quantity: float) -> Dict[str, Any]:
        """POST /equity/orders/market

        Args:
            ticker: Trading 212 instrument ticker (e.g. 'AAPL_US_EQ').
            signed_quantity: Positive (> 0) to BUY, Negative (< 0) to SELL.

        Some instruments accept fewer decimal places than `fractional_decimals`
        (Trading 212 replies `quantity-precision-mismatch`). In that case the
        quantity is truncated (never rounded up) one decimal at a time until
        accepted, and the working precision is remembered per ticker.
        """
        qty = round(float(signed_quantity), self.config.fractional_decimals)
        if qty == 0:
            raise ValueError("Order quantity cannot be zero.")

        broker_ticker = self.to_broker_ticker(ticker)
        decimals = min(
            self._qty_decimals.get(broker_ticker, self.config.fractional_decimals),
            self.config.fractional_decimals,
        )
        sign = 1.0 if qty > 0 else -1.0

        while True:
            send_qty = sign * math.floor(abs(float(signed_quantity)) * 10**decimals + 1e-9) / 10**decimals
            if send_qty == 0:
                raise ValueError(
                    f"Order quantity for {broker_ticker} rounds to zero at {decimals} decimals."
                )
            payload = {
                "ticker": broker_ticker,
                "quantity": round(send_qty, decimals),
            }
            logger.info("T212 POST /equity/orders/market | payload=%s", payload)
            try:
                resp = self._request("POST", "/equity/orders/market", json_body=payload)
            except Trading212APIError as exc:
                if (
                    exc.status_code == 400
                    and "precision" in str(exc).lower()
                    and decimals > 0
                ):
                    decimals -= 1
                    logger.warning(
                        "[%s] Quantity precision rejected; retrying with %d decimal place(s).",
                        broker_ticker,
                        decimals,
                    )
                    continue
                raise
            self._qty_decimals[broker_ticker] = decimals
            return resp

    def place_limit_order(
        self,
        ticker: str,
        signed_quantity: float,
        limit_price: float,
        time_validity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /equity/orders/limit

        Args:
            ticker: Trading 212 instrument ticker (e.g. 'AAPL_US_EQ').
            signed_quantity: Positive (> 0) to BUY, Negative (< 0) to SELL.
            limit_price: Limit execution price.
            time_validity: 'DAY' or 'GOOD_TILL_CANCEL' (defaults to config.t212_time_validity).
        """
        qty = round(float(signed_quantity), self.config.fractional_decimals)
        if qty == 0:
            raise ValueError("Order quantity cannot be zero.")

        broker_ticker = self.to_broker_ticker(ticker)
        scaled_limit = (
            float(limit_price) * 100.0
            if broker_ticker in self.GBX_DENOMINATED_T212_TICKERS
            else float(limit_price)
        )
        payload = {
            "ticker": broker_ticker,
            "quantity": qty,
            "limitPrice": round(scaled_limit, 2),
            "timeValidity": time_validity or self.config.t212_time_validity,
        }
        logger.info("T212 POST /equity/orders/limit | payload=%s", payload)
        return self._request("POST", "/equity/orders/limit", json_body=payload)

    def place_stop_order(
        self,
        ticker: str,
        signed_quantity: float,
        stop_price: float,
        time_validity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /equity/orders/stop"""
        qty = round(float(signed_quantity), self.config.fractional_decimals)
        broker_ticker = self.to_broker_ticker(ticker)
        scaled_stop = (
            float(stop_price) * 100.0
            if broker_ticker in self.GBX_DENOMINATED_T212_TICKERS
            else float(stop_price)
        )
        payload = {
            "ticker": broker_ticker,
            "quantity": qty,
            "stopPrice": round(scaled_stop, 2),
            "timeValidity": time_validity or self.config.t212_time_validity,
        }
        logger.info("T212 POST /equity/orders/stop | payload=%s", payload)
        return self._request("POST", "/equity/orders/stop", json_body=payload)

    def cancel_order(self, order_id: str | int) -> None:
        """DELETE /equity/orders/{id}"""
        logger.info("T212 DELETE /equity/orders/%s", order_id)
        self._request("DELETE", f"/equity/orders/{order_id}", rate_key="/equity/orders/market")

    # -------------------------------------------------------------------------
    # Rate-Limiting & HTTP Transport
    # -------------------------------------------------------------------------
    def _throttle(self, key: str) -> None:
        min_interval = self.ENDPOINT_MIN_INTERVALS.get(key, 1.2)
        last_ts = self._last_call_ts.get(key, 0.0)
        elapsed = time.monotonic() - last_ts
        if elapsed < min_interval:
            sleep_for = min_interval - elapsed
            logger.debug("Rate-limit throttle on %s: sleeping %.2fs", key, sleep_for)
            time.sleep(sleep_for)
        self._last_call_ts[key] = time.monotonic()

    def _request(
        self,
        method: str,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
        rate_key: Optional[str] = None,
        max_attempts: int = 3,
    ) -> Any:
        throttle_bucket = rate_key or path
        url = f"{self.base_url}{path}"

        for attempt in range(1, max_attempts + 1):
            self._throttle(throttle_bucket)
            try:
                resp = self.session.request(
                    method=method,
                    url=url,
                    json=json_body,
                    timeout=15.0,
                )
            except requests.RequestException as exc:
                if attempt == max_attempts:
                    raise Trading212APIError(0, f"Network error calling {path}: {exc}") from exc
                wait = 2.0**attempt
                logger.warning(
                    "Transient network error on %s %s (attempt %d/%d). Retrying in %.1fs: %s",
                    method,
                    path,
                    attempt,
                    max_attempts,
                    wait,
                    exc,
                )
                time.sleep(wait)
                continue

            if resp.status_code in {200, 201}:
                if not resp.text.strip():
                    return {}
                return resp.json()

            if resp.status_code == 204:
                return {}

            if resp.status_code == 429:
                reset_header = resp.headers.get("x-ratelimit-reset")
                wait = 5.5
                if reset_header and reset_header.isdigit():
                    wait = max(1.5, float(int(reset_header) - int(time.time())) + 0.5)
                logger.warning(
                    "Trading 212 HTTP 429 rate limit hit on %s (attempt %d/%d). Sleeping %.1fs...",
                    path,
                    attempt,
                    max_attempts,
                    wait,
                )
                if attempt == max_attempts:
                    raise Trading212APIError(429, f"Rate limit exceeded on {path}", resp.text)
                time.sleep(wait)
                continue

            if resp.status_code >= 500 and attempt < max_attempts:
                wait = 2.0**attempt
                logger.warning(
                    "Trading 212 server error %d on %s (attempt %d/%d). Retrying in %.1fs...",
                    resp.status_code,
                    path,
                    attempt,
                    max_attempts,
                    wait,
                )
                time.sleep(wait)
                continue

            raise Trading212APIError(resp.status_code, resp.text, resp.text)

        raise Trading212APIError(0, f"Exhausted retries for {method} {path}")
