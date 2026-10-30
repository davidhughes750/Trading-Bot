"""Multi-factor Quantitative Stock Screener & Recommendation Engine for Trading 212.

Scans a broad universe of liquid Trading 212 equities, computes technical factors
(EMA 20/50 crossover & trend alignment, Wilder's RSI 14, Wilder's ATR 14, Relative
Volume RVOL, and 10-bar Rate of Change), scores each stock from 0 to 100, outputs
human-readable buy recommendations with exact Stop-Loss and Take-Profit levels,
and feeds the #1 highest-conviction pick to the RiskManager & OrderExecutor.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from bot.config import Config
from bot.data_handler import DataHandler
from bot.models import (
    Position,
    Side,
    Signal,
    SignalAction,
    StockRecommendation,
)
from bot.strategy_engine import StrategyEngine

logger = logging.getLogger(__name__)


DEFAULT_T212_UNIVERSE: List[str] = [
    # 0. Mega-Cap "Magnificent 7+" Institutional Core (8)
    "GOOGL_US_EQ",  # Alphabet (Google)
    "META_US_EQ",   # Meta Platforms (mapped to T212 FB_US_EQ)
    "AMZN_US_EQ",   # Amazon
    "MSFT_US_EQ",   # Microsoft
    "AAPL_US_EQ",   # Apple
    "NFLX_US_EQ",   # Netflix
    "ORCL_US_EQ",   # Oracle
    "UBER_US_EQ",   # Uber Technologies
    # 1. High-Beta AI, Semiconductors & Compute (11)
    "PLTR_US_EQ",   # Palantir Technologies
    "NVDA_US_EQ",   # Nvidia
    "AMD_US_EQ",    # Advanced Micro Devices
    "SMCI_US_EQ",   # Super Micro Computer
    "ARM_US_EQ",    # Arm Holdings
    "MU_US_EQ",     # Micron Technology
    "AVGO_US_EQ",   # Broadcom
    "MRVL_US_EQ",   # Marvell Technology
    "TSM_US_EQ",    # Taiwan Semiconductor
    "ANET_US_EQ",   # Arista Networks
    "VRT_US_EQ",    # Vertiv Holdings (AI Data Center Cooling)
    # 2. Crypto-Linked High-Beta Equities (5)
    "MSTR_US_EQ",   # Strategy (MicroStrategy)
    "COIN_US_EQ",   # Coinbase
    "MARA_US_EQ",   # MARA Holdings
    "RIOT_US_EQ",   # Riot Platforms
    "CLSK_US_EQ",   # CleanSpark
    # 3. AI Power, Grid, Nuclear, Uranium & Gold/Resources (8)
    "VST_US_EQ",    # Vistra Corp
    "CEG_US_EQ",    # Constellation Energy
    "GEV_US_EQ",    # GE Vernova (Grid & Power Infrastructure)
    "OKLO_US_EQ",   # Oklo Inc.
    "CCJ_US_EQ",    # Cameco (Uranium)
    "ENPH_US_EQ",   # Enphase Energy
    "NEM_US_EQ",    # Newmont (Gold Miner — Risk-Off Hedge)
    "FCX_US_EQ",    # Freeport-McMoRan (Copper & Gold)
    # 4. Space, Quantum, Defense & Frontier Tech (7)
    "RKLB_US_EQ",   # Rocket Lab
    "IONQ_US_EQ",   # IonQ
    "ASTS_US_EQ",   # AST SpaceMobile
    "LUNR_US_EQ",   # Intuitive Machines
    "AXON_US_EQ",   # Axon Enterprise
    "KTOS_US_EQ",   # Kratos Defense & Security Solutions
    "RGTI_US_EQ",   # Rigetti Computing
    # 5. High-Beta Fintech & Digital Brokerage (6)
    "HOOD_US_EQ",   # Robinhood Markets
    "SOFI_US_EQ",   # SoFi Technologies
    "AFRM_US_EQ",   # Affirm Holdings
    "UPST_US_EQ",   # Upstart Holdings
    "NU_US_EQ",     # Nu Holdings
    "FUTU_US_EQ",   # Futu Holdings
    # 6. Hyper-Growth Cloud, Cyber & AI Software (8)
    "SHOP_US_EQ",   # Shopify
    "APP_US_EQ",    # AppLovin
    "CRWD_US_EQ",   # CrowdStrike
    "NET_US_EQ",    # Cloudflare
    "SNOW_US_EQ",   # Snowflake
    "PANW_US_EQ",   # Palo Alto Networks
    "DDOG_US_EQ",   # Datadog
    "IOT_US_EQ",    # Samsara
    # 7. Explosive Consumer, Social, Gaming & EV Breakouts (6)
    "TSLA_US_EQ",   # Tesla
    "RIVN_US_EQ",   # Rivian Automotive
    "RDDT_US_EQ",   # Reddit
    "CVNA_US_EQ",   # Carvana
    "DKNG_US_EQ",   # DraftKings
    "DUOL_US_EQ",   # Duolingo
    # 8. High-Beta Biotech, Healthcare & Global ADR Movers (4)
    "HIMS_US_EQ",   # Hims & Hers Health
    "VKTX_US_EQ",   # Viking Therapeutics
    "BABA_US_EQ",   # Alibaba
    "PDD_US_EQ",    # PDD Holdings
]

# UK 3x Leveraged & Inverse Short ETP Sleeve (London Stock Exchange — 0% Stamp Duty, 0% FX fee in GBP)
DEFAULT_UK_ETP_UNIVERSE: List[str] = [
    "QQQ3_UK_EQ",   # WisdomTree NASDAQ 100 3x Daily Leveraged Bull (GBP)
    "3LUS_UK_EQ",   # WisdomTree S&P 500 3x Daily Leveraged Bull (GBP)
    "3LSE_UK_EQ",   # WisdomTree PHLX Semiconductor 3x Daily Leveraged Bull (GBP)
    "3NVD_UK_EQ",   # Leverage Shares 3x Long Nvidia (GBP — 0% FX fee)
    "3TSL_UK_EQ",   # Leverage Shares 3x Long Tesla (GBP — 0% FX fee)
    "3LGO_UK_EQ",   # WisdomTree Gold 3x Daily Leveraged Bull (GBP — Risk-Off Hedge)
    "QQQS_UK_EQ",   # WisdomTree NASDAQ 100 3x Daily Short / Inverse Bear (GBP)
    "3USS_UK_EQ",   # WisdomTree S&P 500 3x Daily Short / Inverse Bear (GBP)
]


class StockScreener:
    """Scans a universe of Trading 212 stocks, ranks them by quant score, and recommends trades."""

    def __init__(
        self,
        config: Config,
        data_handler: DataHandler,
        strategy_engine: StrategyEngine,
    ) -> None:
        self.config = config
        self.data_handler = data_handler
        self.strategy_engine = strategy_engine

    def get_scan_universe(self) -> List[str]:
        """Combine configured symbols with the Trading 212 screener universe (preserving order)."""
        combined: List[str] = []
        seen = set()
        sources = list(self.config.symbols)
        if self.config.enable_screener:
            sources.extend(self.config.screener_universe or DEFAULT_T212_UNIVERSE)
            if getattr(self.config, "enable_uk_etp_sleeve", True):
                sources.extend(
                    getattr(self.config, "uk_etp_universe", None)
                    or DEFAULT_UK_ETP_UNIVERSE
                )

        for raw in sources:
            t212_ticker, _ = self.data_handler.resolve_ticker_pair(raw)
            if t212_ticker not in seen:
                seen.add(t212_ticker)
                combined.append(raw)
        return combined

    def evaluate_dataframe(
        self,
        symbol: str,
        df: pd.DataFrame,
        open_position: Optional[Position] = None,
    ) -> StockRecommendation:
        """Compute quantitative score (0-100), rating, and trade signal from an indicator DataFrame."""
        if len(df) < 12:
            raise ValueError(f"Insufficient bars ({len(df)}) to score {symbol}.")

        prev = df.iloc[-2]
        curr = df.iloc[-1]

        close_price = float(curr["close"])
        high_price = float(curr["high"])
        low_price = float(curr["low"])
        ema_fast = float(curr["ema_fast"])
        ema_slow = float(curr["ema_slow"])
        prev_fast = float(prev["ema_fast"])
        prev_slow = float(prev["ema_slow"])
        rsi = float(curr["rsi"])
        atr = float(curr["atr"])

        # Distance above 20 EMA in ATR units (guards against chasing exhausted spikes)
        ema_extension_atr = (
            (close_price - ema_fast) / max(atr, 1e-6) if close_price > ema_fast else 0.0
        )
        is_overextended = ema_extension_atr > self.config.max_ema_extension_atr

        # Upper-wick shooting-star rejection guard
        bar_range = max(0.0, high_price - low_price)
        upper_wick = max(0.0, high_price - close_price)
        has_upper_wick_rejection = (
            bar_range > 1.2 * max(atr, 1e-6) and upper_wick > 0.65 * bar_range
        )

        # Relative Volume (current bar volume vs 20-bar mean volume)
        vol_window = df["volume"].iloc[-21:-1]
        avg_vol = float(vol_window.mean()) if len(vol_window) > 0 else 0.0
        curr_vol = float(curr["volume"])
        rvol = (curr_vol / avg_vol) if avg_vol > 0 else 1.0

        # 10-bar Rate of Change (%)
        close_10_ago = float(df["close"].iloc[-11])
        roc_10_pct = (
            ((close_price - close_10_ago) / close_10_ago) * 100.0
            if close_10_ago > 0
            else 0.0
        )

        # Base crossover signal from StrategyEngine
        base_sig = self.strategy_engine.generate_signal(
            symbol=symbol, df=df, open_position=open_position
        )

        bullish_cross = (prev_fast <= prev_slow) and (ema_fast > ema_slow)
        ema_fast_rising = ema_fast > prev_fast
        trend_aligned = (close_price > ema_fast) and (ema_fast > ema_slow)
        ema_gap_pct = ((ema_fast - ema_slow) / ema_slow) * 100.0 if ema_slow > 0 else 0.0
        coiling_near_cross = (-0.25 <= ema_gap_pct <= 0.0) and ema_fast_rising and (close_price > ema_fast)

        # ---------------------------------------------------------------------
        # 1. Trend & Crossover Score (0 - 45 points)
        # ---------------------------------------------------------------------
        trend_score = 0.0
        reasons: List[str] = []

        if bullish_cross:
            trend_score = 45.0
            reasons.append("Fresh EMA(20/50) bullish crossover")
        elif trend_aligned and ema_fast_rising:
            trend_score = 34.0
            reasons.append("Strong uptrend (Close > EMA20 > EMA50)")
        elif ema_fast > ema_slow:
            trend_score = 22.0
            reasons.append("Bullish EMA(20>50) structure")
        elif coiling_near_cross:
            trend_score = 20.0
            reasons.append(f"Coiling for crossover (EMA gap {ema_gap_pct:+.2f}%)")
        else:
            trend_score = max(0.0, 10.0 + ema_gap_pct * 5.0)
            reasons.append("Below 50 EMA")

        # ---------------------------------------------------------------------
        # 2. RSI Momentum Score (0 - 25 points)
        # ---------------------------------------------------------------------
        if 54.0 <= rsi <= 67.0:
            rsi_score = 25.0
            reasons.append(f"Sweet-spot momentum (RSI {rsi:.1f})")
        elif 50.0 < rsi < 54.0:
            rsi_score = 18.0
            reasons.append(f"Positive RSI ({rsi:.1f})")
        elif 67.0 < rsi <= 72.0:
            rsi_score = 14.0
            reasons.append(f"High momentum (RSI {rsi:.1f})")
        elif rsi > 72.0:
            rsi_score = 0.0
            reasons.append(f"Overbought (RSI {rsi:.1f})")
        else:
            rsi_score = max(0.0, (rsi - 35.0) * 0.5)
            reasons.append(f"Weak RSI ({rsi:.1f})")

        # ---------------------------------------------------------------------
        # 3. Relative Volume (RVOL) Score (0 - 15 points)
        # ---------------------------------------------------------------------
        if rvol >= 1.5:
            vol_score = 15.0
            reasons.append(f"High volume surge ({rvol:.2f}x avg)")
        elif rvol >= 1.1:
            vol_score = 11.0
            reasons.append(f"Above-avg volume ({rvol:.2f}x)")
        elif rvol >= 0.8:
            vol_score = 6.0
        else:
            vol_score = 2.0

        # ---------------------------------------------------------------------
        # 4. 10-Bar Relative Strength (ROC) Score (0 - 15 points)
        # ---------------------------------------------------------------------
        if roc_10_pct >= 1.5:
            roc_score = 15.0
            reasons.append(f"10-bar RS +{roc_10_pct:.2f}%")
        elif roc_10_pct >= 0.5:
            roc_score = 11.0
            reasons.append(f"10-bar RS +{roc_10_pct:.2f}%")
        elif roc_10_pct > 0.0:
            roc_score = 7.0
        else:
            roc_score = 0.0

        # 5. Over-extension & Upper-Wick Penalties (Anti-Chasing Filter)
        penalty = 0.0
        if is_overextended:
            penalty += 15.0
            reasons.append(
                f"Overextended (+{ema_extension_atr:.1f}x ATR above EMA20 — wait for pullback)"
            )
        if has_upper_wick_rejection:
            penalty += 10.0
            reasons.append("Upper-wick selling rejection on candle")

        total_score = round(
            max(0.0, min(100.0, trend_score + rsi_score + vol_score + roc_score - penalty)),
            1,
        )
        sl, tp = self.strategy_engine.compute_initial_stops(
            entry_price=close_price, atr=max(atr, 0.01), side=Side.LONG
        )

        # FX Fee Reward Hurdle: US equities incur a 0.30% round-trip T212 FX fee.
        # Require distance to take-profit >= min_target_move_pct_fx (default 1.5%) so fees
        # stay <= 20% of expected gross profit. UK GBP ETPs (_UK_EQ) have 0% FX fee.
        is_uk_symbol = str(symbol).endswith("_UK_EQ")
        fx_rate = float(getattr(self.config, "fx_fee_rate", 0.0015))
        min_tp_pct = float(getattr(self.config, "min_target_move_pct_fx", 1.5))
        expected_tp_pct = ((tp - close_price) / close_price * 100.0) if close_price > 0 else 0.0
        has_insufficient_fx_reward = (
            not is_uk_symbol and fx_rate > 0.0 and expected_tp_pct < min_tp_pct
        )
        if has_insufficient_fx_reward:
            reasons.append(
                f"Target move +{expected_tp_pct:.2f}% below {min_tp_pct:.1f}% FX fee hurdle"
            )

        # Determine Rating & whether this recommendation is actionable for auto-trading
        actionable = False
        effective_signal = base_sig
        volume_confirmed = rvol >= self.config.min_rvol_for_entry

        if (
            base_sig.action == SignalAction.BUY
            and not base_sig.is_exit
            and not is_overextended
            and not has_upper_wick_rejection
            and not has_insufficient_fx_reward
            and rvol >= (0.85 * self.config.min_rvol_for_entry)
        ):
            rating = "STRONG BUY"
            actionable = True
        elif (
            trend_aligned
            and ema_fast_rising
            and (self.config.rsi_long_threshold < rsi <= 68.0)
            and volume_confirmed
            and not is_overextended
            and not has_upper_wick_rejection
            and not has_insufficient_fx_reward
            and total_score >= self.config.min_recommendation_score
        ):
            rating = "STRONG BUY" if total_score >= 80.0 else "BUY"
            if self.config.trade_top_recommendation and open_position is None:
                actionable = True
                effective_signal = Signal(
                    symbol=symbol,
                    action=SignalAction.BUY,
                    candle_timestamp=curr["timestamp"],
                    close_price=close_price,
                    ema_fast=ema_fast,
                    ema_slow=ema_slow,
                    rsi=rsi,
                    atr=atr,
                    reason=f"Screener {rating} (Score={total_score:.1f}/100: {', '.join(reasons[:3])})",
                    target_side=Side.LONG,
                    is_exit=False,
                )
        elif (is_overextended or has_insufficient_fx_reward) and trend_aligned:
            rating = "WATCH"
        elif coiling_near_cross and rsi >= 50.0:
            rating = "WATCH"
        elif ema_fast > ema_slow and rsi >= 48.0:
            rating = "HOLD"
        else:
            rating = "AVOID"

        # Explain why a high-scoring stock is not rated BUY (score vs. hard gates)
        blocker = ""
        if (
            rating not in ("BUY", "STRONG BUY")
            and total_score >= self.config.min_recommendation_score
        ):
            blocked_by: List[str] = []
            if not trend_aligned:
                blocked_by.append("price/EMA trend not aligned (needs Close > EMA20 > EMA50)")
            if not ema_fast_rising:
                blocked_by.append("EMA20 not rising")
            if rsi <= self.config.rsi_long_threshold:
                blocked_by.append(f"RSI {rsi:.1f} <= {self.config.rsi_long_threshold:.0f}")
            elif rsi > 68.0:
                blocked_by.append(f"RSI {rsi:.1f} > 68 (overbought)")
            if not volume_confirmed:
                blocked_by.append(
                    f"RVOL {rvol:.2f}x < {self.config.min_rvol_for_entry:.2f}x"
                )
            if is_overextended:
                blocked_by.append(
                    f"overextended {ema_extension_atr:.1f}x ATR above EMA20"
                )
            if has_upper_wick_rejection:
                blocked_by.append("upper-wick rejection candle")
            if has_insufficient_fx_reward:
                blocked_by.append(
                    f"target move +{expected_tp_pct:.2f}% < {min_tp_pct:.1f}% FX hurdle"
                )
            blocker = "; ".join(blocked_by)

        # Trend-strength flag used by the take-profit extension logic: only
        # extend a winner's target while the run is clearly still intact.
        trend_strong = bool(
            trend_aligned
            and ema_fast_rising
            and rsi < self.config.tp_extension_rsi_max
            and rvol >= self.config.tp_extension_min_rvol
            and not has_upper_wick_rejection
        )

        recent_closes = (
            [round(float(p), 2) for p in df["close"].iloc[-12:].tolist()]
            if len(df) >= 2
            else [close_price]
        )

        recent_candles: List[Dict[str, Any]] = []
        if len(df) >= 2:
            tail = df.iloc[-16:]
            for idx, row in tail.iterrows():
                ts = row.get("timestamp")
                time_str = ""
                datetime_str = ""
                ts_iso = ""
                if ts is not None and not pd.isna(ts):
                    try:
                        ts_dt = pd.to_datetime(ts)
                        if ts_dt.tzinfo is None:
                            ts_dt = ts_dt.tz_localize("UTC")
                        ts_utc = ts_dt.tz_convert("UTC")
                        time_str = ts_utc.strftime("%H:%M UTC")
                        datetime_str = ts_utc.strftime("%b %d, %H:%M UTC")
                        ts_iso = ts_utc.isoformat()
                    except Exception:
                        time_str = f"{str(ts)[11:16]} UTC"
                        datetime_str = f"{str(ts)[:16]} UTC"
                        ts_iso = str(ts)

                e20_val = row["ema_fast"] if ("ema_fast" in row and not pd.isna(row["ema_fast"])) else (
                    row["ema_20"] if ("ema_20" in row and not pd.isna(row["ema_20"])) else row["close"]
                )
                e50_val = row["ema_slow"] if ("ema_slow" in row and not pd.isna(row["ema_slow"])) else (
                    row["ema_50"] if ("ema_50" in row and not pd.isna(row["ema_50"])) else (row["close"] * 0.995)
                )

                recent_candles.append({
                    "ts_iso": ts_iso,
                    "time": time_str,
                    "datetime": datetime_str,
                    "o": round(float(row["open"]), 2),
                    "h": round(float(row["high"]), 2),
                    "l": round(float(row["low"]), 2),
                    "c": round(float(row["close"]), 2),
                    "v": round(float(row.get("volume", 0)), 0),
                    "e20": round(float(e20_val), 2),
                    "e50": round(float(e50_val), 2),
                })

        return StockRecommendation(
            symbol=symbol,
            score=total_score,
            rating=rating,
            actionable=actionable,
            close_price=close_price,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            rsi=rsi,
            atr=atr,
            rvol=round(rvol, 2),
            roc_10_pct=round(roc_10_pct, 2),
            suggested_stop_loss=round(sl, 2),
            suggested_take_profit=round(tp, 2),
            thesis="; ".join(reasons),
            signal=effective_signal,
            blocker=blocker,
            trend_strong=trend_strong,
            sparkline=recent_closes,
            candles=recent_candles,
        )

    def _scan_single_symbol(
        self,
        raw_symbol: str,
        open_positions: Dict[str, Position],
        ohlcv_cache: Optional[Dict[str, pd.DataFrame]],
    ) -> Optional[StockRecommendation]:
        t212_ticker, _ = self.data_handler.resolve_ticker_pair(raw_symbol)
        try:
            if ohlcv_cache is not None and t212_ticker in ohlcv_cache:
                df = ohlcv_cache[t212_ticker]
            else:
                df = self.data_handler.fetch_closed_ohlcv(raw_symbol)
                if ohlcv_cache is not None:
                    ohlcv_cache[t212_ticker] = df

            return self.evaluate_dataframe(
                symbol=t212_ticker,
                df=df,
                open_position=open_positions.get(t212_ticker),
            )
        except Exception as exc:
            logger.warning(
                "[%s] Screener skipped ticker due to data error: %s", t212_ticker, exc
            )
            return None

    def scan_universe(
        self,
        open_positions: Dict[str, Position],
        ohlcv_cache: Optional[Dict[str, pd.DataFrame]] = None,
    ) -> List[StockRecommendation]:
        """Scan all 50 stocks in parallel and return recommendations sorted highest score first."""
        recommendations: List[StockRecommendation] = []
        universe = self.get_scan_universe()

        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [
                pool.submit(
                    self._scan_single_symbol, raw_sym, open_positions, ohlcv_cache
                )
                for raw_sym in universe
            ]
            for fut in as_completed(futures):
                rec = fut.result()
                if rec is not None:
                    recommendations.append(rec)

        recommendations.sort(key=lambda r: (r.actionable, r.score, r.roc_10_pct), reverse=True)
        self._save_recommendations_report(recommendations)
        return recommendations

    def format_leaderboard(
        self, recommendations: List[StockRecommendation], top_n: int = 10
    ) -> str:
        """Render a clean ASCII table of the top stock recommendations."""
        if not recommendations:
            return "No stock recommendations available."

        lines = [
            "",
            "=" * 118,
            f"  TRADING 212 QUANTITATIVE STOCK RECOMMENDATIONS (Top {min(top_n, len(recommendations))} of {len(recommendations)} Scanned | Timeframe: {self.config.timeframe})",
            "=" * 118,
            f"{'RANK':<5} {'TICKER':<13} {'RATING':<12} {'SCORE':<7} {'PRICE':>9} {'EMA20/50':>15} {'RSI':>6} {'RVOL':>6} {'STOP-LOSS':>10} {'TARGET':>10}  {'THESIS'}",
            "-" * 118,
        ]
        for idx, rec in enumerate(recommendations[:top_n], start=1):
            ema_pair = f"{rec.ema_fast:.1f}/{rec.ema_slow:.1f}"
            lines.append(
                f"#{idx:<4} {rec.symbol:<13} {rec.rating:<12} {rec.score:>5.1f}   "
                f"${rec.close_price:>8.2f} {ema_pair:>15} {rec.rsi:>6.1f} {rec.rvol:>5.2f}x "
                f"${rec.suggested_stop_loss:>9.2f} ${rec.suggested_take_profit:>9.2f}  {rec.thesis}"
            )
        lines.append("=" * 118)
        return "\n".join(lines)

    def _save_recommendations_report(
        self, recommendations: List[StockRecommendation]
    ) -> None:
        path = Path("logs/recommendations.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "timeframe": self.config.timeframe,
            "count": len(recommendations),
            "top_pick": recommendations[0].symbol if recommendations else None,
            "recommendations": [
                {
                    "rank": idx,
                    "symbol": r.symbol,
                    "rating": r.rating,
                    "score": r.score,
                    "actionable": r.actionable,
                    "close_price": r.close_price,
                    "ema_fast": round(r.ema_fast, 4),
                    "ema_slow": round(r.ema_slow, 4),
                    "rsi": round(r.rsi, 2),
                    "atr": round(r.atr, 4),
                    "rvol": r.rvol,
                    "roc_10_pct": r.roc_10_pct,
                    "suggested_stop_loss": r.suggested_stop_loss,
                    "suggested_take_profit": r.suggested_take_profit,
                    "thesis": r.thesis,
                    "blocker": r.blocker,
                    "sparkline": r.sparkline,
                    "candles": r.candles,
                }
                for idx, r in enumerate(recommendations, start=1)
            ],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
