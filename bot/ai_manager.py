"""AI Portfolio Manager (Gemini LLM + Quantitative News & Catalyst Gatekeeper).

Acts as an intelligent Portfolio Manager layer on top of the deterministic Python
StockScreener and RiskManager:
1. Pre-Trade Entry Vetting (`evaluate_entry_candidate`):
   - Fetches real-time company news headlines via Yahoo Finance for any actionable pick.
   - Evaluates technical setup + news catalysts + portfolio concentration using Google Gemini
     (or a built-in deterministic News & Catalyst Risk Engine when `GEMINI_API_KEY` is not set).
   - Outputs `APPROVE` or `VETO`, confidence (0-100%), position size multiplier (0.5x-1.0x),
     and a concise 1-sentence thesis recorded to `logs/ai_decisions.json` for the Web Dashboard.
2. Smart Slot Rotation (`evaluate_slot_rotation`):
   - When all 3 portfolio slots are full and a new `STRONG BUY` (>= 80/100) appears,
     evaluates whether to close a lagging/stagnant position early and rotate into the stronger setup.

Safety Invariant:
- The AI Portfolio Manager can NEVER bypass `RiskManager` hard limits (cannot exceed the 33% slot
  cap, cannot disable the 1.5x ATR Stop-Loss, and cannot override the 5% 24h Circuit Breaker).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import yfinance as yf

from bot.config import Config
from bot.data_handler import DataHandler
from bot.models import Position, StockRecommendation

logger = logging.getLogger(__name__)

# Bearish / binary risk keywords for deterministic news headline screening
_BEARISH_NEWS_KEYWORDS = (
    "sec investigation",
    "subpoena",
    "accounting fraud",
    "bankruptcy",
    "chapter 11",
    "delisting",
    "trading halt",
    "guidance cut",
    "misses estimates",
    "public offering",
    "share dilution",
    "secondary offering",
    "downgrade to sell",
    "recall",
    "data breach",
)

_BULLISH_NEWS_KEYWORDS = (
    "beats estimates",
    "raises guidance",
    "upgrade",
    "buyback",
    "contract win",
    "partnership",
    "record revenue",
    "breakthrough",
    "ai demand",
    "price target raised",
)


@dataclass
class AIDecision:
    """Structured trade decision produced by the AI Portfolio Manager."""

    timestamp: str
    symbol: str
    action_type: str  # 'ENTRY_VETTING' | 'SLOT_ROTATION'
    decision: str  # 'APPROVE' | 'VETO' | 'ROTATE' | 'HOLD'
    confidence: int
    size_multiplier: float
    engine: str  # e.g. 'gemini-2.5-flash' or 'quant-news-heuristic'
    score: float
    rating: str
    reasoning: str
    headlines: List[str] = field(default_factory=list)
    replace_symbol: Optional[str] = None


class AIPortfolioManager:
    """Hybrid AI + News Catalyst Portfolio Manager for Trading 212."""

    GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, config: Config) -> None:
        self.config = config
        self.decisions_path = Path(self.config.ai_decisions_file)
        self.last_scan_status: str = ""
        self.last_scan_timestamp: str = ""
        self.recent_decisions: List[AIDecision] = self._load_recent_decisions()

    @property
    def is_gemini_configured(self) -> bool:
        key = (self.config.gemini_api_key or "").strip()
        return bool(key and "your_" not in key.lower())

    @property
    def active_engine_label(self) -> str:
        if not self.config.enable_ai_manager:
            return "Disabled"
        if self.is_gemini_configured:
            return f"Google Gemini ({self.config.gemini_model})"
        return "Quant News & Catalyst Engine (Set GEMINI_API_KEY for LLM)"

    # -------------------------------------------------------------------------
    # State Persistence for Web Dashboard
    # -------------------------------------------------------------------------
    def _load_recent_decisions(self) -> List[AIDecision]:
        if not self.decisions_path.exists():
            return []
        try:
            raw = json.loads(self.decisions_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self.last_scan_status = str(raw.get("last_scan_status") or "")
                self.last_scan_timestamp = str(raw.get("last_scan_timestamp") or "")
                items = raw.get("decisions", [])
            else:
                items = []
            return [AIDecision(**item) for item in items[:25]]
        except Exception:
            return []

    def _save_decisions_file(self) -> None:
        try:
            self.decisions_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "engine": self.active_engine_label,
                "gemini_configured": self.is_gemini_configured,
                "last_scan_status": self.last_scan_status,
                "last_scan_timestamp": self.last_scan_timestamp,
                "decisions": [asdict(d) for d in self.recent_decisions],
            }
            self.decisions_path.write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            logger.warning("Failed to write AI decisions file: %s", exc)

    def _record_decision(self, dec: AIDecision) -> None:
        # Replace any older decision for the same symbol on the same action_type so we don't duplicate
        self.recent_decisions = [
            d for d in self.recent_decisions
            if not (d.symbol == dec.symbol and d.action_type == dec.action_type)
        ]
        self.recent_decisions.insert(0, dec)
        self.recent_decisions = self.recent_decisions[:25]
        self._save_decisions_file()

    def record_scan_status(self, status_message: str) -> None:
        """Record the outcome of the latest 15-minute candle scan for the Web Dashboard."""
        self.last_scan_status = status_message
        self.last_scan_timestamp = datetime.now(timezone.utc).isoformat()
        self._save_decisions_file()

    # -------------------------------------------------------------------------
    # Real-Time News Fetcher (Yahoo Finance)
    # -------------------------------------------------------------------------
    def fetch_recent_headlines(self, symbol: str, max_items: int = 5) -> List[str]:
        """Fetch latest company news headlines for `symbol` via yfinance."""
        _, yahoo_sym = DataHandler.resolve_ticker_pair(symbol)
        headlines: List[str] = []
        try:
            ticker_obj = yf.Ticker(yahoo_sym)
            news_items = getattr(ticker_obj, "news", None) or []
            for item in news_items[:max_items]:
                if not isinstance(item, dict):
                    continue
                # Support both legacy and nested content yfinance news schemas
                content = item.get("content") if isinstance(item.get("content"), dict) else item
                title = (
                    content.get("title")
                    or item.get("title")
                    or ""
                ).strip()
                publisher = ""
                if isinstance(content.get("provider"), dict):
                    publisher = str(content["provider"].get("displayName") or "").strip()
                elif item.get("publisher"):
                    publisher = str(item.get("publisher")).strip()

                if title:
                    headlines.append(f"{title} ({publisher})" if publisher else title)
        except Exception as exc:
            logger.debug("[%s] Could not fetch Yahoo Finance news: %s", symbol, exc)
        return headlines

    # -------------------------------------------------------------------------
    # 1. Pre-Trade Entry Vetting
    # -------------------------------------------------------------------------
    def evaluate_entry_candidate(
        self,
        pick: StockRecommendation,
        open_positions: Dict[str, Position],
        total_equity: float,
        market_regime_summary: str = "BULLISH (QQQ > EMA20 > EMA50)",
    ) -> AIDecision:
        """Vet a top StockScreener BUY/STRONG BUY candidate before placing an order."""
        now_iso = datetime.now(timezone.utc).isoformat()
        headlines = self.fetch_recent_headlines(pick.symbol, max_items=5)

        if self.is_gemini_configured:
            try:
                dec = self._call_gemini_for_entry(
                    pick=pick,
                    open_positions=open_positions,
                    total_equity=total_equity,
                    headlines=headlines,
                    now_iso=now_iso,
                    market_regime_summary=market_regime_summary,
                )
                self._record_decision(dec)
                return dec
            except Exception as exc:
                logger.warning(
                    "[%s] Gemini API call failed (%s); falling back to Quant News Engine.",
                    pick.symbol,
                    exc,
                )

        dec = self._heuristic_entry_decision(
            pick=pick,
            open_positions=open_positions,
            headlines=headlines,
            now_iso=now_iso,
        )
        self._record_decision(dec)
        return dec

    def _call_gemini_for_entry(
        self,
        pick: StockRecommendation,
        open_positions: Dict[str, Position],
        total_equity: float,
        headlines: List[str],
        now_iso: str,
        market_regime_summary: str = "BULLISH (QQQ > EMA20 > EMA50)",
    ) -> AIDecision:
        held_list = list(open_positions.keys()) or ["None"]
        news_block = (
            "\n".join(f"- {h}" for h in headlines)
            if headlines
            else "- No major breaking headlines in the last 24h."
        )
        ema_ext_atr = (
            (pick.close_price - pick.ema_fast) / max(pick.atr, 0.01)
            if pick.close_price > pick.ema_fast
            else 0.0
        )

        prompt = (
            "You are the Senior AI Portfolio Manager & Risk Gatekeeper for a concentrated 3-slot "
            f"high-beta US equity momentum bot on Trading 212 UK (Account Equity: £{total_equity:.2f}, "
            f"Max Slots: {self.config.max_open_positions}, Currently Open Positions: {', '.join(held_list)}).\n"
            "Note: Every US equity trade incurs a 0.30% round-trip FX fee (0.15% buy + 0.15% sell), so we ONLY "
            "want high-conviction setups with room to run.\n\n"
            f"Broad Market Regime (Nasdaq-100 QQQ): {market_regime_summary}\n\n"
            "Candidate Trade Identified by 15-Minute Quant Screener:\n"
            f"- Ticker: {pick.symbol}\n"
            f"- Quant Rating & Score: {pick.rating} ({pick.score:.1f} / 100)\n"
            f"- Price: ${pick.close_price:.2f} | 20 EMA: ${pick.ema_fast:.2f} | 50 EMA: ${pick.ema_slow:.2f} "
            f"(Distance above 20 EMA: +{ema_ext_atr:.2f}x ATR)\n"
            f"- 14 RSI: {pick.rsi:.1f} | 14 ATR: ${pick.atr:.2f} | Relative Volume (RVOL): {pick.rvol:.2f}x | 10-Bar ROC: {pick.roc_10_pct:+.2f}%\n"
            f"- Planned Stop-Loss: ${pick.suggested_stop_loss:.2f} ({self.config.stop_loss_atr_mult}x ATR) | "
            f"Take-Profit: ${pick.suggested_take_profit:.2f} ({self.config.take_profit_atr_mult}x ATR)\n"
            f"- Technical Thesis: {pick.thesis}\n\n"
            f"Latest Real-Time News Headlines for {pick.symbol}:\n{news_block}\n\n"
            "Strict Vetting Rules (Act as a sniper — protect capital from whipsaws and overtrading):\n"
            "1. VETO if price is overextended (> 1.6x ATR above 20 EMA) or RSI > 68 without a major breaking news catalyst (high risk of buying the top before a pullback).\n"
            "2. VETO if Relative Volume is weak (RVOL < 1.0x) and there is no fresh bullish crossover or positive news catalyst.\n"
            "3. VETO if headlines indicate negative binary catalysts (share dilution, offering, SEC probe, guidance cut, analyst downgrade, or earnings miss).\n"
            "4. VETO if the candidate duplicates the exact same high-beta niche already in Currently Open Positions (e.g., holding a crypto miner/quantum/space stock and adding a second one).\n"
            "5. APPROVE only when trend structure, volume participation, and news alignment justify paying the 0.30% round-trip FX fee.\n"
            "6. Set size_multiplier between 0.65 and 1.0 (1.0 for A+ conviction with volume/news tailwind, 0.75-0.85 for standard setups).\n\n"
            "Respond strictly in JSON matching this schema:\n"
            '{"decision": "APPROVE" or "VETO", "confidence": 0-100, "size_multiplier": 0.65-1.0, '
            '"reasoning": "Concise 1-sentence sniper explanation covering momentum quality, volume/extension, and news"}'
        )

        parsed = self._invoke_gemini_json(prompt)
        decision_str = str(parsed.get("decision", "APPROVE")).strip().upper()
        if decision_str not in {"APPROVE", "VETO"}:
            decision_str = "APPROVE"

        confidence = max(1, min(100, int(parsed.get("confidence", 80))))
        size_mult = max(0.5, min(1.0, float(parsed.get("size_multiplier", 1.0))))
        reasoning = str(parsed.get("reasoning") or pick.thesis).strip()

        return AIDecision(
            timestamp=now_iso,
            symbol=pick.symbol,
            action_type="ENTRY_VETTING",
            decision=decision_str,
            confidence=confidence,
            size_multiplier=size_mult,
            engine=self.config.gemini_model,
            score=pick.score,
            rating=pick.rating,
            reasoning=reasoning,
            headlines=headlines[:3],
        )

    def _heuristic_entry_decision(
        self,
        pick: StockRecommendation,
        open_positions: Dict[str, Position],
        headlines: List[str],
        now_iso: str,
    ) -> AIDecision:
        """Deterministic News + Sector-Overlap + Momentum Portfolio Manager when Gemini key is absent."""
        joined_news = " | ".join(headlines).lower()
        bearish_hits = [kw for kw in _BEARISH_NEWS_KEYWORDS if kw in joined_news]
        bullish_hits = [kw for kw in _BULLISH_NEWS_KEYWORDS if kw in joined_news]

        # Check crypto-proxy concentration (max 2 of MSTR, COIN, MARA, RIOT at once)
        crypto_tickers = {"MSTR_US_EQ", "COIN_US_EQ", "MARA_US_EQ", "RIOT_US_EQ"}
        open_crypto = [s for s in open_positions if s in crypto_tickers]
        if pick.symbol in crypto_tickers and len(open_crypto) >= 2:
            return AIDecision(
                timestamp=now_iso,
                symbol=pick.symbol,
                action_type="ENTRY_VETTING",
                decision="VETO",
                confidence=88,
                size_multiplier=0.0,
                engine="quant-news-engine",
                score=pick.score,
                rating=pick.rating,
                reasoning=(
                    f"Vetoed to prevent excessive crypto-proxy correlation (already holding {', '.join(open_crypto)})."
                ),
                headlines=headlines[:3],
            )

        if bearish_hits:
            return AIDecision(
                timestamp=now_iso,
                symbol=pick.symbol,
                action_type="ENTRY_VETTING",
                decision="VETO",
                confidence=85,
                size_multiplier=0.0,
                engine="quant-news-engine",
                score=pick.score,
                rating=pick.rating,
                reasoning=f"Negative news catalyst detected in headlines ({', '.join(bearish_hits)}).",
                headlines=headlines[:3],
            )

        size_mult = 1.0 if pick.score >= 80.0 or bullish_hits else 0.90
        confidence = min(96, int(pick.score + (6 if bullish_hits else 2)))
        news_note = (
            f"Positive news catalyst ({bullish_hits[0]})"
            if bullish_hits
            else ("Clean news feed (" + str(len(headlines)) + " headlines checked)" if headlines else "No adverse news")
        )

        return AIDecision(
            timestamp=now_iso,
            symbol=pick.symbol,
            action_type="ENTRY_VETTING",
            decision="APPROVE",
            confidence=confidence,
            size_multiplier=size_mult,
            engine="quant-news-engine",
            score=pick.score,
            rating=pick.rating,
            reasoning=f"{news_note}; {pick.thesis}",
            headlines=headlines[:3],
        )

    # -------------------------------------------------------------------------
    # 2. Smart Slot Rotation (When 3/3 Slots Are Full)
    # -------------------------------------------------------------------------
    def evaluate_slot_rotation(
        self,
        new_pick: StockRecommendation,
        open_positions: Dict[str, Position],
        all_recommendations: List[StockRecommendation],
        latest_prices: Dict[str, float],
    ) -> Optional[AIDecision]:
        """When all slots are full and a new STRONG BUY (>=80) appears, check if we should rotate out of a laggard."""
        if not self.config.ai_slot_rotation_enabled:
            return None
        if new_pick.score < 80.0:
            return None

        rec_by_sym = {r.symbol: r for r in all_recommendations}

        # Find the weakest currently held position
        weakest_sym: Optional[str] = None
        weakest_score: float = 999.0
        weakest_r: float = 0.0

        for sym, pos in open_positions.items():
            mark = latest_prices.get(sym, pos.entry_price)
            r_mult = pos.current_r_multiple(mark)
            # Never interrupt a winning trade that is already >= +0.4R or has trailing stop active
            if pos.trailing_active or r_mult >= 0.40:
                continue
            # In live/demo trading, require a minimum hold duration before rotating out of a slot
            # so the bot does not churn 0.30% round-trip FX fees on freshly opened trades.
            if self.config.execution_mode in {"demo", "live"} and self.config.min_hold_minutes_for_rotation > 0:
                try:
                    opened_dt = datetime.fromisoformat(pos.opened_at)
                    if opened_dt.tzinfo is None:
                        opened_dt = opened_dt.replace(tzinfo=timezone.utc)
                    held_mins = (datetime.now(timezone.utc) - opened_dt).total_seconds() / 60.0
                    if held_mins < self.config.min_hold_minutes_for_rotation:
                        continue
                except Exception:
                    pass
            cur_rec = rec_by_sym.get(sym)
            cur_score = cur_rec.score if cur_rec is not None else 50.0
            if cur_score < weakest_score:
                weakest_score = cur_score
                weakest_sym = sym
                weakest_r = r_mult

        # Only consider rotating if the held position has deteriorated (< 50 score)
        # AND the new STRONG BUY candidate outscores it by at least +28 points
        if weakest_sym is None or weakest_score >= 50.0 or (new_pick.score - weakest_score) < 28.0:
            return None

        now_iso = datetime.now(timezone.utc).isoformat()
        headlines = self.fetch_recent_headlines(new_pick.symbol, max_items=3)

        # Positions that will remain in the portfolio if we close `weakest_sym`
        retained_positions = [s for s in open_positions.keys() if s != weakest_sym]

        # Pre-check high-beta niche duplication against retained positions so we NEVER
        # sell a position to rotate into a stock that duplicates an already-retained niche.
        niche_groups = {
            "Crypto & Bitcoin Miners": {"MSTR_US_EQ", "COIN_US_EQ", "MARA_US_EQ", "RIOT_US_EQ", "CLSK_US_EQ"},
            "Quantum Computing": {"IONQ_US_EQ", "RGTI_US_EQ", "QBTS_US_EQ"},
            "Space & Satellite": {"RKLB_US_EQ", "ASTS_US_EQ", "LUNR_US_EQ"},
            "Next-Gen Nuclear": {"SMR_US_EQ", "OKLO_US_EQ"},
        }
        for niche_name, members in niche_groups.items():
            if new_pick.symbol in members:
                overlapping = [s for s in retained_positions if s in members]
                if overlapping:
                    dec = AIDecision(
                        timestamp=now_iso,
                        symbol=new_pick.symbol,
                        action_type="SLOT_ROTATION",
                        decision="HOLD",
                        confidence=95,
                        size_multiplier=0.0,
                        engine="quant-niche-guard",
                        score=new_pick.score,
                        rating=new_pick.rating,
                        reasoning=(
                            f"Rotation blocked: {new_pick.symbol} duplicates {niche_name} niche already held by "
                            f"{', '.join(overlapping)} (preventing Rotate-then-Veto churn on {weakest_sym})."
                        ),
                        headlines=headlines,
                        replace_symbol=weakest_sym,
                    )
                    self._record_decision(dec)
                    return dec

        if self.is_gemini_configured:
            try:
                news_block = (
                    "\n".join(f"- {h}" for h in headlines)
                    if headlines
                    else "- No major breaking headlines in the last 24h."
                )
                prompt = (
                    "You are the AI Portfolio Manager for a concentrated high-beta momentum bot on Trading 212.\n"
                    f"All sleeve slots are currently full, and a new STRONG BUY breakout just triggered:\n"
                    f"- New Candidate: {new_pick.symbol} | Score: {new_pick.score:.1f}/100 ({new_pick.rating}) | "
                    f"RSI: {new_pick.rsi:.1f} | RVOL: {new_pick.rvol:.2f}x | Thesis: {new_pick.thesis}\n"
                    f"- Weakest Held Position (to be sold): {weakest_sym} | Current Score: {weakest_score:.1f}/100 | "
                    f"Unrealized R-Multiple: {weakest_r:+.2f}R\n"
                    f"- Other Retained Open Positions (will remain in portfolio): {', '.join(retained_positions) or 'None'}\n"
                    f"- Latest News Headlines for {new_pick.symbol}:\n{news_block}\n\n"
                    "Strict Rotation Rules:\n"
                    "1. Return HOLD if the New Candidate duplicates the exact same sector/niche as any of the Other Retained Open Positions.\n"
                    "2. Return HOLD if headlines indicate negative binary catalysts (dilution, offering, downgrade) or if RSI > 68 without a catalyst.\n"
                    "3. Return ROTATE only if the New Candidate is ready to be bought immediately and clearly upgrades the portfolio.\n"
                    'Respond strictly in JSON: {"decision": "ROTATE" or "HOLD", "confidence": 0-100, "reasoning": "1 sentence"}'
                )
                parsed = self._invoke_gemini_json(prompt)
                decision_str = str(parsed.get("decision", "HOLD")).strip().upper()
                if decision_str not in {"ROTATE", "HOLD"}:
                    decision_str = "HOLD"
                dec = AIDecision(
                    timestamp=now_iso,
                    symbol=new_pick.symbol,
                    action_type="SLOT_ROTATION",
                    decision=decision_str,
                    confidence=int(parsed.get("confidence", 80)),
                    size_multiplier=1.0,
                    engine=self.config.gemini_model,
                    score=new_pick.score,
                    rating=new_pick.rating,
                    reasoning=str(parsed.get("reasoning") or "").strip(),
                    headlines=headlines,
                    replace_symbol=weakest_sym,
                )
                self._record_decision(dec)
                return dec
            except Exception as exc:
                logger.warning("Gemini slot rotation check failed (%s); using heuristic.", exc)

        dec = AIDecision(
            timestamp=now_iso,
            symbol=new_pick.symbol,
            action_type="SLOT_ROTATION",
            decision="ROTATE",
            confidence=82,
            size_multiplier=1.0,
            engine="quant-news-engine",
            score=new_pick.score,
            rating=new_pick.rating,
            reasoning=(
                f"Rotating stagnant slot {weakest_sym} (score {weakest_score:.0f}/100, {weakest_r:+.2f}R) "
                f"into fresh STRONG BUY {new_pick.symbol} (score {new_pick.score:.0f}/100)."
            ),
            headlines=headlines,
            replace_symbol=weakest_sym,
        )
        self._record_decision(dec)
        return dec

    # -------------------------------------------------------------------------
    # Low-Level Gemini REST API Caller (Supports both AI Studio & Vertex Express keys)
    # -------------------------------------------------------------------------
    def _invoke_gemini_json(self, prompt: str) -> Dict[str, Any]:
        """Call Google Gemini generateContent REST endpoint with structured JSON output."""
        api_key = self.config.gemini_api_key.strip()
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        # Keys starting with 'AQ.' are Vertex AI Express Mode keys (aiplatform.googleapis.com);
        # keys starting with 'AIza' are Google AI Studio keys (generativelanguage.googleapis.com).
        if api_key.startswith("AQ."):
            endpoints = [
                f"https://aiplatform.googleapis.com/v1/publishers/google/models/{self.config.gemini_model}:generateContent",
                f"{self.GEMINI_API_BASE}/{self.config.gemini_model}:generateContent",
            ]
        else:
            endpoints = [
                f"{self.GEMINI_API_BASE}/{self.config.gemini_model}:generateContent",
                f"https://aiplatform.googleapis.com/v1/publishers/google/models/{self.config.gemini_model}:generateContent",
            ]

        last_err = ""
        for url in endpoints:
            resp = requests.post(url, params={"key": api_key}, json=body, timeout=12)
            if resp.status_code < 400:
                data = resp.json()
                text = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "{}")
                )
                return json.loads(text)
            last_err = f"Gemini HTTP {resp.status_code} ({url.split('/')[2]}): {resp.text[:160]}"

        raise RuntimeError(last_err)
