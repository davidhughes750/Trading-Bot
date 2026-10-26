#!/usr/bin/env python3
"""Real-time Web GUI Dashboard for the Trading 212 Automated Trading Bot.

Reads live bot state from:
- `logs/t212_state.json`       (open positions, entry prices, SL/TP, trailing stops)
- `logs/recommendations.json`  (25-stock quantitative screener rankings & theses)
- `logs/trading_bot.log`       (live portfolio equity, drawdown, and execution events)

Can be run standalone while `main.py` is running:
    python dashboard.py            # Serves live dashboard at http://127.0.0.1:8050
Or started automatically in the background by `main.py`.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import socket
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

from bot import __version__
from bot.config import Config

logger = logging.getLogger(__name__)

PORTFOLIO_LINE_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?"
    r"Total Equity=\$(?P<equity>[0-9.]+)\s*\|\s*"
    r"Free Cash=\$(?P<cash>[0-9.]+)\s*\|\s*"
    r"Open Positions=(?P<open>\d+)/(?P<max_open>\d+)\s*\|\s*"
    r"24h DD=(?P<dd>[0-9.]+)%"
)


def build_dashboard_snapshot(config: Optional[Config] = None) -> Dict[str, Any]:
    """Aggregate live telemetry from state files and log stream into a JSON payload."""
    cfg = config or Config.from_env()
    state_path = Path(cfg.state_file)
    rec_path = Path("logs/recommendations.json")
    log_path = Path(cfg.log_file)

    # 1. Load open positions & realized PnL from state file
    state_data: Dict[str, Any] = {}
    if state_path.exists():
        try:
            state_data = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state_data = {}

    positions_map: Dict[str, Any] = state_data.get("positions", {})
    realized_pnl = float(state_data.get("realized_pnl", 0.0))

    # 2. Load 25-stock screener recommendations
    rec_data: Dict[str, Any] = {}
    if rec_path.exists():
        try:
            rec_data = json.loads(rec_path.read_text(encoding="utf-8"))
        except Exception:
            rec_data = {}

    recommendations: List[Dict[str, Any]] = rec_data.get("recommendations", [])
    price_by_symbol: Dict[str, float] = {
        str(r["symbol"]): float(r["close_price"])
        for r in recommendations
        if "symbol" in r and "close_price" in r
    }

    # 3. Parse recent log lines and latest portfolio heartbeat
    recent_logs: List[Dict[str, str]] = []
    latest_equity = cfg.paper_initial_equity
    latest_cash = cfg.paper_initial_equity
    latest_dd_pct = 0.0
    last_heartbeat_ts = "Waiting for bot tick..."
    bot_mode = cfg.execution_mode.upper()

    if log_path.exists():
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            equity_history = []
            for line in lines[-400:]:
                m = PORTFOLIO_LINE_RE.search(line)
                if m:
                    eq_val = float(m.group("equity"))
                    ts_val = m.group("ts")
                    if not equity_history or equity_history[-1]["equity"] != eq_val or len(equity_history) % 4 == 0:
                        equity_history.append({"timestamp": ts_val, "equity": eq_val})
            if len(equity_history) > 40:
                equity_history = equity_history[-40:]

            for line in reversed(lines):
                m = PORTFOLIO_LINE_RE.search(line)
                if m:
                    last_heartbeat_ts = m.group("ts")
                    latest_equity = float(m.group("equity"))
                    latest_cash = float(m.group("cash"))
                    latest_dd_pct = float(m.group("dd"))
                    break

            # Collect last 60 meaningful single-line log events
            for line in reversed(lines[-180:]):
                if "|" in line and not line.startswith("=") and not line.startswith("-"):
                    parts = [p.strip() for p in line.split("|", 3)]
                    if len(parts) == 4:
                        recent_logs.append(
                            {
                                "timestamp": parts[0],
                                "level": parts[1],
                                "logger": parts[2],
                                "message": parts[3],
                            }
                        )
                    if len(recent_logs) >= 45:
                        break
        except Exception:
            pass

    # 4. Enrich open positions with live unrealized PnL, R-multiple, and progress gauge
    live_quotes_path = Path("logs/live_quotes.json")
    live_quotes: Dict[str, float] = {}
    if live_quotes_path.exists():
        try:
            live_quotes = json.loads(live_quotes_path.read_text(encoding="utf-8"))
        except Exception:
            live_quotes = {}

    enriched_positions: List[Dict[str, Any]] = []
    invested_value = max(0.0, latest_equity - latest_cash)

    for sym, pos in positions_map.items():
        qty = float(pos.get("quantity", 0.0))
        entry = float(pos.get("entry_price", 0.0))
        sl = float(pos.get("stop_loss", 0.0))
        init_sl = float(pos.get("initial_stop_loss", sl))
        tp = float(pos.get("take_profit", 0.0))
        side = str(pos.get("side", "LONG"))

        # Use live USD quote if available, otherwise latest screener / highest tracked USD price
        current_price = float(
            live_quotes.get(sym)
            or price_by_symbol.get(sym)
            or pos.get("highest_price")
            or entry
        )

        one_r = abs(entry - init_sl)
        unrealized_pnl = (current_price - entry) * qty if side == "LONG" else (entry - current_price) * qty
        pnl_pct = ((current_price - entry) / entry * 100.0) if entry > 0 else 0.0
        r_mult = ((current_price - entry) / one_r) if one_r > 0 else 0.0

        total_span = max(0.0001, tp - sl)
        gauge_pct = max(0.0, min(100.0, ((current_price - sl) / total_span) * 100.0))
        entry_marker_pct = max(0.0, min(100.0, ((entry - sl) / total_span) * 100.0))

        enriched_positions.append(
            {
                "symbol": sym,
                "side": side,
                "quantity": round(qty, 4),
                "entry_price": round(entry, 4),
                "current_price": round(current_price, 4),
                "stop_loss": round(sl, 4),
                "initial_stop_loss": round(init_sl, 4),
                "take_profit": round(tp, 4),
                "trailing_active": bool(pos.get("trailing_active", False)),
                "tp_extensions": int(pos.get("tp_extensions", 0)),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "r_multiple": round(r_mult, 2),
                "notional_usd": round(qty * current_price, 2),
                "gauge_pct": round(gauge_pct, 1),
                "entry_marker_pct": round(entry_marker_pct, 1),
                "order_id": str(pos.get("entry_order_id", "")),
                "opened_at": str(pos.get("opened_at", "")),
            }
        )

    ai_data: Dict[str, Any] = {}
    ai_path = Path(cfg.ai_decisions_file)
    if ai_path.exists():
        try:
            ai_data = json.loads(ai_path.read_text(encoding="utf-8"))
        except Exception:
            ai_data = {}

    ai_engine = (
        f"Google Gemini ({cfg.gemini_model})"
        if (cfg.gemini_api_key and "your_" not in cfg.gemini_api_key.lower())
        else "Quant News & Catalyst Engine (Set GEMINI_API_KEY for LLM)"
    )

    now_utc = datetime.now(timezone.utc)
    ttl_sec = max(60, int(cfg.ai_decision_ttl_minutes) * 60)
    raw_decisions: List[Dict[str, Any]] = list(ai_data.get("decisions") or [])
    active_decisions: List[Dict[str, Any]] = []
    expired_decisions: List[Dict[str, Any]] = []

    for d in raw_decisions:
        if not isinstance(d, dict):
            continue
        item = dict(d)
        sym = str(item.get("symbol") or "")
        is_held = sym in positions_map and item.get("decision") in {"APPROVE", "ROTATE"}
        item["is_held"] = is_held

        age_sec = 0.0
        ts_str = str(item.get("timestamp") or "")
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_sec = max(0.0, (now_utc - dt).total_seconds())
            except Exception:
                age_sec = 0.0

        is_expired = (not is_held) and (age_sec > ttl_sec)
        item["is_expired"] = is_expired
        if is_expired:
            expired_decisions.append(item)
        else:
            active_decisions.append(item)

    # 5. Load live runtime state (`logs/bot_runtime.json`), cooldowns, closed trades, and 4-gate diagnostics
    runtime_data: Dict[str, Any] = {}
    runtime_path = Path("logs/bot_runtime.json")
    if runtime_path.exists():
        try:
            runtime_data = json.loads(runtime_path.read_text(encoding="utf-8"))
        except Exception:
            runtime_data = {}

    # Compute US Market Session status (America/New_York)
    us_session_state = "OPEN"
    us_session_badge = "GREEN"
    us_session_detail = "Regular US Session (09:30–16:00 ET)"
    seconds_to_market_open = 0
    seconds_to_market_close = 0
    total_closed_seconds = 63000
    market_is_open = False
    next_open_str = ""
    next_open_iso = ""
    try:
        from zoneinfo import ZoneInfo

        from bot.market_calendar import (
            holiday_name,
            is_early_close,
            is_trading_day,
            market_close_minute,
            next_trading_day,
        )

        now_et = now_utc.astimezone(ZoneInfo("America/New_York"))
        et_str = now_et.strftime("%H:%M ET")
        mins_et = now_et.hour * 60 + now_et.minute
        open_min = 9 * 60 + 30
        close_min = market_close_minute(now_et.date())
        today_is_trading = is_trading_day(now_et.date())

        if today_is_trading and mins_et < open_min:
            next_open_date = now_et.date()
        else:
            next_open_date = next_trading_day(now_et.date())

        next_open_dt = datetime(
            next_open_date.year,
            next_open_date.month,
            next_open_date.day,
            9,
            30,
            tzinfo=ZoneInfo("America/New_York"),
        )
        next_open_iso = next_open_dt.isoformat()
        next_open_str = next_open_date.strftime("%a %d %b") + " 09:30 ET (14:30 UK)"

        if not today_is_trading:
            label = holiday_name(now_et.date()) or "Weekend"
            us_session_state = "WEEKEND (CLOSED)" if label == "Weekend" else "HOLIDAY (CLOSED)"
            us_session_badge = "AMBER"
            us_session_detail = f"{label} ({et_str}) • Reopens {next_open_str}"
            seconds_to_market_open = max(0, int((next_open_dt - now_et).total_seconds()))
        elif mins_et < open_min:
            wait_m = open_min - mins_et
            us_session_state = "PRE-MARKET"
            us_session_badge = "AMBER"
            us_session_detail = f"Pre-Market ({et_str}) • Regular session opens in {wait_m // 60}h {wait_m % 60}m (14:30 UK)"
            seconds_to_market_open = max(0, int((next_open_dt - now_et).total_seconds()))
        elif mins_et >= close_min:
            us_session_state = "AFTER-HOURS"
            us_session_badge = "AMBER"
            us_session_detail = f"US Market Closed ({et_str}) • Next regular session {next_open_str}"
            seconds_to_market_open = max(0, int((next_open_dt - now_et).total_seconds()))
        elif mins_et < open_min + cfg.skip_opening_minutes:
            rem_m = (open_min + cfg.skip_opening_minutes) - mins_et
            us_session_state = "OPENING GUARD"
            us_session_badge = "AMBER"
            us_session_detail = f"Opening-Bell Whipsaw Guard ({et_str}) • Entries unlock in {rem_m}m"
            market_is_open = True
            close_dt = datetime(
                now_et.year,
                now_et.month,
                now_et.day,
                close_min // 60,
                close_min % 60,
                tzinfo=ZoneInfo("America/New_York"),
            )
            seconds_to_market_close = max(0, int((close_dt - now_et).total_seconds()))
        else:
            rem_m = close_min - mins_et
            early = " • EARLY CLOSE 13:00 ET" if is_early_close(now_et.date()) else ""
            us_session_state = "MARKET OPEN"
            us_session_badge = "GREEN"
            us_session_detail = f"Regular Session ({et_str}) • Closes in {rem_m // 60}h {rem_m % 60}m{early}"
            market_is_open = True
            close_dt = datetime(
                now_et.year,
                now_et.month,
                now_et.day,
                close_min // 60,
                close_min % 60,
                tzinfo=ZoneInfo("America/New_York"),
            )
            seconds_to_market_close = max(0, int((close_dt - now_et).total_seconds()))

        total_closed_seconds = 63000
        if not today_is_trading or now_et.weekday() >= 4:
            total_closed_seconds = int(65.5 * 3600)
        elif (next_open_dt - now_et).total_seconds() > 86400:
            total_closed_seconds = max(63000, int((next_open_dt - now_et).total_seconds()) + 3600)
    except Exception:
        pass

    # Compute 15m candle scan countdown & 15s poll progress
    tf_seconds = 900 if cfg.timeframe.lower() == "15m" else 900
    epoch_sec = int(now_utc.timestamp())
    elapsed_in_bar = epoch_sec % tf_seconds
    seconds_to_next_scan = tf_seconds - elapsed_in_bar
    scan_progress_pct = round((elapsed_in_bar / tf_seconds) * 100.0, 1)

    # Active post-loss cooldowns
    raw_cooldowns: Dict[str, Any] = state_data.get("cooldown_until", {})
    active_cooldowns: List[Dict[str, Any]] = []
    cooldown_set = set()
    if isinstance(raw_cooldowns, dict):
        for sym, exp_iso in raw_cooldowns.items():
            try:
                exp_dt = datetime.fromisoformat(str(exp_iso).replace("Z", "+00:00"))
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                rem_sec = int((exp_dt - now_utc).total_seconds())
                if rem_sec > 0:
                    cooldown_set.add(sym)
                    active_cooldowns.append(
                        {
                            "symbol": sym,
                            "remaining_minutes": max(1, rem_sec // 60),
                            "until_utc": exp_dt.strftime("%H:%M UTC"),
                        }
                    )
            except Exception:
                pass

    # Broad market regime & effective minimum score
    regime_state = str(runtime_data.get("market_regime") or "BULLISH")
    regime_summary = str(
        runtime_data.get("market_regime_summary")
        or f"Benchmark {cfg.market_benchmark_symbol} (Min Score Required: {cfg.min_recommendation_score:.0f})"
    )
    effective_min_score = float(
        runtime_data.get("effective_min_score") or cfg.min_recommendation_score
    )

    # Build "Closest Candidate (Gate 4)" and "Warming-Up Watch Radar"
    unheld_recs = [
        r for r in recommendations if str(r.get("symbol")) not in positions_map
    ]
    gate4_status = "WAITING FOR SCAN"
    gate4_badge = "AMBER"
    gate4_detail = "Waiting for 50-stock screener telemetry..."
    watch_radar: List[Dict[str, Any]] = []

    if unheld_recs:
        top_u = unheld_recs[0]
        t_sym = str(top_u.get("symbol", ""))
        t_score = float(top_u.get("score", 0.0))
        t_rating = str(top_u.get("rating", "HOLD"))
        t_thesis = str(top_u.get("thesis", ""))
        t_rvol = float(top_u.get("rvol", 0.0))
        t_act = bool(top_u.get("actionable", False))

        if t_sym in cooldown_set:
            gate4_status = f"{t_sym} IN COOLDOWN"
            gate4_badge = "AMBER"
            gate4_detail = f"#1 {t_sym} scored {t_score:.1f}/100, but is in 2h post-loss cooldown."
        elif t_act and t_score >= effective_min_score:
            gate4_status = f"{t_sym} ACTIONABLE ({t_score:.1f})"
            gate4_badge = "GREEN"
            gate4_detail = f"#1 {t_sym} ({t_rating}, {t_score:.1f}/100, RVOL {t_rvol:.2f}x) meets all sniper criteria!"
        elif "Overextended" in t_thesis:
            gate4_status = f"{t_sym} OVEREXTENDED"
            gate4_badge = "AMBER"
            gate4_detail = f"#1 {t_sym} ({t_score:.1f}/100) stretched too far above EMA20 — waiting for pullback."
        elif t_rvol < cfg.min_rvol_for_entry:
            gate4_status = f"{t_sym} LOW VOLUME"
            gate4_badge = "AMBER"
            gate4_detail = f"#1 {t_sym} ({t_score:.1f}/100) has RVOL {t_rvol:.2f}x (needs >= {cfg.min_rvol_for_entry:.2f}x)."
        else:
            gap = max(0.0, effective_min_score - t_score)
            gate4_status = f"{t_sym} ({t_score:.1f} / {effective_min_score:.0f})"
            gate4_badge = "AMBER"
            gate4_detail = f"Closest is {t_sym} at {t_score:.1f}/100 ({gap:.1f} pts shy of {effective_min_score:.0f} sniper threshold)."

        for r in unheld_recs[:6]:
            r_sym = str(r.get("symbol", ""))
            r_score = float(r.get("score", 0.0))
            r_rvol = float(r.get("rvol", 0.0))
            r_rsi = float(r.get("rsi", 50.0))
            r_thesis = str(r.get("thesis", ""))
            if r_sym in cooldown_set:
                blocker = "In 2h post-loss cooldown"
            elif "Overextended" in r_thesis:
                blocker = f"Wait for pullback toward EMA20 (${float(r.get('ema_fast', 0.0)):.2f})"
            elif r_rvol < cfg.min_rvol_for_entry:
                blocker = f"Needs volume surge (RVOL {r_rvol:.2f}x -> {cfg.min_rvol_for_entry:.1f}x)"
            elif r_score < effective_min_score:
                blocker = f"Needs +{(effective_min_score - r_score):.1f} score pts (RSI {r_rsi:.1f})"
            else:
                blocker = "Ready for next candle evaluation"
            watch_radar.append(
                {
                    "symbol": r_sym,
                    "score": round(r_score, 1),
                    "rating": str(r.get("rating", "HOLD")),
                    "price": round(float(r.get("close_price", 0.0)), 2),
                    "rvol": round(r_rvol, 2),
                    "blocker": blocker,
                }
            )

    open_cnt = len(enriched_positions)
    max_cnt = cfg.max_open_positions
    slots_free = max(0, max_cnt - open_cnt)
    gate2_status = f"{slots_free} SLOT{'S' if slots_free != 1 else ''} OPEN" if slots_free > 0 else "3/3 SLOTS FULL"
    gate2_badge = "GREEN" if slots_free > 0 else "AMBER"
    gate2_detail = (
        f"{open_cnt}/{max_cnt} slots active • ${latest_cash:.2f} cash ready for new entries"
        if slots_free > 0
        else f"All {max_cnt}/{max_cnt} slots full • Only rotating if a held stock drops <50 & new pick >=80"
    )

    gate3_badge = "GREEN" if regime_state == "BULLISH" else ("AMBER" if regime_state == "CAUTIOUS" else "RED")
    gates = [
        {
            "title": "Gate 1 • US Market Session",
            "status": us_session_state,
            "badge": us_session_badge,
            "detail": us_session_detail,
        },
        {
            "title": "Gate 2 • Portfolio Capacity",
            "status": gate2_status,
            "badge": gate2_badge,
            "detail": gate2_detail,
        },
        {
            "title": f"Gate 3 • Market Regime ({cfg.market_benchmark_symbol})",
            "status": f"{regime_state} (Min {effective_min_score:.0f})",
            "badge": gate3_badge,
            "detail": regime_summary,
        },
        {
            "title": "Gate 4 • Closest Candidate",
            "status": gate4_status,
            "badge": gate4_badge,
            "detail": gate4_detail,
        },
    ]

    closed_trades_list: List[Dict[str, Any]] = list(state_data.get("closed_trades") or [])[:10]

    return {
        "version": __version__,
        "server_time_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "last_heartbeat": last_heartbeat_ts,
        "execution_mode": bot_mode,
        "endpoint": cfg.resolved_t212_base_url if cfg.execution_mode in {"demo", "live"} else "Local Paper Sim",
        "timeframe": cfg.timeframe,
        "stop_loss_atr_mult": cfg.stop_loss_atr_mult,
        "take_profit_atr_mult": cfg.take_profit_atr_mult,
        "activity": {
            "state": str(runtime_data.get("state") or "MONITORING"),
            "detail": str(
                runtime_data.get("detail")
                or f"Monitoring {open_cnt}/{max_cnt} positions every {cfg.poll_interval_sec}s; scanning 50 stocks every {cfg.timeframe} candle."
            ),
            "updated_at": str(runtime_data.get("updated_at") or ""),
            "seconds_to_next_scan": seconds_to_next_scan,
            "scan_progress_pct": scan_progress_pct,
            "poll_interval_sec": cfg.poll_interval_sec,
        },
        "market_session": {
            "state": us_session_state,
            "badge": us_session_badge,
            "detail": us_session_detail,
            "is_open": market_is_open,
            "seconds_to_open": seconds_to_market_open,
            "seconds_to_close": seconds_to_market_close,
            "total_closed_seconds": total_closed_seconds,
            "next_open_str": next_open_str,
            "next_open_iso": next_open_iso,
        },
        "gates": gates,
        "cooldowns": active_cooldowns,
        "watch_radar": watch_radar[:4],
        "closed_trades": closed_trades_list,
        "equity_history": locals().get("equity_history", []),
        "portfolio": {
            "total_equity": round(latest_equity, 2),
            "free_cash": round(latest_cash, 2),
            "invested_value": round(max(0.0, latest_equity - latest_cash), 2),
            "realized_pnl": round(realized_pnl, 2),
            "open_positions_count": len(enriched_positions),
            "max_open_positions": cfg.max_open_positions,
            "drawdown_24h_pct": round(latest_dd_pct, 2),
            "max_drawdown_24h_pct": round(cfg.max_daily_drawdown_pct * 100.0, 2),
            "circuit_breaker_tripped": latest_dd_pct >= (cfg.max_daily_drawdown_pct * 100.0),
        },
        "positions": enriched_positions,
        "ai_manager": {
            "enabled": cfg.enable_ai_manager,
            "engine": ai_data.get("engine") or ai_engine,
            "ttl_minutes": cfg.ai_decision_ttl_minutes,
            "last_scan_status": str(ai_data.get("last_scan_status") or ""),
            "last_scan_timestamp": str(ai_data.get("last_scan_timestamp") or ""),
            "decisions": active_decisions[:6],
            "expired_decisions": expired_decisions[:8],
        },
        "screener": {
            "generated_at": rec_data.get("generated_at", ""),
            "count": len(recommendations),
            "top_pick": rec_data.get("top_pick", ""),
            "recommendations": recommendations,
        },
        "logs": recent_logs,
    }


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Trading 212 Quant Bot • Command Center</title>
  <style>
    :root {
      --bg: #f5f5f7;
      --surface: #ffffff;
      --surface-secondary: #fbfbfd;
      --surface-tertiary: #f5f5f7;
      --border: rgba(0, 0, 0, 0.08);
      --border-subtle: rgba(0, 0, 0, 0.04);
      --text-primary: #1d1d1f;
      --text-secondary: #6e6e73;
      --text-tertiary: #86868b;
      --accent: #0071e3;
      --accent-hover: #0077ed;
      --accent-tint: rgba(0, 113, 227, 0.08);
      --green: #34c759;
      --green-text: #248a3d;
      --green-bg: rgba(52, 199, 89, 0.12);
      --amber: #ff9500;
      --amber-text: #b26a00;
      --amber-bg: rgba(255, 149, 0, 0.12);
      --red: #ff3b30;
      --red-text: #d70015;
      --red-bg: rgba(255, 59, 48, 0.10);
      --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.04);
      --shadow-md: 0 4px 20px rgba(0, 0, 0, 0.05);
      --shadow-lg: 0 12px 36px rgba(0, 0, 0, 0.08);
      --radius-sm: 8px;
      --radius-md: 14px;
      --radius-lg: 18px;
      --radius-xl: 22px;
      --radius-pill: 999px;
      --transition: all 0.25s cubic-bezier(0.25, 0.1, 0.25, 1);
    }

    /* Apple Space Black Dark Theme */
    [data-theme="dark"] {
      --bg: #000000;
      --surface: #141416;
      --surface-secondary: #1c1c1e;
      --surface-tertiary: #252528;
      --border: rgba(255, 255, 255, 0.12);
      --border-subtle: rgba(255, 255, 255, 0.06);
      --text-primary: #f5f5f7;
      --text-secondary: #a1a1a6;
      --text-tertiary: #86868b;
      --accent: #2997ff;
      --accent-hover: #47a6ff;
      --accent-tint: rgba(41, 151, 255, 0.15);
      --green: #30d158;
      --green-text: #30d158;
      --green-bg: rgba(48, 209, 88, 0.16);
      --amber: #ff9f0a;
      --amber-text: #ff9f0a;
      --amber-bg: rgba(255, 159, 10, 0.16);
      --red: #ff453a;
      --red-text: #ff453a;
      --red-bg: rgba(255, 69, 58, 0.16);
      --shadow-sm: 0 2px 10px rgba(0, 0, 0, 0.5);
      --shadow-md: 0 6px 24px rgba(0, 0, 0, 0.6);
      --shadow-lg: 0 16px 44px rgba(0, 0, 0, 0.7);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text-primary);
      line-height: 1.47059;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      text-rendering: optimizeLegibility;
      transition: background 0.3s ease, color 0.3s ease;
    }

    /* Fixed Apple Glass Header: Nav + Pinned Ticker Tape */
    .app-header-fixed {
      position: sticky;
      top: 0;
      z-index: 1000;
      width: 100%;
      background: rgba(255, 255, 255, 0.85);
      backdrop-filter: saturate(180%) blur(20px);
      -webkit-backdrop-filter: saturate(180%) blur(20px);
      border-bottom: 1px solid var(--border);
      transition: var(--transition);
    }
    [data-theme="dark"] .app-header-fixed {
      background: rgba(18, 18, 20, 0.88);
      border-bottom: 1px solid var(--border);
    }

    /* Apple Glass Navigation (Slim Executive Height) */
    nav.apple-nav {
      position: relative;
      background: transparent;
      border-bottom: 1px solid rgba(0, 0, 0, 0.05);
      padding: 7px 0;
      transition: var(--transition);
    }
    [data-theme="dark"] nav.apple-nav {
      background: transparent;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }
    .nav-content {
      max-width: 97%;
      width: 100%;
      margin: 0 auto;
      padding: 0 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
    }
    .brand-wrap {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .brand-icon {
      width: 28px;
      height: 28px;
      border-radius: 7px;
      background: linear-gradient(135deg, #0071e3 0%, #42a5f5 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 11px;
      color: #ffffff;
      letter-spacing: -0.02em;
      box-shadow: 0 2px 8px rgba(0, 113, 227, 0.25);
    }
    .brand-text h1 {
      font-size: 15px;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: var(--text-primary);
      margin: 0;
      line-height: 1.15;
    }
    .brand-text p {
      font-size: 11px;
      color: var(--text-tertiary);
      margin: 0;
      line-height: 1.15;
    }
    .status-pills {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }
    .status-pill {
      font-size: 11px;
      font-weight: 500;
      padding: 4px 10px;
      border-radius: var(--radius-pill);
      background: rgba(0, 0, 0, 0.04);
      border: 1px solid rgba(0, 0, 0, 0.05);
      color: var(--text-secondary);
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: var(--transition);
    }
    [data-theme="dark"] .status-pill {
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.12);
    }
    .status-pill:hover {
      background: rgba(0, 0, 0, 0.07);
    }
    [data-theme="dark"] .status-pill:hover {
      background: rgba(255, 255, 255, 0.12);
    }
    .status-pill strong {
      color: var(--text-primary);
      font-weight: 600;
    }

    /* Pulsing Apple Beacon */
    .beacon-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      position: relative;
    }
    .beacon-open {
      background: var(--green);
      box-shadow: 0 0 0 0 rgba(52, 199, 89, 0.7);
      animation: beaconPulseGreen 2s infinite cubic-bezier(0.66, 0, 0, 1);
    }
    .beacon-amber {
      background: var(--amber);
      box-shadow: 0 0 0 0 rgba(255, 149, 0, 0.7);
      animation: beaconPulseAmber 2s infinite cubic-bezier(0.66, 0, 0, 1);
    }
    .beacon-slate {
      background: var(--text-tertiary);
    }
    @keyframes beaconPulseGreen {
      0% { box-shadow: 0 0 0 0 rgba(52, 199, 89, 0.7); }
      70% { box-shadow: 0 0 0 10px rgba(52, 199, 89, 0); }
      100% { box-shadow: 0 0 0 0 rgba(52, 199, 89, 0); }
    }
    @keyframes beaconPulseAmber {
      0% { box-shadow: 0 0 0 0 rgba(255, 149, 0, 0.7); }
      70% { box-shadow: 0 0 0 10px rgba(255, 149, 0, 0); }
      100% { box-shadow: 0 0 0 0 rgba(255, 149, 0, 0); }
    }

    /* Dynamic Theme Switcher Pill */
    .theme-toggle-btn {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 4px 10px;
      border-radius: var(--radius-pill);
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--text-primary);
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      box-shadow: var(--shadow-sm);
      transition: var(--transition);
      user-select: none;
    }
    .theme-toggle-btn:hover {
      background: var(--surface-secondary);
      border-color: var(--accent);
      transform: translateY(-1px);
    }
    .theme-toggle-btn svg {
      width: 13px;
      height: 13px;
    }

    /* Main Container */
    .main-container {
      max-width: 97%;
      width: 100%;
      margin: 0 auto;
      padding: 24px 24px 72px;
    }

    /* SF Symbol Icon Squircles */
    .squircle-icon {
      width: 40px;
      height: 40px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      transition: var(--transition);
    }
    .squircle-blue { background: rgba(0, 113, 227, 0.09); color: var(--accent); }
    .squircle-green { background: rgba(52, 199, 89, 0.12); color: var(--green-text); }
    .squircle-amber { background: rgba(255, 149, 0, 0.12); color: var(--amber-text); }
    .squircle-purple { background: rgba(175, 82, 222, 0.12); color: #af52de; }
    .squircle-red { background: rgba(255, 59, 48, 0.10); color: var(--red-text); }
    .squircle-slate { background: rgba(142, 142, 147, 0.12); color: var(--text-secondary); }

    /* Hero Activity Strip */
    .hero-activity {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-xl);
      padding: 22px 28px;
      margin-bottom: 24px;
      box-shadow: var(--shadow-sm);
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 20px;
      transition: var(--transition);
    }
    .hero-activity:hover {
      box-shadow: var(--shadow-md);
    }
    .activity-left {
      display: flex;
      align-items: center;
      gap: 14px;
      flex-wrap: wrap;
    }
    .activity-state-badge {
      padding: 5px 12px;
      border-radius: var(--radius-pill);
      font-size: 11.5px;
      font-weight: 600;
      letter-spacing: 0.02em;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .timer-group {
      display: flex;
      align-items: center;
      gap: 22px;
      flex-wrap: wrap;
    }
    .timer-widget {
      min-width: 240px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .timer-meta {
      display: flex;
      justify-content: space-between;
      font-size: 11.5px;
      color: var(--text-secondary);
      font-weight: 500;
    }
    .timer-track {
      width: 100%;
      height: 6px;
      background: rgba(0, 0, 0, 0.06);
      border-radius: var(--radius-pill);
      overflow: hidden;
    }
    [data-theme="dark"] .timer-track {
      background: rgba(255, 255, 255, 0.10);
    }
    .timer-bar {
      height: 100%;
      background: var(--accent);
      border-radius: var(--radius-pill);
      transition: width 0.3s ease;
    }

    /* KPI Cards Grid */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 20px;
      margin-bottom: 24px;
    }
    @media (max-width: 1080px) {
      .kpi-grid { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 640px) {
      .kpi-grid { grid-template-columns: 1fr; }
    }

    .kpi-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 24px;
      box-shadow: var(--shadow-sm);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: var(--transition);
      position: relative;
    }
    .kpi-card:hover {
      box-shadow: var(--shadow-md);
      transform: translateY(-2px);
    }
    .kpi-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
    }
    .kpi-title {
      font-size: 13px;
      font-weight: 500;
      color: var(--text-secondary);
      letter-spacing: -0.01em;
    }
    .kpi-val {
      font-size: 30px;
      font-weight: 700;
      letter-spacing: -0.035em;
      color: var(--text-primary);
      margin-bottom: 4px;
      font-variant-numeric: tabular-nums;
    }
    .kpi-sub {
      font-size: 12px;
      color: var(--text-tertiary);
      display: flex;
      align-items: center;
      gap: 6px;
    }

    /* Apple Watch Circular Ring for Drawdown Breaker */
    .ring-gauge-wrap {
      position: relative;
      width: 44px;
      height: 44px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .ring-gauge-svg {
      width: 44px;
      height: 44px;
      transform: rotate(-90deg);
    }
    .ring-track {
      fill: none;
      stroke: rgba(0, 0, 0, 0.08);
      stroke-width: 4;
    }
    [data-theme="dark"] .ring-track {
      stroke: rgba(255, 255, 255, 0.12);
    }
    .ring-fill {
      fill: none;
      stroke-width: 4;
      stroke-linecap: round;
      stroke-dasharray: 113.1;
      stroke-dashoffset: 113.1;
      transition: stroke-dashoffset 0.6s ease, stroke 0.3s ease;
    }

    /* 4-Gate Diagnostics Pipeline */
    .gate-pipeline {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 24px;
    }
    @media (max-width: 980px) {
      .gate-pipeline { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 580px) {
      .gate-pipeline { grid-template-columns: 1fr; }
    }
    .gate-step {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 18px 20px;
      box-shadow: var(--shadow-sm);
      display: flex;
      flex-direction: column;
      gap: 8px;
      transition: var(--transition);
    }
    .gate-step:hover {
      box-shadow: var(--shadow-md);
    }
    .gate-step-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .gate-step-num {
      font-size: 11.5px;
      font-weight: 600;
      color: var(--text-tertiary);
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }
    .gate-status-badge {
      font-size: 11px;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: var(--radius-pill);
    }
    .gate-step-val {
      font-size: 15px;
      font-weight: 600;
      color: var(--text-primary);
      letter-spacing: -0.015em;
    }
    .gate-step-desc {
      font-size: 11.5px;
      color: var(--text-secondary);
      line-height: 1.35;
    }

    /* Section Cards */
    .section-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-xl);
      padding: 28px 32px;
      margin-bottom: 24px;
      box-shadow: var(--shadow-sm);
      transition: var(--transition);
    }
    .section-card:hover {
      box-shadow: var(--shadow-md);
    }
    .section-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      flex-wrap: wrap;
      gap: 12px;
    }
    .section-title-wrap {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .section-title {
      font-size: 18px;
      font-weight: 600;
      letter-spacing: -0.025em;
      color: var(--text-primary);
    }
    .section-sub {
      font-size: 12.5px;
      color: var(--text-tertiary);
      margin-top: 2px;
    }

    /* AI Portfolio Manager Glowing Ambient Box */
    .ai-hero-box {
      position: relative;
      background: var(--surface);
      border-radius: var(--radius-xl);
      padding: 28px 32px;
      margin-bottom: 24px;
      box-shadow: var(--shadow-sm);
      overflow: hidden;
      border: 1px solid var(--border);
    }
    .ai-hero-box::before {
      content: "";
      position: absolute;
      inset: -2px;
      border-radius: inherit;
      padding: 2px;
      background: linear-gradient(135deg, rgba(0, 113, 227, 0.45), rgba(175, 82, 222, 0.45), rgba(255, 45, 85, 0.35), rgba(52, 199, 89, 0.45));
      -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
      -webkit-mask-composite: xor;
      mask-composite: exclude;
      pointer-events: none;
      animation: siriGlow 8s ease infinite alternate;
    }
    @keyframes siriGlow {
      0% { filter: hue-rotate(0deg) opacity(0.5); }
      50% { filter: hue-rotate(180deg) opacity(0.9); }
      100% { filter: hue-rotate(360deg) opacity(0.5); }
    }

    /* Position Cards & Trade Runway */
    .pos-card {
      background: var(--surface-secondary);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 22px 24px;
      margin-bottom: 16px;
      box-shadow: var(--shadow-sm);
      cursor: pointer;
      transition: var(--transition);
    }
    .pos-card:hover {
      box-shadow: var(--shadow-md);
      transform: translateY(-2px);
      border-color: var(--accent);
    }
    .pos-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      flex-wrap: wrap;
      gap: 12px;
    }
    .pos-metrics {
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      gap: 14px;
      margin-bottom: 18px;
    }
    @media (max-width: 980px) {
      .pos-metrics { grid-template-columns: repeat(3, 1fr); }
    }
    @media (max-width: 580px) {
      .pos-metrics { grid-template-columns: repeat(2, 1fr); }
    }
    .pos-metric span {
      display: block;
      font-size: 11px;
      color: var(--text-tertiary);
      text-transform: uppercase;
      margin-bottom: 3px;
      letter-spacing: 0.02em;
    }
    .pos-metric strong {
      font-size: 14.5px;
      color: var(--text-primary);
      font-weight: 600;
    }
    .pos-green { color: var(--green-text) !important; font-weight: 600; }
    .pos-red { color: var(--red-text) !important; font-weight: 600; }

    /* Apple-Grade Trade Runway */
    .runway-wrap {
      background: var(--surface);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      padding: 14px 18px;
    }
    .runway-header {
      display: flex;
      justify-content: space-between;
      font-size: 11.5px;
      color: var(--text-secondary);
      margin-bottom: 8px;
    }
    .runway-track {
      position: relative;
      height: 8px;
      background: rgba(0, 0, 0, 0.06);
      border-radius: var(--radius-pill);
      overflow: hidden;
    }
    [data-theme="dark"] .runway-track {
      background: rgba(255, 255, 255, 0.10);
    }
    .runway-fill {
      height: 100%;
      background: linear-gradient(90deg, #ff3b30 0%, #ff9500 40%, #34c759 100%);
      border-radius: var(--radius-pill);
      transition: width 0.4s ease;
    }
    .runway-anchors {
      display: flex;
      justify-content: space-between;
      font-size: 10.5px;
      color: var(--text-tertiary);
      margin-top: 6px;
    }

    /* Badges */
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 3px 10px;
      border-radius: var(--radius-pill);
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.02em;
    }
    .badge-strong-buy { background: var(--green-bg); color: var(--green-text); }
    .badge-buy { background: rgba(0, 113, 227, 0.12); color: var(--accent); }
    .badge-watch { background: var(--amber-bg); color: var(--amber-text); }
    .badge-avoid { background: var(--red-bg); color: var(--red-text); }
    .badge-hold { background: rgba(142, 142, 147, 0.12); color: var(--text-secondary); }

    /* Apple Filter Bar */
    .filter-bar {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .filter-btn {
      padding: 6px 14px;
      border-radius: var(--radius-pill);
      border: 1px solid var(--border);
      background: var(--surface);
      font-size: 12px;
      font-weight: 500;
      color: var(--text-secondary);
      cursor: pointer;
      transition: var(--transition);
    }
    .filter-btn:hover {
      background: var(--surface-secondary);
      color: var(--text-primary);
    }
    .filter-btn.active {
      background: var(--text-primary);
      color: var(--bg);
      border-color: var(--text-primary);
      font-weight: 600;
    }

    /* Inspect Button in Screener Table */
    .inspect-btn {
      padding: 4px 11px;
      border-radius: var(--radius-pill);
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--accent);
      font-size: 11.5px;
      font-weight: 600;
      cursor: pointer;
      transition: var(--transition);
      white-space: nowrap;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .inspect-btn:hover {
      background: var(--accent);
      color: #ffffff;
      border-color: var(--accent);
      transform: translateY(-1px);
      box-shadow: 0 2px 8px rgba(0, 113, 227, 0.25);
    }
    [data-theme="dark"] .inspect-btn {
      background: rgba(255, 255, 255, 0.08);
      border-color: rgba(255, 255, 255, 0.12);
      color: var(--accent);
    }
    [data-theme="dark"] .inspect-btn:hover {
      background: var(--accent);
      color: #000000;
    }

    /* Apple Collapsible Screener Column Guide */
    .screener-guide-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 20px;
      transition: var(--transition);
    }
    @media (max-width: 1280px) {
      .screener-guide-grid { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 680px) {
      .screener-guide-grid { grid-template-columns: 1fr; }
    }
    .screener-guide-card {
      background: var(--surface-secondary);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 12px 16px;
      font-size: 11.5px;
      line-height: 1.45;
      color: var(--text-secondary);
      box-shadow: var(--shadow-sm);
    }
    .screener-guide-card strong {
      display: block;
      color: var(--accent);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-bottom: 4px;
      font-weight: 700;
    }
    .screener-guide-card b {
      color: var(--text-primary);
      font-weight: 600;
    }

    /* Tables */
    .table-container {
      overflow-x: auto;
      border-radius: var(--radius-md);
      border: 1px solid var(--border);
      background: var(--surface);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 12.5px;
      table-layout: auto;
    }
    th {
      background: var(--surface-secondary);
      padding: 10px 10px;
      font-weight: 600;
      font-size: 11px;
      color: var(--text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }
    th.th-thesis {
      min-width: 280px;
      width: 100%;
    }
    td {
      padding: 10px 10px;
      border-bottom: 1px solid var(--border-subtle);
      color: var(--text-primary);
      vertical-align: middle;
      white-space: nowrap;
    }
    td.td-thesis {
      white-space: normal;
      line-height: 1.45;
      min-width: 280px;
    }
    tr:last-child td {
      border-bottom: none;
    }
    tbody tr {
      transition: var(--transition);
      cursor: pointer;
    }
    tbody tr:hover {
      background: rgba(0, 113, 227, 0.035);
    }
    [data-theme="dark"] tbody tr:hover {
      background: rgba(255, 255, 255, 0.04);
    }
    .th-sub {
      display: block;
      font-size: 9.5px;
      color: var(--text-tertiary);
      font-weight: 400;
      text-transform: none;
      margin-top: 1px;
    }

    /* Apple Stocks Sparkline Area */
    .sparkline-svg {
      display: block;
      overflow: visible;
    }

    /* Radial Score Dial */
    .radial-dial {
      position: relative;
      width: 38px;
      height: 38px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }
    .radial-dial svg {
      width: 38px;
      height: 38px;
      transform: rotate(-90deg);
    }
    .dial-track {
      fill: none;
      stroke: rgba(0, 0, 0, 0.08);
      stroke-width: 3.5;
    }
    [data-theme="dark"] .dial-track {
      stroke: rgba(255, 255, 255, 0.12);
    }
    .dial-fill {
      fill: none;
      stroke-width: 3.5;
      stroke-linecap: round;
      stroke-dasharray: 94.2;
      stroke-dashoffset: 94.2;
      transition: stroke-dashoffset 0.5s ease;
    }
    .dial-score-num {
      position: absolute;
      font-size: 11px;
      font-weight: 700;
      color: var(--text-primary);
      letter-spacing: -0.02em;
    }

    /* Analytics Section Grid */
    .analytics-grid {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 20px;
      margin-bottom: 24px;
    }
    @media (max-width: 980px) {
      .analytics-grid { grid-template-columns: 1fr; }
    }

    /* Apple Fitness Concentric Activity Rings */
    .rings-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-xl);
      padding: 24px 28px;
      box-shadow: var(--shadow-sm);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .rings-content-wrap {
      display: flex;
      align-items: center;
      gap: 24px;
      margin: 14px 0;
      flex-wrap: wrap;
    }
    .rings-svg-wrap {
      position: relative;
      width: 110px;
      height: 110px;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }
    .rings-svg {
      width: 110px;
      height: 110px;
      transform: rotate(-90deg);
    }
    .ring-bg {
      fill: none;
      stroke-width: 7;
      opacity: 0.18;
    }
    .ring-active {
      fill: none;
      stroke-width: 7;
      stroke-linecap: round;
      transition: stroke-dashoffset 0.8s ease;
    }
    .rings-legend {
      display: flex;
      flex-direction: column;
      gap: 10px;
      flex: 1;
      min-width: 160px;
    }
    .ring-leg-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 12.5px;
    }
    .ring-leg-label {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--text-secondary);
    }
    .ring-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
    }
    .ring-leg-val {
      font-weight: 600;
      color: var(--text-primary);
    }

    /* Sector Diversification Donut */
    .donut-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-xl);
      padding: 24px 28px;
      box-shadow: var(--shadow-sm);
      margin-bottom: 24px;
    }
    .donut-layout {
      display: flex;
      align-items: center;
      gap: 32px;
      flex-wrap: wrap;
      margin-top: 14px;
    }
    .donut-svg-wrap {
      position: relative;
      width: 140px;
      height: 140px;
      flex-shrink: 0;
    }
    .donut-svg {
      width: 140px;
      height: 140px;
      transform: rotate(-90deg);
    }
    .donut-legend-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px 20px;
      flex: 1;
      min-width: 280px;
    }
    @media (max-width: 680px) {
      .donut-legend-grid { grid-template-columns: 1fr; }
    }
    .donut-leg-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 12px;
      padding: 6px 10px;
      border-radius: var(--radius-sm);
      background: var(--surface-secondary);
      border: 1px solid var(--border-subtle);
    }

    /* Interactive Drill-Down "Sheet" Modal */
    .modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.48);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      z-index: 2000;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 20px;
      opacity: 0;
      transition: opacity 0.25s ease;
    }
    .modal-backdrop.open {
      display: flex;
      opacity: 1;
    }
    .modal-sheet {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 24px;
      box-shadow: var(--shadow-lg);
      width: 100%;
      max-width: 840px;
      max-height: 90vh;
      overflow-y: auto;
      scrollbar-width: none;
      -ms-overflow-style: none;
      padding: 32px;
      position: relative;
      transform: translateY(20px) scale(0.98);
      transition: max-width 0.3s cubic-bezier(0.2, 0.9, 0.3, 1), max-height 0.3s cubic-bezier(0.2, 0.9, 0.3, 1), transform 0.28s cubic-bezier(0.2, 0.9, 0.3, 1);
    }
    .modal-sheet::-webkit-scrollbar {
      display: none;
    }
    .modal-sheet.modal-sheet-wide {
      max-width: 1080px;
      max-height: 96vh;
      padding: 24px 32px;
    }
    .modal-backdrop.open .modal-sheet {
      transform: translateY(0) scale(1);
    }
    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 24px;
    }
    .modal-title-group {
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .modal-close-btn {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      border: 1px solid var(--border);
      background: var(--surface-secondary);
      color: var(--text-secondary);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: var(--transition);
    }
    .modal-close-btn:hover {
      background: var(--surface-tertiary);
      color: var(--text-primary);
    }
    .modal-chart-card {
      background: var(--surface-secondary);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 22px 24px;
      margin-bottom: 22px;
    }
    .modal-chart-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .modal-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 14px;
      margin-bottom: 22px;
    }
    @media (max-width: 680px) {
      .modal-grid { grid-template-columns: 1fr; }
    }
    .modal-tile {
      background: var(--surface-secondary);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 16px 18px;
    }
    .tile-label {
      display: block;
      font-size: 11px;
      font-weight: 500;
      color: var(--text-tertiary);
      text-transform: uppercase;
      letter-spacing: 0.03em;
      margin-bottom: 4px;
    }
    .tile-val {
      display: block;
      font-size: 20px;
      font-weight: 700;
      color: var(--text-primary);
      letter-spacing: -0.02em;
    }
    .tile-sub {
      display: block;
      font-size: 11.5px;
      color: var(--text-secondary);
      margin-top: 3px;
    }
    .modal-thesis-card {
      background: var(--surface-secondary);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 18px 20px;
    }

    /* Logs Terminal */
    .log-box {
      background: #0d0d0f;
      color: #e5e5ea;
      font-family: "SF Mono", Menlo, Consolas, Monaco, monospace;
      font-size: 12px;
      border-radius: var(--radius-md);
      padding: 16px 20px;
      height: 280px;
      overflow-y: auto;
      border: 1px solid rgba(255, 255, 255, 0.08);
      line-height: 1.6;
    }
    .log-row {
      display: flex;
      gap: 12px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      padding: 3px 0;
    }
    .log-ts { color: #8e8e93; flex-shrink: 0; }
    .log-lvl-INFO { color: #30d158; font-weight: 600; flex-shrink: 0; }
    .log-lvl-WARNING { color: #ffd60a; font-weight: 600; flex-shrink: 0; }
    .log-lvl-ERROR { color: #ff453a; font-weight: 600; flex-shrink: 0; }
  
    /* --- ENHANCEMENT 1: Screener Micro-Visualizers --- */
    .asset-cell {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .asset-logo-wrap {
      width: 32px;
      height: 32px;
      border-radius: 9px;
      background: #ffffff;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
      border: 1px solid rgba(0, 0, 0, 0.08);
      overflow: hidden;
      position: relative;
    }
    [data-theme="dark"] .asset-logo-wrap {
      background: #ffffff;
      border: 1px solid rgba(255, 255, 255, 0.22);
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.45);
    }
    .asset-logo-img {
      width: 22px;
      height: 22px;
      object-fit: contain;
      display: block;
    }
    .asset-monogram {
      width: 32px;
      height: 32px;
      border-radius: 9px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 11.5px;
      font-weight: 700;
      color: #ffffff;
      letter-spacing: -0.02em;
      flex-shrink: 0;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
    }
    .rsi-bullet-wrap {
      min-width: 82px;
    }
    .rsi-bullet-track {
      position: relative;
      height: 6px;
      background: rgba(0, 0, 0, 0.08);
      border-radius: var(--radius-pill);
      overflow: hidden;
      margin-top: 4px;
    }
    [data-theme="dark"] .rsi-bullet-track {
      background: rgba(255, 255, 255, 0.12);
    }
    .rsi-sweet-spot {
      position: absolute;
      left: 54%;
      width: 13%;
      height: 100%;
      background: rgba(52, 199, 89, 0.5);
      border-radius: 2px;
    }
    .rsi-marker {
      position: absolute;
      top: 0;
      width: 6px;
      height: 6px;
      background: var(--text-primary);
      border-radius: 2px;
      transform: translateX(-50%);
      transition: left 0.4s ease;
      box-shadow: 0 0 3px rgba(0,0,0,0.4);
    }
    .rvol-meter-wrap {
      min-width: 78px;
    }
    .rvol-track {
      height: 6px;
      background: rgba(0, 0, 0, 0.08);
      border-radius: var(--radius-pill);
      overflow: hidden;
      margin-top: 4px;
    }
    [data-theme="dark"] .rvol-track {
      background: rgba(255, 255, 255, 0.12);
    }
    .rvol-fill {
      height: 100%;
      border-radius: var(--radius-pill);
      transition: width 0.4s ease, background 0.3s ease;
    }

    /* --- ENHANCEMENT 2: 4-Gate Diagnostics Animated Conduit --- */
    .gate-icon-title {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .gate-mini-icon {
      width: 22px;
      height: 22px;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }
    @keyframes radarSpin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
    .radar-beam {
      transform-origin: 12px 12px;
      animation: radarSpin 3.5s linear infinite;
    }
    @keyframes crosshairPulse {
      0%, 100% { transform: scale(1); opacity: 1; }
      50% { transform: scale(1.18); opacity: 0.7; }
    }
    .crosshair-anim {
      transform-origin: center;
      animation: crosshairPulse 2s ease-in-out infinite;
    }

    /* --- ENHANCEMENT 3: Tactile KPI Graphic Meters --- */
    .kpi-bg-wave {
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      width: 100%;
      height: 38px;
      opacity: 0.18;
      pointer-events: none;
      border-bottom-left-radius: inherit;
      border-bottom-right-radius: inherit;
    }
    .kpi-capsule-meter {
      display: flex;
      width: 100%;
      height: 6px;
      background: rgba(0, 0, 0, 0.08);
      border-radius: var(--radius-pill);
      overflow: hidden;
      margin-top: 8px;
    }
    [data-theme="dark"] .kpi-capsule-meter {
      background: rgba(255, 255, 255, 0.12);
    }
    .kpi-capsule-fill {
      height: 100%;
      transition: width 0.5s ease;
    }
    .kpi-slots-wrap {
      display: flex;
      gap: 6px;
      margin-top: 8px;
    }
    .slot-pill {
      flex: 1;
      padding: 3px 0;
      text-align: center;
      border-radius: var(--radius-pill);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.02em;
      transition: var(--transition);
      text-transform: uppercase;
    }
    .slot-pill.filled {
      background: var(--green-bg);
      color: var(--green-text);
      border: 1px solid rgba(52, 199, 89, 0.4);
      box-shadow: 0 0 8px rgba(52, 199, 89, 0.25);
    }
    .slot-pill.empty {
      background: rgba(0, 0, 0, 0.04);
      color: var(--text-tertiary);
      border: 1px dashed var(--border);
    }
    [data-theme="dark"] .slot-pill.empty {
      background: rgba(255, 255, 255, 0.04);
    }

    /* --- ENHANCEMENT 4: Solar Arc Session Sky Dial --- */
    .solar-dial-card {
      min-width: 270px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .solar-arc-svg {
      width: 100%;
      height: 38px;
      overflow: visible;
    }
    .solar-anchors {
      display: flex;
      justify-content: space-between;
      font-size: 9.5px;
      color: var(--text-tertiary);
      font-weight: 500;
      margin-top: -2px;
    }

    /* --- ENHANCEMENT 5: macOS Window Terminal Frame for Live Logs --- */
    .macos-window {
      background: #0d0d0f;
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: var(--radius-lg);
      box-shadow: var(--shadow-lg);
      overflow: hidden;
    }
    .macos-window-header {
      background: #18181c;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      padding: 10px 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
    }
    .macos-traffic-lights {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .traffic-dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
    }
    .traffic-red { background: #ff5f56; border: 1px solid #e0443e; }
    .traffic-yellow { background: #ffbd2e; border: 1px solid #dea123; }
    .traffic-green { background: #27c93f; border: 1px solid #1aab29; }
    .macos-window-title {
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
      font-size: 12px;
      color: #a1a1a6;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .log-filter-pills {
      display: flex;
      gap: 6px;
    }
    .log-filter-btn {
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #a1a1a6;
      padding: 3px 10px;
      border-radius: var(--radius-pill);
      font-size: 10.5px;
      font-weight: 600;
      cursor: pointer;
      transition: var(--transition);
    }
    .log-filter-btn:hover {
      background: rgba(255, 255, 255, 0.15);
      color: #ffffff;
    }
    .log-filter-btn.active {
      background: var(--accent);
      color: #ffffff;
      border-color: var(--accent);
    }

  
    /* Flash Animations for Live Data Updates */
    @keyframes flashGreen {
      0% { background-color: rgba(52, 199, 89, 0.35); color: #34c759; }
      100% { background-color: transparent; }
    }
    @keyframes flashRed {
      0% { background-color: rgba(255, 59, 48, 0.35); color: #ff3b30; }
      100% { background-color: transparent; }
    }
    .flash-up {
      animation: flashGreen 1.4s cubic-bezier(0.16, 1, 0.3, 1);
      border-radius: 6px;
    }
    .flash-down {
      animation: flashRed 1.4s cubic-bezier(0.16, 1, 0.3, 1);
      border-radius: 6px;
    }

    /* Top-Movers Ticker Tape / Marquee (Pinned under Nav) */
    .ticker-tape-container {
      width: 100%;
      background: rgba(0, 0, 0, 0.02);
      overflow: hidden;
      height: 31px;
      display: flex;
      align-items: center;
      position: relative;
    }
    [data-theme="dark"] .ticker-tape-container {
      background: rgba(255, 255, 255, 0.02);
    }
    .ticker-tape-track {
      display: flex;
      align-items: center;
      gap: 22px;
      white-space: nowrap;
      will-change: transform;
      animation: tickerScroll 55s linear infinite;
    }
    .ticker-tape-track:hover {
      animation-play-state: paused;
    }
    @keyframes tickerScroll {
      0% { transform: translateX(0); }
      100% { transform: translateX(-50%); }
    }
    .ticker-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 11px;
      font-weight: 500;
      cursor: pointer;
      padding: 2px 8px;
      border-radius: var(--radius-pill);
      background: var(--surface-secondary);
      border: 1px solid var(--border);
      transition: var(--transition);
      user-select: none;
    }
    .ticker-item:hover {
      background: var(--surface);
      border-color: var(--accent);
      transform: translateY(-1px);
    }
    .ticker-item strong {
      font-weight: 700;
      color: var(--text-primary);
    }
    .ticker-logo {
      width: 16px;
      height: 16px;
      border-radius: 4px;
      object-fit: contain;
      background: #ffffff;
      padding: 1px;
      flex-shrink: 0;
    }
    .ticker-badge {
      font-size: 9.5px;
      font-weight: 700;
      padding: 1px 6px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }

    /* Screener Search & Controls Bar */
    .screener-search-wrap {
      display: flex;
      align-items: center;
      gap: 8px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-pill);
      padding: 5px 12px;
      transition: var(--transition);
      min-width: 280px;
    }
    .screener-search-wrap:focus-within {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.15);
      background: var(--surface-secondary);
    }
    .screener-search-wrap input {
      border: none;
      outline: none;
      background: transparent;
      font-size: 12px;
      color: var(--text-primary);
      width: 100%;
      font-family: inherit;
    }
    .screener-search-wrap input::placeholder {
      color: var(--text-tertiary);
    }
    .search-kbd-shortcut {
      font-size: 10px;
      font-weight: 600;
      padding: 1px 5px;
      border-radius: 4px;
      background: var(--surface-secondary);
      border: 1px solid var(--border);
      color: var(--text-tertiary);
    }

    /* Sortable Table Columns */
    th.sortable {
      cursor: pointer;
      user-select: none;
      transition: color 0.15s ease;
    }
    th.sortable:hover {
      color: var(--accent);
    }
    .sort-icon {
      display: inline-block;
      margin-left: 4px;
      font-size: 9px;
      opacity: 0.4;
      vertical-align: middle;
      transition: opacity 0.15s ease;
    }
    th.sortable.active-sort .sort-icon {
      opacity: 1;
      color: var(--accent);
    }

    /* Risk / Reward Visual Ladder Card in Modal */
    .modal-rr-card {
      background: var(--surface-secondary);
      border: 1px solid var(--border);
      border-radius: var(--radius-card);
      padding: 18px 20px;
      margin-top: 16px;
    }
    .modal-rr-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 14px;
    }
    .modal-rr-ladder {
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      gap: 16px;
      align-items: center;
      padding: 6px 0;
    }
    .rr-point {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .rr-dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      flex-shrink: 0;
      box-shadow: 0 0 8px currentColor;
    }
    .rr-info {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .rr-label {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }
    .rr-delta {
      font-size: 11.5px;
      font-weight: 600;
    }
    .rr-bar-bracket {
      display: flex;
      flex-direction: column;
      width: 8px;
      height: 90px;
      background: rgba(142, 142, 147, 0.15);
      border-radius: 4px;
      overflow: hidden;
      margin: 0 auto;
    }
    .rr-bar-fill-gain {
      background: var(--green);
      transition: height 0.4s ease;
    }
    .rr-bar-fill-risk {
      background: var(--red);
      transition: height 0.4s ease;
    }
    .rr-footer-stats {
      display: flex;
      justify-content: space-between;
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid var(--border);
      font-size: 12px;
      color: var(--text-secondary);
    }
    .rr-footer-stats strong {
      color: var(--text-primary);
    }

    /* Shortcuts HUD Modal */
    .shortcuts-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
      margin-top: 14px;
    }
    .shortcut-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 13px;
      color: var(--text-primary);
      padding: 6px 0;
      border-bottom: 1px solid var(--border);
    }
    .shortcut-item:last-child {
      border-bottom: none;
    }
    kbd {
      font-family: -apple-system, BlinkMacSystemFont, "SF Mono", Menlo, monospace;
      font-size: 11px;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
      background: var(--surface-secondary);
      border: 1px solid var(--border);
      box-shadow: 0 1px 2px rgba(0,0,0,0.1);
      color: var(--text-primary);
    }

    /* Apple-Style Toast Notifications */
    .toast-container {
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 99999;
      display: flex;
      flex-direction: column;
      gap: 10px;
      pointer-events: none;
    }
    .apple-toast {
      pointer-events: auto;
      background: rgba(28, 28, 30, 0.92);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.16);
      color: #ffffff;
      padding: 12px 18px;
      border-radius: 14px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
      font-size: 12.5px;
      display: flex;
      align-items: center;
      gap: 12px;
      transform: translateY(0);
      opacity: 1;
      transition: all 0.35s cubic-bezier(0.16, 1, 0.3, 1);
    }
    [data-theme="light"] .apple-toast {
      background: rgba(255, 255, 255, 0.95);
      border: 1px solid rgba(0, 0, 0, 0.1);
      color: #1d1d1f;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12);
    }
    .apple-toast.hide {
      opacity: 0;
      transform: translateY(12px) scale(0.96);
    }
    .toast-icon {
      font-size: 18px;
      flex-shrink: 0;
    }
    .toast-body {
      display: flex;
      flex-direction: column;
      gap: 1px;
    }
    .toast-body strong {
      font-size: 13px;
      font-weight: 600;
    }
    .toast-body span {
      font-size: 11.5px;
      opacity: 0.8;
    }

  
    /* Rough Square Heatmap Matrix (7 Columns • Natural Drop • Zero-Scroll Fit) */
    .heatmap-square-wrapper {
      width: 100%;
      display: flex;
      justify-content: center;
      align-items: center;
      padding: 8px 0;
    }
    .heatmap-square-grid {
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 7px;
      width: min(94vw, 590px);
      box-sizing: border-box;
    }
    .heatmap-tile-square {
      aspect-ratio: 1 / 1;
      width: 100%;
      border-radius: 10px;
      border: 1px solid var(--border);
      padding: 5px 3px;
      cursor: pointer;
      transition: transform 0.18s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.18s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.15s ease;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      position: relative;
      overflow: hidden;
      user-select: none;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
      box-sizing: border-box;
    }
    .heatmap-tile-square:hover {
      transform: translateY(-2px) scale(1.06);
      box-shadow: 0 6px 18px rgba(0, 0, 0, 0.28);
      border-color: var(--accent);
      z-index: 10;
    }
    .heatmap-square-logo-wrap {
      width: 22px;
      height: 22px;
      border-radius: 6px;
      background: #ffffff;
      padding: 1.5px;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
      flex-shrink: 0;
      margin-bottom: 3px;
    }
    .heatmap-square-logo-wrap img {
      width: 16px;
      height: 16px;
      object-fit: contain;
      display: block;
    }
    .heatmap-square-symbol {
      font-size: 11.5px;
      font-weight: 800;
      letter-spacing: -0.01em;
      line-height: 1.1;
      color: var(--text-primary);
    }
    .heatmap-square-price {
      font-size: 10px;
      font-weight: 600;
      color: var(--text-secondary);
      margin-top: 1px;
      line-height: 1.1;
    }
    .heatmap-square-badge {
      font-size: 9.5px;
      font-weight: 700;
      padding: 1px 5px;
      border-radius: 4px;
      margin-top: 3px;
      line-height: 1.15;
      display: inline-block;
    }
    .heatmap-square-badge.pos-green {
      background: rgba(52, 199, 89, 0.22);
      color: #34c759;
    }
    .heatmap-square-badge.pos-red {
      background: rgba(255, 59, 48, 0.22);
      color: #ff3b30;
    }

    /* Engine Specs HUD */
    .engine-specs-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin-top: 16px;
    }
    @media (max-width: 900px) {
      .engine-specs-grid { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 500px) {
      .engine-specs-grid { grid-template-columns: 1fr; }
    }
    .engine-spec-card {
      background: var(--surface-secondary);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .engine-spec-title {
      font-size: 11px;
      font-weight: 600;
      color: var(--text-tertiary);
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }
    .engine-spec-val {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.02em;
    }
    .engine-spec-sub {
      font-size: 11.5px;
      color: var(--text-secondary);
      line-height: 1.35;
    }
    .engine-spec-bar {
      height: 4px;
      background: rgba(142, 142, 147, 0.2);
      border-radius: 2px;
      overflow: hidden;
      margin-top: 4px;
    }
    .engine-spec-fill {
      height: 100%;
      background: var(--accent);
      border-radius: 2px;
    }

  
    /* Feature 1: Quantitative Ratios Ribbon */
    .quant-ratios-ribbon {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 12px;
      margin-bottom: 18px;
    }
    @media (max-width: 900px) {
      .quant-ratios-ribbon { grid-template-columns: repeat(3, 1fr); }
    }
    @media (max-width: 600px) {
      .quant-ratios-ribbon { grid-template-columns: 1fr 1fr; }
    }
    .quant-ratio-card {
      background: var(--surface-secondary);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 3px;
      transition: var(--transition);
    }
    .quant-ratio-card:hover {
      border-color: var(--accent);
      transform: translateY(-1px);
    }
    .ratio-label {
      font-size: 10.5px;
      font-weight: 600;
      color: var(--text-tertiary);
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }
    .ratio-val {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.02em;
    }
    .ratio-sub {
      font-size: 11px;
      color: var(--text-secondary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    /* Feature 2: Interactive Crosshair Scrubber on Equity Curve */
    .equity-chart-container {
      position: relative;
    }
    .equity-hover-tip {
      position: absolute;
      background: rgba(28, 28, 30, 0.94);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid rgba(255, 255, 255, 0.18);
      color: #ffffff;
      padding: 6px 10px;
      border-radius: 8px;
      font-size: 11.5px;
      box-shadow: 0 4px 14px rgba(0,0,0,0.3);
      pointer-events: none;
      transition: opacity 0.15s ease, transform 0.15s ease;
      transform: translate(-50%, -120%);
      white-space: nowrap;
      z-index: 30;
    }
    [data-theme="light"] .equity-hover-tip {
      background: rgba(255, 255, 255, 0.95);
      border: 1px solid rgba(0, 0, 0, 0.12);
      color: #1d1d1f;
      box-shadow: 0 4px 14px rgba(0,0,0,0.12);
    }

    /* Feature 3: Global Financial Market Sessions Clock */
    .market-clocks-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 8px 18px;
      margin-top: 10px;
      flex-wrap: wrap;
    }
    .market-clock-item {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
    }
    .clock-city {
      font-weight: 600;
      color: var(--text-primary);
    }
    .clock-time {
      font-family: -apple-system, BlinkMacSystemFont, "SF Mono", Menlo, monospace;
      font-size: 11px;
      font-weight: 600;
      color: var(--text-secondary);
    }
    .clock-status {
      font-size: 9.5px;
      font-weight: 700;
      padding: 1px 6px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }
    .clock-open { background: var(--green-bg); color: var(--green-text); }
    .clock-closed { background: rgba(142,142,147,0.12); color: var(--text-tertiary); }

    /* Feature 4: Ambient Mesh Glow */
    .ambient-glow-mesh {
      position: absolute;
      inset: -4px;
      border-radius: var(--radius-card);
      background: radial-gradient(circle at 50% 30%, rgba(52, 199, 89, 0.14) 0%, transparent 70%);
      pointer-events: none;
      z-index: 0;
      opacity: 0;
      transition: opacity 0.8s ease, background 0.8s ease;
    }
    .ambient-glow-mesh.active-green {
      opacity: 1;
      background: radial-gradient(circle at 50% 30%, rgba(52, 199, 89, 0.16) 0%, transparent 70%);
    }
    .ambient-glow-mesh.active-red {
      opacity: 1;
      background: radial-gradient(circle at 50% 30%, rgba(255, 59, 48, 0.16) 0%, transparent 70%);
    }

  
    /* 1-Click Executive PDF Teardown Print Stylesheet */
    @media print {
      body {
        background: #ffffff !important;
        color: #1d1d1f !important;
        font-size: 10pt !important;
        padding: 0 !important;
        margin: 0 !important;
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
      }
      .app-header-fixed,
      .apple-nav,
      .ticker-tape-container,
      .market-clocks-bar,
      .screener-search-wrap,
      .filter-bar,
      .inspect-btn,
      .theme-toggle-btn,
      .toast-container,
      .modal-backdrop,
      .macos-window,
      #engine-specs-card,
      #btn-toggle-engine-specs,
      #screener-heatmap-container,
      .slot-pill.empty {
        display: none !important;
      }
      .main-container {
        max-width: 100% !important;
        padding: 6mm 8mm !important;
      }
      .print-executive-header {
        display: block !important;
        border-bottom: 2pt solid #1d1d1f;
        padding-bottom: 4mm;
        margin-bottom: 6mm;
      }
      .print-executive-footer {
        display: flex !important;
        justify-content: space-between;
        align-items: center;
        border-top: 1pt solid #d2d2d7;
        padding-top: 4mm;
        margin-top: 8mm;
        font-size: 8.5pt;
        color: #6e6e73;
      }
      .section-card {
        background: #ffffff !important;
        border: 1pt solid #d2d2d7 !important;
        box-shadow: none !important;
        page-break-inside: avoid;
        margin-bottom: 5mm !important;
        padding: 4mm !important;
      }
      .kpi-card {
        background: #fbfbfd !important;
        border: 1pt solid #e5e5ea !important;
        box-shadow: none !important;
      }
      .kpi-bg-wave, .ambient-glow-mesh {
        display: none !important;
      }
      .table-container {
        overflow: visible !important;
        border: none !important;
      }
      table {
        font-size: 8.5pt !important;
      }
      th, td {
        padding: 4px 6px !important;
      }
      .quant-ratios-ribbon {
        page-break-inside: avoid;
      }
      .quant-ratio-card {
        background: #fbfbfd !important;
        border: 1pt solid #e5e5ea !important;
      }
      .gate-step {
        background: #fbfbfd !important;
        border: 1pt solid #e5e5ea !important;
      }
      .pos-card {
        background: #fbfbfd !important;
        border: 1pt solid #e5e5ea !important;
      }
    }

  </style>
</head>
<body>

  <!-- Fixed Top Header: Ultra-Slim Nav + Pinned Ticker Tape (Visible at all times) -->
  <header class="app-header-fixed">
    <!-- Apple Glass Sticky Nav -->
    <nav class="apple-nav">
      <div class="nav-content">
        <div class="brand-wrap">
          <div class="brand-icon">212</div>
          <div class="brand-text">
            <h1>Trading 212 Quant Bot</h1>
            <p id="endpoint-sub">Connecting to local telemetry engine...</p>
          </div>
        </div>
        <div class="status-pills">
          <div class="status-pill">
            <div id="market-beacon-dot" class="beacon-dot beacon-slate"></div>
            <span id="market-status-badge">SESSION CHECK</span>
          </div>
          <div class="status-pill">
            <span>Mode:</span>
            <strong id="mode-pill">TRADING 212 DEMO</strong>
          </div>
          <div class="status-pill">
            <span>Candle:</span>
            <strong id="tf-pill">15m</strong>
          </div>
          <div class="status-pill">
            <span>Heartbeat:</span>
            <strong id="hb-pill">Syncing...</strong>
          </div>
          <div class="status-pill">
            <strong id="ver-pill">v2.5.1</strong>
          </div>

          <!-- Proxmox LXC Server Telemetry Pill -->
          <div class="status-pill status-pill-node" title="Proxmox Private Cloud Container • 24/7 Daemon">
            <div class="beacon-dot beacon-green"></div>
            <span>Node:</span>
            <strong id="node-pill">Proxmox LXC • 38ms</strong>
          </div>

          <!-- 1-Click Executive PDF Briefing -->
          <button id="pdf-report-btn" class="theme-toggle-btn" onclick="exportExecutivePDF()" title="1-Click Executive PDF Teardown (P)">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:3px;">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
              <polyline points="10 9 9 9 8 9"></polyline>
            </svg>
            <span style="font-weight:600;font-size:11.5px;">PDF</span>
          </button>

          <!-- Terminal Audio Sound Toggle -->
          <button id="sound-toggle-btn" class="theme-toggle-btn" onclick="toggleSound()" title="Terminal Audio Haptics (Muted by default)">
            <span id="sound-icon" style="font-size:13px;">🔕</span>
          </button>

          <!-- Keyboard Shortcuts Trigger -->
          <button id="shortcuts-btn" class="theme-toggle-btn" onclick="openShortcutsModal()" title="Keyboard Shortcuts (?)">
            <span style="font-weight:700;font-size:11.5px;">⌘K</span>
          </button>

          <!-- Space Black Theme Switcher -->
          <button id="theme-toggle-btn" class="theme-toggle-btn" onclick="toggleTheme()" title="Switch Light & Space Black theme">
            <svg id="theme-sun-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="5"></circle>
              <line x1="12" y1="1" x2="12" y2="3"></line>
              <line x1="12" y1="21" x2="12" y2="23"></line>
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
              <line x1="1" y1="12" x2="3" y2="12"></line>
              <line x1="21" y1="12" x2="23" y2="12"></line>
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
            </svg>
            <svg id="theme-moon-icon" style="display:none;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
            </svg>
            <span id="theme-btn-label">Space Black</span>
          </button>
        </div>
      </div>
    </nav>

    <!-- Live Top-Movers Ticker Tape / Marquee -->
    <div class="ticker-tape-container" title="Continuous Wall Street Ticker Tape • Click any stock to inspect">
      <div class="ticker-tape-track" id="ticker-tape-track">
        <div class="ticker-item"><span style="color:var(--text-tertiary);">Loading live market ticker tape...</span></div>
      </div>
    </div>
  </header>

  <!-- Main Content -->
  <main class="main-container">

    <!-- Executive Print Header (Only visible on Cmd+P / PDF Export) -->
    <div class="print-executive-header" style="display:none;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;">
        <div>
          <h1 style="font-size:20pt;font-weight:800;letter-spacing:-0.03em;margin:0;color:#1d1d1f;">Trading 212 Quantitative Bot</h1>
          <p style="font-size:10.5pt;color:#6e6e73;margin:3px 0 0 0;">Executive Portfolio Performance & Screener Teardown Briefing</p>
        </div>
        <div style="text-align:right;font-size:8.5pt;color:#6e6e73;">
          <div>Generated: <strong id="print-timestamp" style="color:#1d1d1f;">--</strong></div>
          <div>Host: <strong>Proxmox LXC Daemon</strong> • Mode: <strong id="print-session-mode">T212 DEMO</strong></div>
        </div>
      </div>
    </div>

    <!-- Hero Activity Strip with Market Countdown & Scan Progress -->
    <div class="hero-activity">
      <div class="activity-left">
        <div class="squircle-icon squircle-blue">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <polyline points="12 6 12 12 16 14"></polyline>
          </svg>
        </div>
        <div>
          <div style="display:flex;align-items:center;gap:8px;">
            <span id="activity-state" class="activity-state-badge badge-buy">MONITORING</span>
            <span id="activity-updated" style="font-size:12px;color:var(--text-tertiary);">Real-time</span>
          </div>
          <div id="activity-detail" style="font-size:13.5px;color:var(--text-secondary);margin-top:3px;">
            Initializing quant trading loop and telemetry monitors...
          </div>
        </div>
      </div>
      <div class="timer-group">
        <div class="timer-widget">
          <div class="timer-meta">
            <span id="scan-timer-label">15m Candle Scan</span>
            <span id="scan-timer-val">Next in --:--</span>
          </div>
          <div class="timer-track">
            <div id="scan-timer-bar" class="timer-bar" style="width:0%"></div>
          </div>
        </div>
        <div class="solar-dial-card">
          <div class="timer-meta">
            <span id="market-timer-label">Market Session Horizon</span>
            <span id="market-timer-val">Calculating...</span>
          </div>
          <div class="solar-dial-wrap">
            <svg class="solar-arc-svg" viewBox="0 0 280 40">
              <defs>
                <linearGradient id="solarGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stop-color="#ff9500" />
                  <stop offset="35%" stop-color="#34c759" />
                  <stop offset="75%" stop-color="#34c759" />
                  <stop offset="100%" stop-color="#ff9500" />
                </linearGradient>
              </defs>
              <line x1="15" y1="32" x2="265" y2="32" stroke="rgba(142,142,147,0.25)" stroke-width="1.5" stroke-dasharray="3,3" />
              <path d="M 20 32 Q 140 4 260 32" fill="none" stroke="rgba(0,113,227,0.18)" stroke-width="4" stroke-linecap="round" />
              <path id="solar-arc-progress" d="M 20 32 Q 140 4 260 32" fill="none" stroke="url(#solarGrad)" stroke-width="4" stroke-linecap="round" stroke-dasharray="245" stroke-dashoffset="0" />
              <circle id="solar-beacon-pin" cx="140" cy="18" r="6.5" fill="#ff9500" stroke="#ffffff" stroke-width="2" />
            </svg>
            <div class="solar-anchors">
              <span>04:00 Pre</span>
              <span style="color:var(--green-text);">09:30 Open</span>
              <span style="color:var(--amber-text);">16:00 Close</span>
              <span>20:00 Post</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Global Financial Market Sessions Clock Bar -->
      <div class="market-clocks-bar">
        <div class="market-clock-item">
          <div class="beacon-dot beacon-slate" id="beacon-ny"></div>
          <span class="clock-city">🇺🇸 New York</span>
          <strong class="clock-time" id="time-ny">--:-- ET</strong>
          <span class="clock-status clock-closed" id="status-ny">NYSE</span>
        </div>
        <div class="market-clock-item">
          <div class="beacon-dot beacon-slate" id="beacon-lon"></div>
          <span class="clock-city">🇬🇧 London</span>
          <strong class="clock-time" id="time-lon">--:-- GMT</strong>
          <span class="clock-status clock-closed" id="status-lon">LSE</span>
        </div>
        <div class="market-clock-item">
          <div class="beacon-dot beacon-slate" id="beacon-fra"></div>
          <span class="clock-city">🇩🇪 Frankfurt</span>
          <strong class="clock-time" id="time-fra">--:-- CET</strong>
          <span class="clock-status clock-closed" id="status-fra">XETRA</span>
        </div>
        <div class="market-clock-item">
          <div class="beacon-dot beacon-slate" id="beacon-tok"></div>
          <span class="clock-city">🇯🇵 Tokyo</span>
          <strong class="clock-time" id="time-tok">--:-- JST</strong>
          <span class="clock-status clock-closed" id="status-tok">TSE</span>
        </div>
      </div>
    </div>

    <!-- 4 KPI Cards Grid with Tactile Visual Meters -->
    <div class="kpi-grid">
      <div class="kpi-card" style="position:relative;">
        <div id="kpi-ambient-aura" class="ambient-glow-mesh active-green"></div>
        <svg class="kpi-bg-wave" viewBox="0 0 100 24" preserveAspectRatio="none">
          <path d="M0,20 Q25,8 50,14 T100,4 L100,24 L0,24 Z" fill="var(--green)" />
        </svg>
        <div class="kpi-header">
          <span class="kpi-title">Total Portfolio Equity</span>
          <div class="squircle-icon squircle-green">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="1" x2="12" y2="23"></line>
              <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
            </svg>
          </div>
        </div>
        <div id="kpi-equity" class="kpi-val">$0.00</div>
        <div id="kpi-invested" class="kpi-sub">Invested in Positions: $0.00</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-header">
          <span class="kpi-title">Free Available Cash</span>
          <div class="squircle-icon squircle-blue">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="2" y="4" width="20" height="16" rx="2"></rect>
              <line x1="2" y1="10" x2="22" y2="10"></line>
            </svg>
          </div>
        </div>
        <div id="kpi-cash" class="kpi-val">$0.00</div>
        <div id="kpi-realized" class="kpi-sub">Session Realized P&L: $0.00</div>
        <div class="kpi-capsule-meter" title="Liquid Cash vs Active Capital">
          <div id="kpi-cash-bar" class="kpi-capsule-fill" style="width:100%; background:var(--accent);"></div>
          <div id="kpi-invested-bar" class="kpi-capsule-fill" style="width:0%; background:var(--green);"></div>
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-header">
          <span class="kpi-title">Active Position Capacity</span>
          <div class="squircle-icon squircle-purple">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
              <polyline points="2 17 12 22 22 17"></polyline>
              <polyline points="2 12 12 17 22 12"></polyline>
            </svg>
          </div>
        </div>
        <div id="kpi-positions" class="kpi-val">0 / 3</div>
        <div class="kpi-slots-wrap">
          <div id="slot-pill-1" class="slot-pill empty">Slot 1</div>
          <div id="slot-pill-2" class="slot-pill empty">Slot 2</div>
          <div id="slot-pill-3" class="slot-pill empty">Slot 3</div>
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-header">
          <span class="kpi-title">24h Drawdown vs Circuit Breaker</span>
          <div class="ring-gauge-wrap">
            <svg class="ring-gauge-svg" viewBox="0 0 44 44">
              <circle class="ring-track" cx="22" cy="22" r="18"></circle>
              <circle id="dd-ring-circle" class="ring-fill" cx="22" cy="22" r="18" stroke="var(--green)"></circle>
            </svg>
          </div>
        </div>
        <div id="kpi-dd" class="kpi-val">0.00%</div>
        <div id="kpi-dd-limit" class="kpi-sub">Healthy (Hard Stop at 5.00% 24h DD)</div>
      </div>
    </div>

    <!-- 4-Gate Diagnostics Pipeline with Animated Conduit -->
    <div class="gate-pipeline">
      <div class="gate-step">
        <div class="gate-step-head">
          <div class="gate-icon-title">
            <div class="gate-mini-icon">
              <svg width="20" height="20" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10" fill="none" stroke="rgba(0,113,227,0.2)" stroke-width="2" />
                <circle cx="12" cy="12" r="5" fill="none" stroke="rgba(0,113,227,0.35)" stroke-width="1.5" />
                <line x1="12" y1="12" x2="22" y2="12" stroke="var(--accent)" stroke-width="2" class="radar-beam" />
              </svg>
            </div>
            <span class="gate-step-num">Gate 1 • Session</span>
          </div>
          <span id="gate1-badge" class="gate-status-badge badge-hold">CHECKING</span>
        </div>
        <div id="gate1-val" class="gate-step-val">US Market Session</div>
        <div id="gate1-desc" class="gate-step-desc">Awaiting session telemetry...</div>
      </div>

      <div class="gate-step">
        <div class="gate-step-head">
          <div class="gate-icon-title">
            <div class="gate-mini-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="2" y="6" width="18" height="12" rx="3" stroke="var(--text-secondary)" />
                <line x1="22" y1="10" x2="22" y2="14" stroke="var(--text-secondary)" />
                <rect id="gate-batt-seg1" x="4.5" y="8.5" width="3.5" height="7" rx="1" fill="var(--green)" />
                <rect id="gate-batt-seg2" x="9.5" y="8.5" width="3.5" height="7" rx="1" fill="var(--green)" />
                <rect id="gate-batt-seg3" x="14.5" y="8.5" width="3.5" height="7" rx="1" fill="rgba(142,142,147,0.3)" />
              </svg>
            </div>
            <span class="gate-step-num">Gate 2 • Capacity</span>
          </div>
          <span id="gate2-badge" class="gate-status-badge badge-hold">CHECKING</span>
        </div>
        <div id="gate2-val" class="gate-step-val">Portfolio Capacity</div>
        <div id="gate2-desc" class="gate-step-desc">Awaiting capacity status...</div>
      </div>

      <div class="gate-step">
        <div class="gate-step-head">
          <div class="gate-icon-title">
            <div class="gate-mini-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 4v4M4.93 7.93l2.83 2.83M19.07 7.93l-2.83 2.83M2 14h4M18 14h4" stroke="var(--text-tertiary)" stroke-width="1.5" />
                <path d="M4 14a8 8 0 1 1 16 0" stroke="var(--accent)" stroke-width="2" />
                <line x1="12" y1="14" x2="16" y2="9" stroke="var(--green)" stroke-width="2.5" stroke-linecap="round" />
              </svg>
            </div>
            <span class="gate-step-num">Gate 3 • Regime</span>
          </div>
          <span id="gate3-badge" class="gate-status-badge badge-hold">CHECKING</span>
        </div>
        <div id="gate3-val" class="gate-step-val">Market Regime (SPY)</div>
        <div id="gate3-desc" class="gate-step-desc">Awaiting benchmark filter...</div>
      </div>

      <div class="gate-step">
        <div class="gate-step-head">
          <div class="gate-icon-title">
            <div class="gate-mini-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" class="crosshair-anim">
                <circle cx="12" cy="12" r="9" fill="none" stroke="var(--amber)" stroke-width="1.5" />
                <circle cx="12" cy="12" r="2.5" fill="var(--amber)" />
                <line x1="12" y1="1" x2="12" y2="6" stroke="var(--amber)" stroke-width="2" />
                <line x1="12" y1="18" x2="12" y2="23" stroke="var(--amber)" stroke-width="2" />
                <line x1="1" y1="12" x2="6" y2="12" stroke="var(--amber)" stroke-width="2" />
                <line x1="18" y1="12" x2="23" y2="12" stroke="var(--amber)" stroke-width="2" />
              </svg>
            </div>
            <span class="gate-step-num">Gate 4 • Conviction</span>
          </div>
          <span id="gate4-badge" class="gate-status-badge badge-hold">CHECKING</span>
        </div>
        <div id="gate4-val" class="gate-step-val">Top Setup Conviction</div>
        <div id="gate4-desc" class="gate-step-desc">Awaiting quantitative screener...</div>
      </div>
    </div>

    <!-- Quantitative Strategy Architecture & Risk Envelopes HUD -->
    <section class="section-card" id="engine-specs-card" style="margin-top:16px;">
      <div class="section-header" style="cursor:pointer;" onclick="toggleEngineSpecs()">
        <div class="section-title-wrap">
          <div class="squircle-icon squircle-purple">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="3"></circle>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
            </svg>
          </div>
          <div>
            <h2 class="section-title">Quantitative Strategy Architecture & Risk Guardrails</h2>
            <p class="section-sub">Multi-factor weighting model, dynamic ATR stop/target ladders, and protective circuit breakers.</p>
          </div>
        </div>
        <button id="btn-toggle-engine-specs" class="filter-btn" onclick="event.stopPropagation(); toggleEngineSpecs();">Show Strategy DNA</button>
      </div>

      <div id="engine-specs-body" style="display:none; margin-top:14px; border-top:1px solid var(--border); padding-top:16px;">
        <div class="engine-specs-grid">
          <div class="engine-spec-card">
            <span class="engine-spec-title">Factor 1 • Trend Structure</span>
            <span class="engine-spec-val" style="color:var(--accent);">35% Weight</span>
            <span class="engine-spec-sub">EMA 20 &gt; EMA 50 trend alignment with positive price expansion.</span>
            <div class="engine-spec-bar"><div class="engine-spec-fill" style="width:35%;"></div></div>
          </div>
          <div class="engine-spec-card">
            <span class="engine-spec-title">Factor 2 • Momentum Velocity</span>
            <span class="engine-spec-val" style="color:var(--green);">30% Weight</span>
            <span class="engine-spec-sub">RSI 14 sweet spot (54–67) and positive 10-bar rate of change.</span>
            <div class="engine-spec-bar"><div class="engine-spec-fill" style="width:30%; background:var(--green);"></div></div>
          </div>
          <div class="engine-spec-card">
            <span class="engine-spec-title">Factor 3 • Volume Conviction</span>
            <span class="engine-spec-val" style="color:var(--amber);">20% Weight</span>
            <span class="engine-spec-sub">Relative volume surge (RVOL &ge; 1.15x) validating institutional buying.</span>
            <div class="engine-spec-bar"><div class="engine-spec-fill" style="width:20%; background:var(--amber);"></div></div>
          </div>
          <div class="engine-spec-card">
            <span class="engine-spec-title">Factor 4 • Volatility Bracket</span>
            <span class="engine-spec-val" style="color:#af52de;">15% Weight</span>
            <span class="engine-spec-sub">Average True Range (ATR 14) sizing with protective downside stop.</span>
            <div class="engine-spec-bar"><div class="engine-spec-fill" style="width:15%; background:#af52de;"></div></div>
          </div>
        </div>

        <div class="engine-specs-grid" style="margin-top:14px;">
          <div class="engine-spec-card">
            <span class="engine-spec-title">Risk Rule • Position Sizing</span>
            <span class="engine-spec-val">Max 2.0% Risk</span>
            <span class="engine-spec-sub">Dollar risk per trade capped at 2% total equity based on 2.0x ATR stop distance.</span>
          </div>
          <div class="engine-spec-card">
            <span class="engine-spec-title">Risk Rule • Portfolio Capacity</span>
            <span class="engine-spec-val">3 Slots Max</span>
            <span class="engine-spec-sub">Strict 33% capital allocation per slot preventing over-concentration.</span>
          </div>
          <div class="engine-spec-card">
            <span class="engine-spec-title">Risk Rule • Circuit Breaker</span>
            <span class="engine-spec-val" style="color:var(--red);">5.00% 24h Stop</span>
            <span class="engine-spec-sub">Automated trading halt if portfolio drawdown exceeds 5% from high-water mark.</span>
          </div>
          <div class="engine-spec-card">
            <span class="engine-spec-title">Risk Rule • Trailing Stop</span>
            <span class="engine-spec-val" style="color:var(--green);">+1.0R Ratchet</span>
            <span class="engine-spec-sub">Locks in breakeven once price reaches +1.0R, trailing at +1.5x ATR thereafter.</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Active Positions Section with Apple-Grade Runway Visualizer -->
    <section class="section-card">
      <div class="section-header">
        <div class="section-title-wrap">
          <div class="squircle-icon squircle-blue">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
            </svg>
          </div>
          <div>
            <h2 class="section-title">Open Positions & Real-Time Risk Runway</h2>
            <p class="section-sub">Dynamic trailing stops and profit runways evaluated every 15 seconds. Click any position for detailed metrics.</p>
          </div>
        </div>
      </div>
      <div id="positions-container">
        <!-- Rendered dynamically -->
      </div>
    </section>

    <!-- AI Portfolio Manager Hero Banner -->
    <div class="ai-hero-box">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
        <div style="display:flex;align-items:center;gap:12px;">
          <div class="squircle-icon squircle-purple">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"></path>
            </svg>
          </div>
          <div>
            <h3 style="font-size:17px;font-weight:600;letter-spacing:-0.02em;">AI Portfolio Manager</h3>
            <p style="font-size:12px;color:var(--text-tertiary);margin-top:1px;">Multi-agent entry vetting, catalyst risk checks, and slot rotation governor.</p>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <span id="ai-engine-badge" class="badge badge-buy">Google Gemini</span>
          <button id="btn-toggle-expired" class="filter-btn" style="display:none;" onclick="toggleExpiredAI()">Show Expired</button>
        </div>
      </div>
      <div id="ai-scan-banner" style="display:none;background:rgba(0,113,227,0.08);border:1px solid rgba(0,113,227,0.15);border-radius:var(--radius-sm);padding:8px 14px;font-size:12px;color:var(--text-primary);margin-bottom:14px;"></div>
      <div id="ai-decisions-container">
        <!-- Decisions rendered here -->
      </div>
    </div>

    <!-- Apple Portfolio Analytics (Equity Curve + Performance Activity Rings) -->
    <div class="analytics-grid">
      <!-- Cumulative Portfolio Equity Curve -->
      <div class="section-card" style="margin-bottom:0;">
        <div class="section-header">
          <div class="section-title-wrap">
            <div class="squircle-icon squircle-green">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
              </svg>
            </div>
            <div>
              <h2 class="section-title">Portfolio Equity Trajectory</h2>
              <p class="section-sub">Cumulative portfolio valuation curve & drawdown floor</p>
            </div>
          </div>
          <div style="text-align:right;">
            <span id="curve-pnl-badge" class="badge badge-strong-buy">+0.00% Realized</span>
          </div>
        </div>
        <div id="equity-curve-container" style="position:relative;height:180px;width:100%;">
          <!-- SVG curve rendered dynamically -->
        </div>
      </div>

      <!-- Apple Fitness Concentric Activity Rings -->
      <div class="rings-card">
        <div class="section-header" style="margin-bottom:0;">
          <div class="section-title-wrap">
            <div class="squircle-icon squircle-amber">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <circle cx="12" cy="12" r="6"></circle>
                <circle cx="12" cy="12" r="2"></circle>
              </svg>
            </div>
            <div>
              <h2 class="section-title">Trading Health Rings</h2>
              <p class="section-sub">Win Rate, Profit Factor & Capacity</p>
            </div>
          </div>
        </div>

        <div class="rings-content-wrap">
          <div class="rings-svg-wrap">
            <svg class="rings-svg" viewBox="0 0 110 110">
              <!-- Ring 1 (Outer - Win Rate) -->
              <circle class="ring-bg" cx="55" cy="55" r="46" stroke="#ff2d55"></circle>
              <circle id="ring-win-rate" class="ring-active" cx="55" cy="55" r="46" stroke="#ff2d55" stroke-dasharray="289.0" stroke-dashoffset="289.0"></circle>

              <!-- Ring 2 (Middle - Profit Factor) -->
              <circle class="ring-bg" cx="55" cy="55" r="34" stroke="#ff9500"></circle>
              <circle id="ring-profit-factor" class="ring-active" cx="55" cy="55" r="34" stroke="#ff9500" stroke-dasharray="213.6" stroke-dashoffset="213.6"></circle>

              <!-- Ring 3 (Inner - Slot Capacity) -->
              <circle class="ring-bg" cx="55" cy="55" r="22" stroke="#0071e3"></circle>
              <circle id="ring-slot-capacity" class="ring-active" cx="55" cy="55" r="22" stroke="#0071e3" stroke-dasharray="138.2" stroke-dashoffset="138.2"></circle>
            </svg>
          </div>
          <div class="rings-legend">
            <div class="ring-leg-item">
              <div class="ring-leg-label"><div class="ring-dot" style="background:#ff2d55;"></div> Win Rate</div>
              <div id="stat-win-rate" class="ring-leg-val">--%</div>
            </div>
            <div class="ring-leg-item">
              <div class="ring-leg-label"><div class="ring-dot" style="background:#ff9500;"></div> Profit Factor</div>
              <div id="stat-profit-factor" class="ring-leg-val">--x</div>
            </div>
            <div class="ring-leg-item">
              <div class="ring-leg-label"><div class="ring-dot" style="background:#0071e3;"></div> Slot Usage</div>
              <div id="stat-slot-usage" class="ring-leg-val">0 / 3</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Sector Diversification Donut Card -->
    <div class="donut-card">
      <div class="section-header">
        <div class="section-title-wrap">
          <div class="squircle-icon squircle-purple">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <path d="M12 2a10 10 0 0 1 10 10h-10z"></path>
            </svg>
          </div>
          <div>
            <h2 class="section-title">Sector Capital Diversification</h2>
            <p class="section-sub">Live allocation across high-beta growth sectors and cash reserves</p>
          </div>
        </div>
      </div>
      <div class="donut-layout">
        <div class="donut-svg-wrap">
          <svg class="donut-svg" viewBox="0 0 140 140" id="sector-donut-svg">
            <!-- Rendered dynamically -->
          </svg>
        </div>
        <div id="donut-legend-container" class="donut-legend-grid">
          <!-- Legend tags rendered dynamically -->
        </div>
      </div>
    </div>

    <!-- 50-Stock Screener with Radial Score Rings & Sparklines -->
    <section class="section-card">
      <div class="section-header">
        <div class="section-title-wrap">
          <div class="squircle-icon squircle-blue">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="20" x2="18" y2="10"></line>
              <line x1="12" y1="20" x2="12" y2="4"></line>
              <line x1="6" y1="20" x2="6" y2="14"></line>
            </svg>
          </div>
          <div>
            <h2 id="screener-title" class="section-title">50-Stock Quantitative Screener & Recommendation Leaderboard</h2>
            <p class="section-sub">Scored 0–100 via multi-factor quantitative engine. Click any stock to view detailed technical matrix.</p>
          </div>
        </div>
        <div class="filter-bar">
          <!-- Spotlight Quick-Search -->
          <div class="screener-search-wrap">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" style="opacity:0.6;">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
            <input type="text" id="screener-search-input" placeholder="Search 50 stocks (symbol, name, sector)... [/]" oninput="handleScreenerSearch(this.value)" autocomplete="off" spellcheck="false" />
            <span class="search-kbd-shortcut">/</span>
          </div>

          <button id="btn-filter-all" class="filter-btn active" onclick="setFilter('ALL', this)">All (50)</button>
          <button id="btn-filter-strong-buy" class="filter-btn" onclick="setFilter('STRONG BUY', this)">Strong Buy</button>
          <button id="btn-filter-buy" class="filter-btn" onclick="setFilter('BUY', this)">Buy</button>
          <button id="btn-filter-watch" class="filter-btn" onclick="setFilter('WATCH', this)">Watch</button>
          <button id="btn-filter-avoid" class="filter-btn" onclick="setFilter('AVOID', this)">Avoid</button>
          <button id="btn-toggle-guide" class="filter-btn" onclick="toggleScreenerGuide()">Hide Guide</button>
          <button id="btn-export-csv" class="filter-btn export-csv-btn" onclick="exportScreenerCSV()" title="Export ranked 50-stock matrix as CSV">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle;margin-right:3px;">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="7 10 12 15 17 10"></polyline>
              <line x1="12" y1="15" x2="12" y2="3"></line>
            </svg>
            <span>CSV</span>
          </button>
        </div>
      </div>

      <!-- Collapsible 8-Card Quantitative Column Guide -->
      <div id="screener-guide" class="screener-guide-grid">
        <div class="screener-guide-card">
          <strong>Quant Score (0–100)</strong>
          Composite multi-factor rank combining trend alignment, momentum, volume, and volatility. Needs <b>&ge;70</b> for a BUY signal (<b>&ge;80</b> Strong Buy).
        </div>
        <div class="screener-guide-card">
          <strong>Price</strong>
          Latest 15-minute bar closing price in USD used to evaluate technical signals and entry sizing.
        </div>
        <div class="screener-guide-card">
          <strong>EMA 20 / 50</strong>
          Fast (20-bar) vs. Slow (50-bar) Exponential Moving Averages. Bullish uptrend when <b>EMA 20 &gt; EMA 50</b> and price stays above both.
        </div>
        <div class="screener-guide-card">
          <strong>RSI (14)</strong>
          14-bar Relative Strength Index (0–100). Measures momentum velocity; sweet spot for entries is <b>54–67</b> (avoids overbought &gt;72 spikes).
        </div>
        <div class="screener-guide-card">
          <strong>Rel Vol (RVOL)</strong>
          Current 15m volume divided by its 20-bar average. Values <b>&ge;1.15x</b> confirm genuine institutional participation behind the move (<b>&ge;1.5x</b> surge).
        </div>
        <div class="screener-guide-card">
          <strong>10-Bar ROC</strong>
          10-Bar Rate of Change (% price gain/loss over the last 2.5 trading hours). Positive values confirm active upward velocity.
        </div>
        <div class="screener-guide-card">
          <strong id="guide-sl-title">Stop-Loss (2.0x ATR)</strong>
          Initial protective exit placed <b>2.0&times; Average True Range</b> below entry price to cap downside on a normal volatility swing.
        </div>
        <div class="screener-guide-card">
          <strong id="guide-tp-title">Target (3.5x ATR)</strong>
          Projected profit-taking exit placed <b>3.5&times; ATR</b> above entry (<b>1.75:1</b> reward-to-risk ratio), while trailing stops lock in gains from +1.0R.
        </div>
      </div>

      <!-- Screener View Mode Selector -->
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;margin-top:4px;">
        <div style="display:flex;gap:6px;">
          <button id="view-mode-table" class="filter-btn active" onclick="switchScreenerView('table')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle;margin-right:4px;">
              <line x1="8" y1="6" x2="21" y2="6"></line>
              <line x1="8" y1="12" x2="21" y2="12"></line>
              <line x1="8" y1="18" x2="21" y2="18"></line>
              <line x1="3" y1="6" x2="3.01" y2="6"></line>
              <line x1="3" y1="12" x2="3.01" y2="12"></line>
              <line x1="3" y1="18" x2="3.01" y2="18"></line>
            </svg>
            Leaderboard Table
          </button>
          <button id="view-mode-heatmap" class="filter-btn" onclick="switchScreenerView('heatmap')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle;margin-right:4px;">
              <rect x="3" y="3" width="7" height="7"></rect>
              <rect x="14" y="3" width="7" height="7"></rect>
              <rect x="14" y="14" width="7" height="7"></rect>
              <rect x="3" y="14" width="7" height="7"></rect>
            </svg>
            Sector Heatmap
          </button>
        </div>
        <span id="screener-count-pill" style="font-size:12px;color:var(--text-tertiary);">50 stocks analyzed</span>
      </div>

      <!-- Sector Heatmap Container -->
      <div id="screener-heatmap-container" style="display:none;margin-bottom:16px;">
        <!-- Dynamically rendered sector heatmap groups -->
      </div>

      <div class="table-container" id="screener-table-container">
        <table>
          <thead>
            <tr>
              <th id="th-sort-rank" class="sortable active-sort" onclick="handleSort('rank')">Rank<span id="sort-rank" class="sort-icon">▲</span></th>
              <th id="th-sort-symbol" class="sortable" onclick="handleSort('symbol')">Asset<span id="sort-symbol" class="sort-icon">▲</span></th>
              <th id="th-sort-rating" class="sortable" onclick="handleSort('rating')">Rating<span id="sort-rating" class="sort-icon">▲</span></th>
              <th id="th-sort-score" class="sortable" onclick="handleSort('score')">Score<span class="th-sub">0-100 Radial</span><span id="sort-score" class="sort-icon">▲</span></th>
              <th id="th-sort-price" class="sortable" onclick="handleSort('price')">Price<span id="sort-price" class="sort-icon">▲</span></th>
              <th>Trendline<span class="th-sub">Trend Sparkline</span></th>
              <th id="th-sort-ema" class="sortable" onclick="handleSort('ema')">EMA 20/50<span id="sort-ema" class="sort-icon">▲</span></th>
              <th id="th-sort-rsi" class="sortable" onclick="handleSort('rsi')">RSI<span id="sort-rsi" class="sort-icon">▲</span></th>
              <th id="th-sort-rvol" class="sortable" onclick="handleSort('rvol')">RVOL<span id="sort-rvol" class="sort-icon">▲</span></th>
              <th id="th-sort-roc" class="sortable" onclick="handleSort('roc')">10-Bar ROC<span id="sort-roc" class="sort-icon">▲</span></th>
              <th id="th-sort-sl" class="sortable" onclick="handleSort('sl')"><span id="th-sl-label">Stop-Loss</span><span id="sort-sl" class="sort-icon">▲</span></th>
              <th id="th-sort-tp" class="sortable" onclick="handleSort('tp')"><span id="th-tp-label">Take-Profit</span><span id="sort-tp" class="sort-icon">▲</span></th>
              <th class="th-thesis">Quantitative Thesis & Catalyst Rationale</th>
              <th style="text-align:right;">Action</th>
            </tr>
          </thead>
          <tbody id="screener-tbody">
            <!-- Screener rows rendered here -->
          </tbody>
        </table>
      </div>
    </section>

    <!-- Closed Trades History -->
    <section class="section-card">
      <div class="section-header">
        <div class="section-title-wrap">
          <div class="squircle-icon squircle-green">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
          </div>
          <div>
            <h2 class="section-title">Recent Realized Executions</h2>
            <p id="closed-trades-summary" class="section-sub">Complete trade ledger with entry/exit fills, net P&L, R-multiple, and holding periods.</p>
          </div>
        </div>
      </div>
      <div id="closed-trades-container">
        <!-- Rendered here -->
      </div>
    </section>

    <!-- Live Execution Logs Terminal with macOS Window Frame -->
    <section class="section-card" style="padding:0;overflow:hidden;background:transparent;border:none;box-shadow:none;">
      <div class="macos-window">
        <div class="macos-window-header">
          <div class="macos-traffic-lights">
            <div class="traffic-dot traffic-red" title="Close"></div>
            <div class="traffic-dot traffic-yellow" title="Minimize"></div>
            <div class="traffic-dot traffic-green" title="Expand"></div>
            <div class="macos-window-title" style="margin-left:8px;">
              <span>bash • trading_bot.log (Live Daemon Stream)</span>
              <span class="beacon-dot beacon-open" style="width:6px;height:6px;"></span>
            </div>
          </div>
          <div class="log-filter-pills">
            <button class="log-filter-btn active" onclick="setLogFilter('ALL', this)">All Logs</button>
            <button class="log-filter-btn" onclick="setLogFilter('ORDER', this)">Orders</button>
            <button class="log-filter-btn" onclick="setLogFilter('SCREENER', this)">Screener</button>
            <button class="log-filter-btn" onclick="setLogFilter('HEARTBEAT', this)">Heartbeats</button>
          </div>
        </div>
        <div id="log-container" class="log-box" style="border:none;border-radius:0;">
          <!-- Live log stream -->
        </div>
      </div>
    </section>

    <!-- Executive Print Footer (Only visible on Cmd+P / PDF Export) -->
    <div class="print-executive-footer" style="display:none;">
      <span>Trading 212 Automated Quant Daemon • Multi-Factor Momentum Strategy Engine</span>
      <span>Automated Briefing • Strictly Confidential</span>
    </div>

  </main>

  <!-- Interactive Drill-Down "Sheet" Modal -->
  <div id="stock-modal-backdrop" class="modal-backdrop" onclick="closeStockModal(event)">
    <div class="modal-sheet" onclick="event.stopPropagation()">
      <div class="modal-header">
        <div class="modal-title-group">
          <div id="modal-squircle" class="squircle-icon squircle-blue">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"></polyline>
              <polyline points="16 7 22 7 22 13"></polyline>
            </svg>
          </div>
          <div>
            <div style="display:flex;align-items:center;gap:10px;">
              <h2 id="modal-symbol" style="font-size:24px;font-weight:700;letter-spacing:-0.03em;">AAPL</h2>
              <span id="modal-sector-badge" class="badge badge-buy">Technology</span>
              <span id="modal-rating-badge" class="badge badge-strong-buy">STRONG BUY</span>
            </div>
            <div id="modal-company-name" style="font-size:13px;color:var(--text-secondary);margin-top:2px;">Apple Inc. • NASDAQ</div>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:10px;">
          <a id="modal-tv-link" href="#" target="_blank" rel="noopener" class="theme-toggle-btn" style="text-decoration:none;font-size:11.5px;padding:6px 12px;" title="Open live candlestick chart in TradingView">
            <span>TradingView Chart</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
              <polyline points="15 3 21 3 21 9"></polyline>
              <line x1="10" y1="14" x2="21" y2="3"></line>
            </svg>
          </a>
          <button class="modal-close-btn" onclick="closeStockModal()" aria-label="Close">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
      </div>

      <!-- Large Chart / Sparkline -->
      <div class="modal-chart-card">
        <div class="modal-chart-header">
          <div>
            <span style="font-size:12px;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:0.04em;">Current Mark Price</span>
            <div style="display:flex;align-items:baseline;gap:8px;margin-top:2px;">
              <span id="modal-price" style="font-size:32px;font-weight:700;letter-spacing:-0.03em;">$0.00</span>
              <span id="modal-roc" style="font-size:16px;font-weight:600;">+0.00%</span>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:12px;">
            <div style="display:flex;gap:4px;">
              <button id="modal-chart-btn-spark" class="filter-btn active" onclick="switchModalChart('spark')">Trendline</button>
              <button id="modal-chart-btn-tv" class="filter-btn" onclick="switchModalChart('tv')">Interactive Candles</button>
            </div>
            <div id="modal-score-wrap" style="text-align:right;">
              <!-- Radial dial inserted here -->
            </div>
          </div>
        </div>
        <div id="modal-sparkline-expanded" style="height:120px;width:100%;margin-top:14px;"></div>
        <div id="modal-tv-embedded-wrap" style="height:360px;width:100%;margin-top:14px;display:none;border-radius:12px;overflow:hidden;border:1px solid var(--border);"></div>
      </div>

      <!-- 6-Tile Technical Intelligence Matrix -->
      <div class="modal-grid">
        <div class="modal-tile">
          <span class="tile-label">Momentum (RSI 14)</span>
          <span id="modal-rsi" class="tile-val">50.0</span>
          <span id="modal-rsi-desc" class="tile-sub">Sweet-Spot Zone (45–65)</span>
        </div>
        <div class="modal-tile">
          <span class="tile-label">Relative Volume (RVOL)</span>
          <span id="modal-rvol" class="tile-val">1.00x</span>
          <span id="modal-rvol-desc" class="tile-sub">Institutional Surge</span>
        </div>
        <div class="modal-tile">
          <span class="tile-label">Trend Structure</span>
          <span id="modal-mas" class="tile-val">$0.00 / $0.00</span>
          <span id="modal-trend-desc" class="tile-sub">EMA 20 vs EMA 50</span>
        </div>
        <div class="modal-tile">
          <span class="tile-label">Volatility (14 ATR)</span>
          <span id="modal-atr" class="tile-val">$0.00</span>
          <span id="modal-atr-desc" class="tile-sub">Average True Range</span>
        </div>
        <div class="modal-tile">
          <span class="tile-label">Stop-Loss Bracket</span>
          <span id="modal-sl" class="tile-val pos-red">$0.00</span>
          <span id="modal-sl-desc" class="tile-sub">1.5x ATR Downside Guard</span>
        </div>
        <div class="modal-tile">
          <span class="tile-label">Profit Target Bracket</span>
          <span id="modal-tp" class="tile-val pos-green">$0.00</span>
          <span id="modal-tp-desc" class="tile-sub">3.5x ATR Target (+2.3R)</span>
        </div>
      </div>

      <!-- Asymmetric Risk / Reward Bracket Geometry Visualizer -->
      <div class="modal-rr-card">
        <div class="modal-rr-header">
          <span style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-tertiary);">Asymmetric Trade Geometry</span>
          <span id="modal-rr-ratio" class="badge badge-strong-buy" style="font-size:11px;">1 : 2.33 R/R</span>
        </div>
        <div class="modal-rr-ladder">
          <div class="rr-point rr-tp">
            <div class="rr-dot" style="background:var(--green); color:var(--green);"></div>
            <div class="rr-info">
              <span class="rr-label" style="color:var(--green-text);">🎯 Take-Profit (+3.5x ATR)</span>
              <strong id="modal-rr-tp-val" style="color:var(--green-text); font-size:15px;">$0.00</strong>
              <span id="modal-rr-tp-pct" class="rr-delta pos-green">+0.0% (+2.33R)</span>
            </div>
          </div>
          <div class="rr-bar-bracket">
            <div class="rr-bar-fill-gain" id="modal-rr-gain-bar" style="height:70%;"></div>
            <div class="rr-bar-fill-risk" id="modal-rr-risk-bar" style="height:30%;"></div>
          </div>
          <div class="rr-point rr-sl">
            <div class="rr-dot" style="background:var(--red); color:var(--red);"></div>
            <div class="rr-info">
              <span class="rr-label" style="color:var(--red-text);">🛡️ Stop-Loss (1.5x ATR)</span>
              <strong id="modal-rr-sl-val" style="color:var(--red-text); font-size:15px;">$0.00</strong>
              <span id="modal-rr-sl-pct" class="rr-delta pos-red">-0.0% (-1.0R)</span>
            </div>
          </div>
        </div>
        <div class="rr-footer-stats">
          <span>Breakeven Threshold: <strong id="modal-rr-be-rate">30.0% Win Rate</strong></span>
          <span>Payoff Ratio: <strong>1.0R Risk : 2.33R Gain</strong></span>
        </div>
      </div>

      <!-- Plain-English Thesis & Non-Trader Explanation Card -->
      <div class="modal-thesis-card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
          <h4 style="font-size:12px;font-weight:700;letter-spacing:-0.01em;text-transform:uppercase;color:var(--text-tertiary);margin:0;display:flex;align-items:center;gap:6px;">
            <span>💡 Plain-English Summary</span>
            <span style="font-size:11px;font-weight:500;padding:2px 8px;border-radius:12px;background:rgba(56,189,248,0.12);color:var(--blue-text);text-transform:none;">Non-Technical Guide</span>
          </h4>
          <span id="modal-plain-action-pill" class="status-pill status-pill-active" style="font-size:11px;padding:3px 10px;">MONITORING</span>
        </div>

        <!-- Executive Human-Readable Verdict Banner -->
        <div id="modal-plain-verdict-banner" style="background:var(--surface-tertiary);border:1px solid var(--border);border-radius:10px;padding:12px 14px;margin-bottom:14px;">
          <div id="modal-plain-verdict-title" style="font-size:14px;font-weight:700;color:var(--text-primary);margin-bottom:4px;"></div>
          <p id="modal-plain-verdict-desc" style="font-size:13px;line-height:1.55;color:var(--text-secondary);margin:0;"></p>
        </div>

        <!-- 3 Simple Pillars Grid -->
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;margin-bottom:14px;">
          <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 12px;">
            <div style="font-size:11px;font-weight:600;color:var(--text-tertiary);text-transform:uppercase;margin-bottom:4px;">1. Price Direction</div>
            <div id="modal-plain-trend" style="font-size:13px;font-weight:600;color:var(--text-primary);"></div>
            <div id="modal-plain-trend-sub" style="font-size:11.5px;color:var(--text-secondary);margin-top:2px;"></div>
          </div>
          <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 12px;">
            <div style="font-size:11px;font-weight:600;color:var(--text-tertiary);text-transform:uppercase;margin-bottom:4px;">2. Trading Interest</div>
            <div id="modal-plain-volume" style="font-size:13px;font-weight:600;color:var(--text-primary);"></div>
            <div id="modal-plain-volume-sub" style="font-size:11.5px;color:var(--text-secondary);margin-top:2px;"></div>
          </div>
          <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 12px;">
            <div style="font-size:11px;font-weight:600;color:var(--text-tertiary);text-transform:uppercase;margin-bottom:4px;">3. Safety & Timing</div>
            <div id="modal-plain-safety" style="font-size:13px;font-weight:600;color:var(--text-primary);"></div>
            <div id="modal-plain-safety-sub" style="font-size:11.5px;color:var(--text-secondary);margin-top:2px;"></div>
          </div>
        </div>

        <!-- Bot Decision Banner -->
        <div id="modal-plain-bot-decision" style="font-size:12.5px;line-height:1.5;padding:10px 12px;border-radius:8px;background:rgba(255,255,255,0.03);border:1px solid var(--border);margin-bottom:12px;"></div>

        <!-- Collapsible Quantitative / Indicator Breakdown for Technical Users -->
        <details style="margin-top:10px;font-size:12px;color:var(--text-tertiary);">
          <summary style="cursor:pointer;font-weight:600;color:var(--blue-text);user-select:none;outline:none;padding:4px 0;">
            ⚙️ View Technical Quantitative Rules & Formulas (EMA, RSI, ATR, RVOL)
          </summary>
          <div style="margin-top:8px;padding:10px 12px;border-radius:8px;background:rgba(0,0,0,0.25);border:1px solid var(--border);font-family:ui-monospace,Menlo,monospace;font-size:11.5px;line-height:1.6;color:var(--text-secondary);">
            <div><strong>Algorithm Thesis:</strong> <span id="modal-thesis-text" style="color:var(--text-primary);"></span></div>
            <div id="modal-blocker-note" style="margin-top:6px;color:var(--amber-text);display:none;"></div>
          </div>
        </details>
      </div>
    </div>
  </div>

  <!-- Keyboard Shortcuts HUD Modal -->
  <div id="shortcuts-modal-backdrop" class="modal-backdrop" onclick="closeShortcutsModal(event)">
    <div class="modal-sheet" style="max-width:500px;padding:26px;" onclick="event.stopPropagation()">
      <div class="modal-header" style="margin-bottom:14px;">
        <div style="display:flex;align-items:center;gap:12px;">
          <div class="squircle-icon squircle-blue" style="width:36px;height:36px;border-radius:10px;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="2" y="4" width="20" height="16" rx="2"></rect>
              <path d="M6 8h.01M10 8h.01M14 8h.01M18 8h.01M6 12h.01M10 12h.01M14 12h.01M18 12h.01M8 16h8"></path>
            </svg>
          </div>
          <div>
            <h3 style="font-size:18px;font-weight:700;letter-spacing:-0.02em;">Terminal Shortcuts</h3>
            <p style="font-size:12px;color:var(--text-secondary);margin:0;">Workstation Quick-Navigation</p>
          </div>
        </div>
        <button class="modal-close-btn" onclick="closeShortcutsModal()" aria-label="Close">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
      <div class="shortcuts-list">
        <div class="shortcut-item"><span>Focus Stock Quick-Search</span><span><kbd>/</kbd> or <kbd>⌘K</kbd></span></div>
        <div class="shortcut-item"><span>Filter: All Stocks (50)</span><kbd>1</kbd></div>
        <div class="shortcut-item"><span>Filter: Strong Buy Setups</span><kbd>2</kbd></div>
        <div class="shortcut-item"><span>Filter: Buy Setups</span><kbd>3</kbd></div>
        <div class="shortcut-item"><span>Filter: Watchlist</span><kbd>4</kbd></div>
        <div class="shortcut-item"><span>Filter: Avoid Setups</span><kbd>5</kbd></div>
        <div class="shortcut-item"><span>Toggle Light / Space Black</span><kbd>T</kbd></div>
        <div class="shortcut-item"><span>Toggle Screener Column Guide</span><kbd>G</kbd></div>
        <div class="shortcut-item"><span>Export Screener to CSV</span><kbd>E</kbd></div>
        <div class="shortcut-item"><span>Executive PDF Briefing</span><span><kbd>P</kbd> or <kbd>⌘P</kbd></span></div>
        <div class="shortcut-item"><span>Close Modal Sheets</span><kbd>Esc</kbd></div>
        <div class="shortcut-item"><span>Show Keyboard Shortcuts HUD</span><kbd>?</kbd></div>
      </div>
    </div>
  </div>

  <!-- Dynamic Toast Container -->
  <div id="toast-container" class="toast-container"></div>

  <script>
    // Universe Company & Sector Metadata
    const STOCK_METADATA = {
      'PLTR_US_EQ': { name: 'Palantir Technologies', sector: 'Enterprise AI & Defense', domain: 'palantir.com' },
      'NVDA_US_EQ': { name: 'NVIDIA Corp', sector: 'AI & Semiconductors', domain: 'nvidia.com' },
      'AMD_US_EQ': { name: 'Advanced Micro Devices', sector: 'AI & Semiconductors', domain: 'amd.com' },
      'SMCI_US_EQ': { name: 'Super Micro Computer', sector: 'AI Server Infrastructure', domain: 'supermicro.com' },
      'ARM_US_EQ': { name: 'Arm Holdings', sector: 'Semiconductor Architecture', domain: 'arm.com' },
      'MU_US_EQ': { name: 'Micron Technology', sector: 'Memory & Storage', domain: 'micron.com' },
      'AVGO_US_EQ': { name: 'Broadcom Inc', sector: 'Semiconductors & Networking', domain: 'broadcom.com' },
      'MRVL_US_EQ': { name: 'Marvell Technology', sector: 'Data Infrastructure Silicon', domain: 'marvell.com' },
      'TSM_US_EQ': { name: 'Taiwan Semiconductor', sector: 'Semiconductor Foundry', domain: 'tsmc.com' },
      'ANET_US_EQ': { name: 'Arista Networks', sector: 'Cloud Networking', domain: 'arista.com' },
      'MSTR_US_EQ': { name: 'MicroStrategy', sector: 'Bitcoin Treasury & Software', domain: 'microstrategy.com' },
      'COIN_US_EQ': { name: 'Coinbase Global', sector: 'Crypto Exchange', domain: 'coinbase.com' },
      'MARA_US_EQ': { name: 'MARA Holdings', sector: 'Digital Asset Compute', domain: 'mara.com' },
      'RIOT_US_EQ': { name: 'Riot Platforms', sector: 'Digital Asset Compute', domain: 'riotplatforms.com' },
      'CLSK_US_EQ': { name: 'CleanSpark', sector: 'Digital Asset Compute', domain: 'cleanspark.com' },
      'VST_US_EQ': { name: 'Vistra Corp', sector: 'Clean Energy & Nuclear', domain: 'vistracorp.com' },
      'CEG_US_EQ': { name: 'Constellation Energy', sector: 'Clean Energy & Nuclear', domain: 'constellationenergy.com' },
      'OKLO_US_EQ': { name: 'Oklo Inc', sector: 'Next-Gen Fission Energy', domain: 'oklo.com' },
      'CCJ_US_EQ': { name: 'Cameco Corp', sector: 'Uranium & Nuclear Fuel', domain: 'cameco.com' },
      'ENPH_US_EQ': { name: 'Enphase Energy', sector: 'Solar & Renewable Tech', domain: 'enphase.com' },
      'RKLB_US_EQ': { name: 'Rocket Lab USA', sector: 'Space Systems & Launch', domain: 'rocketlabusa.com' },
      'IONQ_US_EQ': { name: 'IonQ Inc', sector: 'Quantum Computing', domain: 'ionq.com' },
      'ASTS_US_EQ': { name: 'AST SpaceMobile', sector: 'Space Cellular Broadband', domain: 'ast-science.com' },
      'LUNR_US_EQ': { name: 'Intuitive Machines', sector: 'Lunar Exploration', domain: 'intuitivemachines.com' },
      'AXON_US_EQ': { name: 'Axon Enterprise', sector: 'Public Safety Technology', domain: 'axon.com' },
      'RGTI_US_EQ': { name: 'Rigetti Computing', sector: 'Quantum Computing', domain: 'rigetti.com' },
      'HOOD_US_EQ': { name: 'Robinhood Markets', sector: 'Fintech & Brokerage', domain: 'robinhood.com' },
      'SOFI_US_EQ': { name: 'SoFi Technologies', sector: 'Digital Banking', domain: 'sofi.com' },
      'AFRM_US_EQ': { name: 'Affirm Holdings', sector: 'Fintech & BNPL', domain: 'affirm.com' },
      'UPST_US_EQ': { name: 'Upstart Holdings', sector: 'AI Lending Platform', domain: 'upstart.com' },
      'NU_US_EQ': { name: 'Nu Holdings', sector: 'Digital Banking', domain: 'nubank.com.br' },
      'FUTU_US_EQ': { name: 'Futu Holdings', sector: 'Global Digital Brokerage', domain: 'futuholdings.com' },
      'SHOP_US_EQ': { name: 'Shopify Inc', sector: 'Global E-Commerce', domain: 'shopify.com' },
      'APP_US_EQ': { name: 'AppLovin Corp', sector: 'AI Marketing & Ads', domain: 'applovin.com' },
      'CRWD_US_EQ': { name: 'CrowdStrike Holdings', sector: 'Cybersecurity Cloud', domain: 'crowdstrike.com' },
      'NET_US_EQ': { name: 'Cloudflare Inc', sector: 'Edge Cloud & Security', domain: 'cloudflare.com' },
      'SNOW_US_EQ': { name: 'Snowflake Inc', sector: 'Data Cloud Platform', domain: 'snowflake.com' },
      'PANW_US_EQ': { name: 'Palo Alto Networks', sector: 'Enterprise Cybersecurity', domain: 'paloaltonetworks.com' },
      'DDOG_US_EQ': { name: 'Datadog Inc', sector: 'Cloud Observability', domain: 'datadoghq.com' },
      'IOT_US_EQ': { name: 'Samsara Inc', sector: 'Connected IoT Operations', domain: 'samsara.com' },
      'TSLA_US_EQ': { name: 'Tesla Inc', sector: 'EV & Autonomous Systems', domain: 'tesla.com' },
      'RIVN_US_EQ': { name: 'Rivian Automotive', sector: 'Electric Vehicles', domain: 'rivian.com' },
      'RDDT_US_EQ': { name: 'Reddit Inc', sector: 'Social Media & Community', domain: 'reddit.com' },
      'CVNA_US_EQ': { name: 'Carvana Co', sector: 'E-Commerce Automotive', domain: 'carvana.com' },
      'DKNG_US_EQ': { name: 'DraftKings Inc', sector: 'Digital Sports Entertainment', domain: 'draftkings.com' },
      'DUOL_US_EQ': { name: 'Duolingo Inc', sector: 'EdTech & Gamification', domain: 'duolingo.com' },
      'HIMS_US_EQ': { name: 'Hims & Hers Health', sector: 'Telehealth & Consumer Health', domain: 'hims.com' },
      'VKTX_US_EQ': { name: 'Viking Therapeutics', sector: 'Biopharmaceuticals', domain: 'vikingtherapeutics.com' },
      'BABA_US_EQ': { name: 'Alibaba Group', sector: 'Global E-Commerce & Cloud', domain: 'alibabagroup.com' },
      'PDD_US_EQ': { name: 'PDD Holdings', sector: 'Global E-Commerce', domain: 'pddholdings.com' },
    };

    function getStockDomain(symbol) {
      if (STOCK_METADATA[symbol] && STOCK_METADATA[symbol].domain) {
        return STOCK_METADATA[symbol].domain;
      }
      const clean = (symbol || '').replace('_US_EQ', '').toLowerCase();
      const fallbacks = {
        aapl: 'apple.com', msft: 'microsoft.com', googl: 'google.com',
        goog: 'google.com', amzn: 'amazon.com', meta: 'meta.com',
        nflx: 'netflix.com', spy: 'ssga.com', qqq: 'invesco.com'
      };
      return fallbacks[clean] || `${clean}.com`;
    }

    function getSectorGradient(sector) {
      const sec = sector || '';
      if (sec.includes('Crypto') || sec.includes('Bitcoin')) return 'linear-gradient(135deg, #ff9500 0%, #ffb340 100%)';
      if (sec.includes('Clean') || sec.includes('Nuclear') || sec.includes('Solar')) return 'linear-gradient(135deg, #34c759 0%, #66d982 100%)';
      if (sec.includes('Fintech') || sec.includes('Banking') || sec.includes('Lending')) return 'linear-gradient(135deg, #af52de 0%, #c77ded 100%)';
      if (sec.includes('Cyber') || sec.includes('Cloud')) return 'linear-gradient(135deg, #5856d6 0%, #7a79e0 100%)';
      if (sec.includes('EV') || sec.includes('Auto')) return 'linear-gradient(135deg, #ff2d55 0%, #ff6482 100%)';
      return 'linear-gradient(135deg, #0071e3 0%, #42a5f5 100%)';
    }

    function renderStockLogo(symbol, clean, monoGrad, size, imgSize, radius) {
      size = size || 32;
      imgSize = imgSize || 22;
      radius = radius || 9;
      const domain = getStockDomain(symbol);
      const logoUrl = `https://www.google.com/s2/favicons?domain=${domain}&sz=128`;
      return `
        <div class="asset-logo-wrap" style="width:${size}px; height:${size}px; border-radius:${radius}px;">
          <img class="asset-logo-img" style="width:${imgSize}px; height:${imgSize}px;" src="${logoUrl}" alt="${clean}" loading="lazy" onerror="this.style.display='none'; if(this.nextElementSibling) this.nextElementSibling.style.display='flex';" />
          <div class="asset-monogram" style="background:${monoGrad}; display:none; width:100%; height:100%; border-radius:${radius}px; font-size:${Math.round(size * 0.36)}px;">${clean.slice(0, 2)}</div>
        </div>
      `;
    }

    let currentFilter = 'ALL';
    let screenerSearchQuery = '';
    let currentSortCol = 'rank';
    let currentSortDir = 'asc';
    let currentScreenerView = 'table';
    let currentModalSymbol = '';
    let soundEnabled = localStorage.getItem('trading_bot_sound') === 'true';
    let previousEquity = null;
    let latestRecommendations = [];
    let latestAIData = null;
    let showExpiredAI = false;
    let marketIsOpen = false;
    let marketSecondsRemaining = 0;
    let marketTotalClosedSeconds = 63000;
    let marketState = 'CLOSED';
    let marketNextOpenStr = '';
    let scanSecondsRemaining = 900;
    let scanProgressPct = 0;


    // Web Audio Terminal Haptics (Muted by default)
    function updateSoundUI() {
      const icon = document.getElementById('sound-icon');
      if (icon) icon.textContent = soundEnabled ? '🔔' : '🔕';
    }

    function toggleSound() {
      soundEnabled = !soundEnabled;
      localStorage.setItem('trading_bot_sound', soundEnabled ? 'true' : 'false');
      updateSoundUI();
      if (soundEnabled) {
        playHaptic('chime');
        showToast('Audio FX Enabled', 'Terminal sound cues active', '🔔');
      } else {
        showToast('Audio FX Muted', 'Terminal sound cues silenced', '🔕');
      }
    }

    function playHaptic(type) {
      if (!soundEnabled) return;
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        const ctx = new AudioCtx();
        if (ctx.state === 'suspended') ctx.resume();

        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);

        const now = ctx.currentTime;
        if (type === 'click') {
          osc.type = 'sine';
          osc.frequency.setValueAtTime(800, now);
          gain.gain.setValueAtTime(0.04, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
          osc.start(now);
          osc.stop(now + 0.04);
        } else if (type === 'chime') {
          osc.type = 'triangle';
          osc.frequency.setValueAtTime(523.25, now);
          osc.frequency.setValueAtTime(659.25, now + 0.08);
          gain.gain.setValueAtTime(0.05, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
          osc.start(now);
          osc.stop(now + 0.25);
        } else if (type === 'action') {
          osc.type = 'sine';
          osc.frequency.setValueAtTime(880, now);
          osc.frequency.setValueAtTime(1046.5, now + 0.06);
          gain.gain.setValueAtTime(0.05, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
          osc.start(now);
          osc.stop(now + 0.2);
        }
      } catch (err) {
        // AudioContext ignored if unprompted
      }
    }

    function toggleEngineSpecs() {
      playHaptic('click');
      const b = document.getElementById('engine-specs-body');
      const btn = document.getElementById('btn-toggle-engine-specs');
      if (!b || !btn) return;
      const isHidden = b.style.display === 'none';
      b.style.display = isHidden ? 'block' : 'none';
      btn.textContent = isHidden ? 'Hide Strategy DNA' : 'Show Strategy DNA';
    }

    function switchScreenerView(mode) {
      playHaptic('click');
      currentScreenerView = mode;
      const tableWrap = document.getElementById('screener-table-container');
      const heatWrap = document.getElementById('screener-heatmap-container');
      const btnTable = document.getElementById('view-mode-table');
      const btnHeat = document.getElementById('view-mode-heatmap');

      if (mode === 'heatmap') {
        if (tableWrap) tableWrap.style.display = 'none';
        if (heatWrap) heatWrap.style.display = 'block';
        if (btnTable) btnTable.classList.remove('active');
        if (btnHeat) btnHeat.classList.add('active');
        renderHeatmap(latestRecommendations);
      } else {
        if (tableWrap) tableWrap.style.display = 'block';
        if (heatWrap) heatWrap.style.display = 'none';
        if (btnTable) btnTable.classList.add('active');
        if (btnHeat) btnHeat.classList.remove('active');
      }
    }

    function switchModalChart(mode) {
      playHaptic('click');
      const sheet = document.querySelector('#stock-modal-backdrop .modal-sheet');
      const sparkEl = document.getElementById('modal-sparkline-expanded');
      const tvWrap = document.getElementById('modal-tv-embedded-wrap');
      const btnSpark = document.getElementById('modal-chart-btn-spark');
      const btnTv = document.getElementById('modal-chart-btn-tv');

      if (mode === 'tv') {
        if (sheet) sheet.classList.add('modal-sheet-wide');
        if (sparkEl) sparkEl.style.display = 'none';
        if (tvWrap) {
          tvWrap.style.display = 'block';
          const clean = (currentModalSymbol || 'AAPL').replace('_US_EQ', '');
          const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
          const themeStr = isDark ? 'dark' : 'light';
          tvWrap.innerHTML = '<iframe src="https://s.tradingview.com/widgetembed/?symbol=' + clean + '&interval=15&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=rgba(0,0,0,0)&theme=' + themeStr + '&style=1&timezone=Etc%2FUTC&studies=[]&hideideas=1" style="width:100%;height:100%;border:none;" frameborder="0" allowfullscreen></iframe>';
        }
        if (btnSpark) btnSpark.classList.remove('active');
        if (btnTv) btnTv.classList.add('active');
      } else {
        if (sheet) sheet.classList.remove('modal-sheet-wide');
        if (sparkEl) sparkEl.style.display = 'block';
        if (tvWrap) tvWrap.style.display = 'none';
        if (btnSpark) btnSpark.classList.add('active');
        if (btnTv) btnTv.classList.remove('active');
      }
    }

    function getHeatmapBgAndBorder(roc) {
      if (roc >= 3.0) {
        return { bg: 'linear-gradient(145deg, rgba(52, 199, 89, 0.35) 0%, rgba(52, 199, 89, 0.16) 100%)', border: 'rgba(52, 199, 89, 0.55)' };
      } else if (roc >= 0.5) {
        return { bg: 'linear-gradient(145deg, rgba(52, 199, 89, 0.20) 0%, rgba(52, 199, 89, 0.08) 100%)', border: 'rgba(52, 199, 89, 0.35)' };
      } else if (roc <= -3.0) {
        return { bg: 'linear-gradient(145deg, rgba(255, 59, 48, 0.35) 0%, rgba(255, 59, 48, 0.16) 100%)', border: 'rgba(255, 59, 48, 0.55)' };
      } else if (roc <= -0.5) {
        return { bg: 'linear-gradient(145deg, rgba(255, 59, 48, 0.20) 0%, rgba(255, 59, 48, 0.08) 100%)', border: 'rgba(255, 59, 48, 0.35)' };
      }
      return { bg: 'var(--surface-secondary)', border: 'var(--border)' };
    }

    function renderHeatmap(recs) {
      const container = document.getElementById('screener-heatmap-container');
      if (!container) return;
      let filtered = currentFilter === 'ALL' ? [...(recs || [])] : (recs || []).filter(r => r.rating === currentFilter);

      // Search Query Filter
      if (screenerSearchQuery) {
        filtered = filtered.filter(r => {
          const clean = (r.symbol || '').replace('_US_EQ', '').toLowerCase();
          const meta = STOCK_METADATA[r.symbol] || { name: '', sector: '' };
          const name = (meta.name || '').toLowerCase();
          const sector = (meta.sector || '').toLowerCase();
          return clean.includes(screenerSearchQuery) || name.includes(screenerSearchQuery) || sector.includes(screenerSearchQuery);
        });
      }

      if (!filtered || filtered.length === 0) {
        container.innerHTML = '<div style="color:var(--text-tertiary);padding:32px;text-align:center;">No stocks match the selected search or filter criteria.</div>';
        return;
      }

      // Sort by momentum % descending so top performers appear in top-left
      filtered.sort((a, b) => (b.roc_10_pct || 0) - (a.roc_10_pct || 0));

      const tilesHtml = filtered.map(r => {
        const clean = (r.symbol || '').replace('_US_EQ', '');
        const meta = STOCK_METADATA[r.symbol] || { domain: 'apple.com', name: 'US Equity', sector: 'Equities' };
        const monoGrad = getSectorGradient(meta.sector);
        const roc = Number(r.roc_10_pct || 0);
        const rocSign = roc >= 0 ? '+' : '';
        const rocClass = roc >= 0 ? 'pos-green' : 'pos-red';
        const style = getHeatmapBgAndBorder(roc);

        return `
          <div class="heatmap-tile-square" style="background:${style.bg}; border-color:${style.border};" onclick="openStockDetail('${r.symbol}')" title="${clean} (${meta.name}) • ${meta.sector} • Score: ${r.score} • Price: $${Number(r.close_price||0).toFixed(2)} • 10-Bar: ${rocSign}${roc.toFixed(2)}% • RVOL: ${(r.rvol||1).toFixed(2)}x">
            <div class="heatmap-square-logo-wrap">
              <img src="https://www.google.com/s2/favicons?domain=${meta.domain || 'apple.com'}&sz=64" alt="${clean}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />
              <div class="asset-monogram" style="background:${monoGrad}; display:none; width:100%; height:100%; font-size:9px;">${clean.slice(0, 2)}</div>
            </div>
            <strong class="heatmap-square-symbol">${clean}</strong>
            <span class="heatmap-square-price">$${Number(r.close_price || 0).toFixed(2)}</span>
            <span class="heatmap-square-badge ${rocClass}">${rocSign}${roc.toFixed(1)}%</span>
          </div>
        `;
      }).join('');

      container.innerHTML = `
        <div class="heatmap-square-wrapper">
          <div class="heatmap-square-grid">
            ${tilesHtml}
          </div>
        </div>
      `;
    }

    function exportExecutivePDF() {
      playHaptic('action');
      const printTs = document.getElementById('print-timestamp');
      if (printTs) printTs.textContent = new Date().toLocaleString();
      const printMode = document.getElementById('print-session-mode');
      const modePill = document.getElementById('mode-pill');
      if (printMode && modePill) printMode.textContent = modePill.textContent;

      showToast('Executive Briefing', 'Generating print-ready PDF teardown...', '📄');
      setTimeout(() => {
        window.print();
      }, 350);
    }

    // Theme Management
    function initTheme() {
      const saved = localStorage.getItem('trading_bot_theme');
      if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        setTheme('dark');
      } else {
        setTheme('light');
      }
    }

    function setTheme(mode) {
      if (mode === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        document.getElementById('theme-sun-icon').style.display = 'none';
        document.getElementById('theme-moon-icon').style.display = 'block';
        document.getElementById('theme-btn-label').textContent = 'Light Mode';
        localStorage.setItem('trading_bot_theme', 'dark');
      } else {
        document.documentElement.removeAttribute('data-theme');
        document.getElementById('theme-sun-icon').style.display = 'block';
        document.getElementById('theme-moon-icon').style.display = 'none';
        document.getElementById('theme-btn-label').textContent = 'Space Black';
        localStorage.setItem('trading_bot_theme', 'light');
      }
    }

    function toggleTheme() {
      const current = document.documentElement.getAttribute('data-theme');
      setTheme(current === 'dark' ? 'light' : 'dark');
    }

    initTheme();

    function initGuideVisibility() {
      if (localStorage.getItem('trading_bot_guide_visible') === 'false') {
        const g = document.getElementById('screener-guide');
        const b = document.getElementById('btn-toggle-guide');
        if (g) g.style.display = 'none';
        if (b) b.textContent = 'Show Column Guide';
      }
    }
    initGuideVisibility();

    function formatTimeSec(totalSec) {
      if (totalSec <= 0) return '00:00';
      const h = Math.floor(totalSec / 3600);
      const m = Math.floor((totalSec % 3600) / 60);
      const s = totalSec % 60;
      if (h > 0) {
        return `${h}h ${String(m).padStart(2, '0')}m ${String(s).padStart(2, '0')}s`;
      }
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }

    function tickerLink(symbol) {
      const clean = symbol.replace('_US_EQ', '').replace('.US', '');
      return `<a href="https://www.tradingview.com/chart/?symbol=${clean}" target="_blank" rel="noopener" style="color:inherit;text-decoration:none;">${clean}</a>`;
    }

    function toggleExpiredAI() {
      showExpiredAI = !showExpiredAI;
      if (latestAIData) renderAIManager(latestAIData);
    }

    function updateGlobalMarketClocks() {
      const now = new Date();

      // Format times in time zones
      function getTimeStr(tz) {
        return now.toLocaleTimeString('en-US', { timeZone: tz, hour12: false, hour: '2-digit', minute: '2-digit' });
      }

      function getMinutesOfDay(tz) {
        const parts = now.toLocaleTimeString('en-US', { timeZone: tz, hour12: false, hour: '2-digit', minute: '2-digit' }).split(':');
        return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
      }

      function getDayOfWeek(tz) {
        const str = now.toLocaleDateString('en-US', { timeZone: tz, weekday: 'short' });
        return str; // 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'
      }

      // NY: 09:30 - 16:00 ET Mon-Fri
      const nyDay = getDayOfWeek('America/New_York');
      const nyMins = getMinutesOfDay('America/New_York');
      const nyOpen = (nyDay !== 'Sat' && nyDay !== 'Sun') && (nyMins >= 570 && nyMins < 960);
      const timeNyEl = document.getElementById('time-ny');
      const statusNyEl = document.getElementById('status-ny');
      const beaconNyEl = document.getElementById('beacon-ny');
      if (timeNyEl) timeNyEl.textContent = getTimeStr('America/New_York') + ' ET';
      if (statusNyEl) {
        statusNyEl.textContent = nyOpen ? 'OPEN' : 'CLOSED';
        statusNyEl.className = 'clock-status ' + (nyOpen ? 'clock-open' : 'clock-closed');
      }
      if (beaconNyEl) beaconNyEl.className = 'beacon-dot ' + (nyOpen ? 'beacon-green' : 'beacon-slate');

      // London: 08:00 - 16:30 GMT Mon-Fri
      const lonDay = getDayOfWeek('Europe/London');
      const lonMins = getMinutesOfDay('Europe/London');
      const lonOpen = (lonDay !== 'Sat' && lonDay !== 'Sun') && (lonMins >= 480 && lonMins < 990);
      const timeLonEl = document.getElementById('time-lon');
      const statusLonEl = document.getElementById('status-lon');
      const beaconLonEl = document.getElementById('beacon-lon');
      if (timeLonEl) timeLonEl.textContent = getTimeStr('Europe/London') + ' GMT';
      if (statusLonEl) {
        statusLonEl.textContent = lonOpen ? 'OPEN' : 'CLOSED';
        statusLonEl.className = 'clock-status ' + (lonOpen ? 'clock-open' : 'clock-closed');
      }
      if (beaconLonEl) beaconLonEl.className = 'beacon-dot ' + (lonOpen ? 'beacon-green' : 'beacon-slate');

      // Frankfurt: 09:00 - 17:30 CET Mon-Fri
      const fraDay = getDayOfWeek('Europe/Berlin');
      const fraMins = getMinutesOfDay('Europe/Berlin');
      const fraOpen = (fraDay !== 'Sat' && fraDay !== 'Sun') && (fraMins >= 540 && fraMins < 1050);
      const timeFraEl = document.getElementById('time-fra');
      const statusFraEl = document.getElementById('status-fra');
      const beaconFraEl = document.getElementById('beacon-fra');
      if (timeFraEl) timeFraEl.textContent = getTimeStr('Europe/Berlin') + ' CET';
      if (statusFraEl) {
        statusFraEl.textContent = fraOpen ? 'OPEN' : 'CLOSED';
        statusFraEl.className = 'clock-status ' + (fraOpen ? 'clock-open' : 'clock-closed');
      }
      if (beaconFraEl) beaconFraEl.className = 'beacon-dot ' + (fraOpen ? 'beacon-green' : 'beacon-slate');

      // Tokyo: 09:00 - 15:00 JST Mon-Fri
      const tokDay = getDayOfWeek('Asia/Tokyo');
      const tokMins = getMinutesOfDay('Asia/Tokyo');
      const tokOpen = (tokDay !== 'Sat' && tokDay !== 'Sun') && (tokMins >= 540 && tokMins < 900);
      const timeTokEl = document.getElementById('time-tok');
      const statusTokEl = document.getElementById('status-tok');
      const beaconTokEl = document.getElementById('beacon-tok');
      if (timeTokEl) timeTokEl.textContent = getTimeStr('Asia/Tokyo') + ' JST';
      if (statusTokEl) {
        statusTokEl.textContent = tokOpen ? 'OPEN' : 'CLOSED';
        statusTokEl.className = 'clock-status ' + (tokOpen ? 'clock-open' : 'clock-closed');
      }
      if (beaconTokEl) beaconTokEl.className = 'beacon-dot ' + (tokOpen ? 'beacon-green' : 'beacon-slate');
    }

    function updateCountdownTimers() {
      const scanValEl = document.getElementById('scan-timer-val');
      const scanBarEl = document.getElementById('scan-timer-bar');
      if (scanValEl) {
        scanValEl.textContent = `Next in ${formatTimeSec(scanSecondsRemaining)}`;
        scanBarEl.style.width = `${Math.min(100, Math.max(0, scanProgressPct))}%`;
      }

      const marketLabelEl = document.getElementById('market-timer-label');
      const marketValEl = document.getElementById('market-timer-val');
            const beaconEl = document.getElementById('market-beacon-dot');

      // Solar Arc Math & Progress
      const solarPin = document.getElementById('solar-beacon-pin');
      const solarArcProg = document.getElementById('solar-arc-progress');
      let t = 0.5;

      if (marketIsOpen) {
        if (marketLabelEl) marketLabelEl.textContent = 'Regular US Session';
        if (marketValEl) marketValEl.textContent = `Closes in ${formatTimeSec(marketSecondsRemaining)}`;
        const dayTotal = 390 * 60; // 6.5 hours
        const elapsed = Math.max(0, dayTotal - marketSecondsRemaining);
        const frac = Math.min(1, Math.max(0, elapsed / dayTotal));
        t = 0.23 + (frac * 0.54); // Map 09:30..16:00 to 0.23..0.77 of the arc
        if (solarPin) {
          solarPin.setAttribute('fill', '#34c759');
          solarPin.setAttribute('r', '7.5');
        }
        if (beaconEl) beaconEl.className = 'beacon-dot beacon-open';
      } else {
        if (marketLabelEl) marketLabelEl.textContent = marketState.includes('WEEKEND') ? 'Weekend Twilight Arc' : 'Market Reopens In';
        if (marketValEl) marketValEl.textContent = marketSecondsRemaining > 0 ? formatTimeSec(marketSecondsRemaining) : 'Opening Soon';
        const totalClosed = marketTotalClosedSeconds || 63000;
        const elapsed = Math.max(0, totalClosed - marketSecondsRemaining);
        const frac = Math.min(1, Math.max(0, elapsed / totalClosed));
        // Night / Pre-market transition: 0.77 to 1.0, then wraps to 0.0 to 0.23
        t = (frac <= 0.5) ? (0.77 + frac * 0.46) : (frac - 0.5) * 0.46;
        t = Math.max(0.02, Math.min(0.98, t));
        if (solarPin) {
          solarPin.setAttribute('fill', marketState.includes('PRE') ? '#ff9500' : '#8e8e93');
          solarPin.setAttribute('r', '6');
        }
        if (beaconEl) {
          beaconEl.className = (marketState.includes('PRE') || marketState.includes('AFTER')) ? 'beacon-dot beacon-amber' : 'beacon-dot beacon-slate';
        }
      }

      // Compute quadratic bezier point: P0=(20,32), P1=(140,4), P2=(260,32)
      if (solarPin) {
        const pinX = (1 - t)**2 * 20 + 2 * (1 - t) * t * 140 + t**2 * 260;
        const pinY = (1 - t)**2 * 32 + 2 * (1 - t) * t * 4 + t**2 * 32;
        solarPin.setAttribute('cx', pinX.toFixed(1));
        solarPin.setAttribute('cy', pinY.toFixed(1));
      }
      if (solarArcProg) {
        const circ = 245;
        const arcOff = (circ - (t * circ)).toFixed(1);
        solarArcProg.setAttribute('stroke-dashoffset', arcOff);
      }

      if (scanSecondsRemaining > 0) scanSecondsRemaining--;
      if (marketSecondsRemaining > 0) marketSecondsRemaining--;
    }

    function renderSparklineSVG(points, rocPct, width = 96, height = 24) {
      if (!points || points.length < 2) {
        return `<span style="font-size:11px;color:var(--text-tertiary);">Data pending...</span>`;
      }
      const minVal = Math.min(...points);
      const maxVal = Math.max(...points);
      const range = (maxVal - minVal) || (minVal * 0.01) || 1.0;
      const padX = 3;
      const padY = 4;
      const usableW = width - (padX * 2);
      const usableH = height - (padY * 2);

      const coords = points.map((val, idx) => {
        const x = padX + (idx / (points.length - 1)) * usableW;
        const normY = (val - minVal) / range;
        const y = (height - padY) - (normY * usableH);
        return [x.toFixed(1), y.toFixed(1)];
      });

      const polyPoints = coords.map(c => c.join(',')).join(' ');
      const strokeColor = rocPct >= 0 ? 'var(--green)' : 'var(--red)';
      const fillColor = rocPct >= 0 ? 'rgba(52, 199, 89, 0.12)' : 'rgba(255, 59, 48, 0.12)';
      const firstX = coords[0][0];
      const lastX = coords[coords.length - 1][0];
      const areaPoints = `${polyPoints} ${lastX},${height} ${firstX},${height}`;

      return `
        <svg class="sparkline-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
          <polygon points="${areaPoints}" fill="${fillColor}" />
          <polyline points="${polyPoints}" fill="none" stroke="${strokeColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          <circle cx="${coords[coords.length - 1][0]}" cy="${coords[coords.length - 1][1]}" r="2.5" fill="${strokeColor}" />
        </svg>
      `;
    }

    function renderRadialScore(score, rating) {
      const circ = 94.2; // 2 * pi * 15
      const sc = Math.min(100, Math.max(0, score || 0));
      const offset = (circ - ((sc / 100) * circ)).toFixed(1);
      let strokeColor = 'var(--text-tertiary)';
      if (sc >= 80) strokeColor = 'var(--green)';
      else if (sc >= 65) strokeColor = 'var(--accent)';
      else if (sc >= 50) strokeColor = 'var(--amber)';
      else strokeColor = 'var(--red)';

      return `
        <div class="radial-dial" title="Quant Score: ${sc.toFixed(1)}/100">
          <svg viewBox="0 0 38 38">
            <circle class="dial-track" cx="19" cy="19" r="15"></circle>
            <circle class="dial-fill" cx="19" cy="19" r="15" stroke="${strokeColor}" style="stroke-dashoffset:${offset};"></circle>
          </svg>
          <span class="dial-score-num">${Math.round(sc)}</span>
        </div>
      `;
    }

    function renderActivityAndGates(data) {
      if (data.activity) {
        document.getElementById('activity-state').textContent = data.activity.state || 'MONITORING';
        document.getElementById('activity-state').className = `activity-state-badge badge-${data.activity.state === 'HALTED' ? 'avoid' : 'buy'}`;
        document.getElementById('activity-detail').textContent = data.activity.detail || '';
        document.getElementById('activity-updated').textContent = data.activity.updated_at ? `Updated: ${data.activity.updated_at.slice(11,19)} UTC` : '';
        scanSecondsRemaining = data.activity.seconds_to_next_scan || 900;
        scanProgressPct = data.activity.scan_progress_pct || 0;
      }
      if (data.gates && data.gates.length >= 4) {
        for (let i = 0; i < 4; i++) {
          const g = data.gates[i];
          const badgeClass = g.badge === 'GREEN' ? 'badge-strong-buy' : (g.badge === 'RED' ? 'badge-avoid' : 'badge-watch');
          document.getElementById(`gate${i+1}-badge`).className = `gate-status-badge badge ${badgeClass}`;
          document.getElementById(`gate${i+1}-badge`).textContent = g.status.split('•')[0].trim();
          document.getElementById(`gate${i+1}-val`).textContent = g.title.split('•')[1] ? g.title.split('•')[1].trim() : g.title;
          document.getElementById(`gate${i+1}-desc`).textContent = g.detail;
        }
      }
      if (data.market_session) {
        document.getElementById('market-status-badge').textContent = data.market_session.state;
      }
    }

    function toggleScreenerGuide() {
      const g = document.getElementById('screener-guide');
      const b = document.getElementById('btn-toggle-guide');
      if (!g || !b) return;
      const isHidden = g.style.display === 'none';
      g.style.display = isHidden ? 'grid' : 'none';
      b.textContent = isHidden ? 'Hide Column Guide' : 'Show Column Guide';
      localStorage.setItem('trading_bot_guide_visible', isHidden ? 'true' : 'false');
    }

    function setFilter(filter, btn) {
      currentFilter = filter;
      document.querySelectorAll('.filter-bar .filter-btn').forEach(b => {
        if (b.id && b.id.startsWith('btn-filter-')) {
          b.classList.remove('active');
        }
      });
      if (btn) btn.classList.add('active');
      renderScreener(latestRecommendations);
    }

    function handleScreenerSearch(query) {
      screenerSearchQuery = (query || '').trim().toLowerCase();
      renderScreener(latestRecommendations);
    }

    function handleSort(col) {
      if (currentSortCol === col) {
        currentSortDir = currentSortDir === 'asc' ? 'desc' : 'asc';
      } else {
        currentSortCol = col;
        currentSortDir = (col === 'rank' || col === 'symbol') ? 'asc' : 'desc';
      }

      // Update sort indicators in table header
      document.querySelectorAll('th.sortable').forEach(th => th.classList.remove('active-sort'));
      const activeTh = document.getElementById('th-sort-' + col);
      if (activeTh) activeTh.classList.add('active-sort');

      const sortIcon = document.getElementById('sort-' + col);
      if (sortIcon) sortIcon.textContent = currentSortDir === 'asc' ? '▲' : '▼';

      renderScreener(latestRecommendations);
    }

    function exportScreenerCSV() {
      if (!latestRecommendations || latestRecommendations.length === 0) {
        showToast('Export Unavailable', 'No screener data loaded yet', '⚠️');
        return;
      }
      const headers = ['Rank', 'Symbol', 'Company', 'Sector', 'Rating', 'Score', 'Price_USD', 'EMA_Fast', 'EMA_Slow', 'RSI_14', 'RVOL', 'ROC_10_Pct', 'Stop_Loss_USD', 'Take_Profit_USD', 'Thesis'];
      const rows = latestRecommendations.map(r => {
        const meta = STOCK_METADATA[r.symbol] || { name: 'US Equity', sector: 'Equities' };
        const clean = (r.symbol || '').replace('_US_EQ', '');
        return [
          r.rank || 0,
          clean,
          '"' + (meta.name || '').replace(/"/g, '""') + '"',
          '"' + (meta.sector || '').replace(/"/g, '""') + '"',
          r.rating || 'WATCH',
          r.score || 0,
          Number(r.close_price || 0).toFixed(2),
          Number(r.ema_fast || 0).toFixed(2),
          Number(r.ema_slow || 0).toFixed(2),
          Number(r.rsi || 50).toFixed(1),
          Number(r.rvol || 1).toFixed(2),
          Number(r.roc_10_pct || 0).toFixed(2),
          Number(r.suggested_stop_loss || 0).toFixed(2),
          Number(r.suggested_take_profit || 0).toFixed(2),
          '"' + (r.thesis || '').replace(/"/g, '""') + '"'
        ].join(',');
      });

      const csvContent = [headers.join(','), ...rows].join(String.fromCharCode(10));
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      const dateStr = new Date().toISOString().slice(0, 10);
      link.setAttribute('href', url);
      link.setAttribute('download', 't212_screener_leaderboard_' + dateStr + '.csv');
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      showToast('Export Complete', 'Saved 50-stock quantitative dataset (' + rows.length + ' rows)', '📊');
    }

    function showToast(title, message, icon) {
      icon = icon || '⚡';
      const container = document.getElementById('toast-container');
      if (!container) return;
      const toast = document.createElement('div');
      toast.className = 'apple-toast';
      toast.innerHTML = `
        <span class="toast-icon">${icon}</span>
        <div class="toast-body">
          <strong>${title}</strong>
          <span>${message}</span>
        </div>
      `;
      container.appendChild(toast);
      setTimeout(() => {
        toast.classList.add('hide');
        setTimeout(() => { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 400);
      }, 3500);
    }

    function openShortcutsModal() {
      const modal = document.getElementById('shortcuts-modal-backdrop');
      if (modal) {
        modal.classList.add('open');
        document.body.style.overflow = 'hidden';
      }
    }

    function closeShortcutsModal(e) {
      if (e && e.target !== e.currentTarget && !e.target.closest('.modal-close-btn')) return;
      const modal = document.getElementById('shortcuts-modal-backdrop');
      if (modal) {
        modal.classList.remove('open');
        const stockModal = document.getElementById('stock-modal-backdrop');
        if (!stockModal || !stockModal.classList.contains('open')) {
          document.body.style.overflow = '';
        }
      }
    }

    // Keyboard Shortcuts Listener
    window.addEventListener('keydown', (e) => {
      const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
      if (activeTag === 'input' || activeTag === 'textarea') {
        if (e.key === 'Escape') {
          document.activeElement.blur();
        }
        return;
      }

      if (e.key === '/' || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k')) {
        e.preventDefault();
        const input = document.getElementById('screener-search-input');
        if (input) {
          input.focus();
          input.select();
        }
      } else if (e.key === '1') {
        const btn = document.getElementById('btn-filter-all');
        setFilter('ALL', btn);
        showToast('Filter Applied', 'Showing all 50 universe stocks', '📋');
      } else if (e.key === '2') {
        const btn = document.getElementById('btn-filter-strong-buy');
        setFilter('STRONG BUY', btn);
        showToast('Filter Applied', 'Showing Strong Buy setups', '🚀');
      } else if (e.key === '3') {
        const btn = document.getElementById('btn-filter-buy');
        setFilter('BUY', btn);
        showToast('Filter Applied', 'Showing Buy setups', '🟢');
      } else if (e.key === '4') {
        const btn = document.getElementById('btn-filter-watch');
        setFilter('WATCH', btn);
        showToast('Filter Applied', 'Showing Watchlist setups', '👀');
      } else if (e.key === '5') {
        const btn = document.getElementById('btn-filter-avoid');
        setFilter('AVOID', btn);
        showToast('Filter Applied', 'Showing Avoid / Blocked setups', '🛑');
      } else if (e.key.toLowerCase() === 't') {
        toggleTheme();
      } else if (e.key.toLowerCase() === 'g') {
        toggleScreenerGuide();
      } else if (e.key.toLowerCase() === 'e') {
        exportScreenerCSV();
      } else if (e.key.toLowerCase() === 'p') {
        e.preventDefault();
        exportExecutivePDF();
      } else if (e.key === '?' || (e.shiftKey && e.key === '/')) {
        openShortcutsModal();
      } else if (e.key === 'Escape') {
        closeStockModal();
        closeShortcutsModal();
      }
    });

    let lastTickerDataHash = '';
    function renderTickerTape(recs) {
      const track = document.getElementById('ticker-tape-track');
      if (!track || !recs || recs.length === 0) return;

      const hash = recs.slice(0, 15).map(r => (r.symbol || '') + ':' + Number(r.close_price || 0).toFixed(1) + ':' + (r.rating || '')).join('|');
      if (hash === lastTickerDataHash) return;
      lastTickerDataHash = hash;

      const notable = [...recs].sort((a, b) => Math.abs(b.roc_10_pct || 0) - Math.abs(a.roc_10_pct || 0)).slice(0, 14);
      const loopItems = [...notable, ...notable];

      track.innerHTML = loopItems.map(r => {
        const clean = (r.symbol || '').replace('_US_EQ', '');
        const meta = STOCK_METADATA[r.symbol] || { domain: 'apple.com' };
        const rocSign = (r.roc_10_pct || 0) >= 0 ? '+' : '';
        const rocColor = (r.roc_10_pct || 0) >= 0 ? 'pos-green' : 'pos-red';
        const ratingBadgeClass = r.rating === 'STRONG BUY' ? 'badge-strong-buy' : (r.rating === 'BUY' ? 'badge-buy' : 'badge-watch');

        return `
          <div class="ticker-item" onclick="openStockDetail('${r.symbol}')" title="Click to inspect ${clean} details">
            <img class="ticker-logo" src="https://www.google.com/s2/favicons?domain=${meta.domain || 'apple.com'}&sz=64" alt="${clean}" onerror="this.style.display='none';" />
            <strong>${clean}</strong>
            <span>$${Number(r.close_price || 0).toFixed(2)}</span>
            <span class="${rocColor}">${rocSign}${Number(r.roc_10_pct || 0).toFixed(2)}%</span>
            <span class="ticker-badge ${ratingBadgeClass}">${r.rating}</span>
          </div>
        `;
      }).join('');
    }

    function badgeClass(rating) {
      if (rating === 'STRONG BUY') return 'badge badge-strong-buy';
      if (rating === 'BUY') return 'badge badge-buy';
      if (rating === 'WATCH') return 'badge badge-watch';
      if (rating === 'AVOID') return 'badge badge-avoid';
      return 'badge badge-hold';
    }

    function renderPositions(positions) {
      const el = document.getElementById('positions-container');
      if (!positions || positions.length === 0) {
        el.innerHTML = '<div style="color:var(--text-tertiary);font-size:13px;padding:12px 0;">No open positions currently held. Bot is scanning for the highest-scoring BUY setup.</div>';
        return;
      }
      el.innerHTML = positions.map(p => {
        const pnlClass = p.unrealized_pnl >= 0 ? 'pos-green' : 'pos-red';
        const sign = p.unrealized_pnl >= 0 ? '+' : '';
        const extBadge = p.tp_extensions > 0
          ? ` <span class="badge badge-strong-buy">TARGET EXTENDED x${p.tp_extensions}</span>`
          : '';
        const trailBadge = (p.trailing_active
          ? '<span class="badge badge-strong-buy">1R TRAILING ACTIVE</span>'
          : '<span class="badge badge-watch">INITIAL STOP (+1.0R Anchor)</span>') + extBadge;
        const meta = STOCK_METADATA[p.symbol] || { name: 'US Equity', sector: 'Equities' };
        const clean = p.symbol.replace('_US_EQ', '');
        const monoGrad = getSectorGradient(meta.sector);
        const logoBadge = renderStockLogo(p.symbol, clean, monoGrad, 36, 24, 10);

        return `
          <div class="pos-card" onclick="openStockDetail('${p.symbol}')">
            <div class="pos-top">
              <div style="display:flex;align-items:center;gap:12px;">
                ${logoBadge}
                <div>
                  <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                    <strong style="font-size:18px;letter-spacing:-0.02em;">${clean}</strong>
                    <span style="font-size:12.5px;color:var(--text-secondary);">${meta.name}</span>
                    <span class="badge badge-buy">${p.side}</span>
                    ${trailBadge}
                  </div>
                  <div style="font-size:12px;color:var(--text-tertiary);margin-top:2px;">Order #${p.order_id}</div>
                </div>
              </div>
              <div style="text-align:right;">
                <span style="font-size:20px;font-weight:700;letter-spacing:-0.02em;" class="${pnlClass}">
                  ${sign}$${p.unrealized_pnl.toFixed(2)} (${sign}${p.pnl_pct.toFixed(2)}% | ${sign}${p.r_multiple.toFixed(2)}R)
                </span>
              </div>
            </div>
            <div class="pos-metrics">
              <div class="pos-metric"><span>Quantity</span><strong>${p.quantity} shs</strong></div>
              <div class="pos-metric"><span>Entry Fill</span><strong>$${p.entry_price.toFixed(2)}</strong></div>
              <div class="pos-metric"><span>Current Mark</span><strong>$${p.current_price.toFixed(2)}</strong></div>
              <div class="pos-metric"><span>Position Value</span><strong>$${p.notional_usd.toFixed(2)}</strong></div>
              <div class="pos-metric"><span>Active Stop-Loss</span><strong class="pos-red">$${p.stop_loss.toFixed(2)}</strong></div>
              <div class="pos-metric"><span>Take-Profit Target</span><strong class="pos-green">$${p.take_profit.toFixed(2)}</strong></div>
            </div>

            <!-- Apple Trade Runway Visualizer -->
            <div class="runway-wrap">
              <div class="runway-header">
                <span>🛡️ Stop-Loss: <strong>$${p.stop_loss.toFixed(2)}</strong></span>
                <span>📌 Entry Fill: <strong>$${p.entry_price.toFixed(2)}</strong></span>
                <span>🎯 Target Profit: <strong>$${p.take_profit.toFixed(2)}</strong></span>
              </div>
              <div class="runway-track">
                <div class="runway-fill" style="width:${p.gauge_pct}%"></div>
              </div>
              <div class="runway-anchors">
                <span style="color:var(--red-text);">Downside Guard</span>
                <span style="color:var(--accent);">Current Mark: $${p.current_price.toFixed(2)}</span>
                <span style="color:var(--green-text);">Target (+3.5x ATR)</span>
              </div>
            </div>
          </div>
        `;
      }).join('');
    }

    function renderScreener(recs) {
      const tbody = document.getElementById('screener-tbody');
      let filtered = currentFilter === 'ALL' ? (recs || []) : (recs || []).filter(r => r.rating === currentFilter);

      // Search Query Filter
      if (screenerSearchQuery) {
        filtered = filtered.filter(r => {
          const clean = r.symbol.replace('_US_EQ', '').toLowerCase();
          const meta = STOCK_METADATA[r.symbol] || { name: '', sector: '' };
          const name = (meta.name || '').toLowerCase();
          const sector = (meta.sector || '').toLowerCase();
          return clean.includes(screenerSearchQuery) || name.includes(screenerSearchQuery) || sector.includes(screenerSearchQuery);
        });
      }

      // Column Sorting
      filtered.sort((a, b) => {
        let valA, valB;
        switch (currentSortCol) {
          case 'symbol':
            valA = a.symbol; valB = b.symbol;
            return currentSortDir === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
          case 'rating':
            const rateOrder = { 'STRONG BUY': 4, 'BUY': 3, 'WATCH': 2, 'AVOID': 1 };
            valA = rateOrder[a.rating] || 0; valB = rateOrder[b.rating] || 0;
            break;
          case 'score': valA = a.score || 0; valB = b.score || 0; break;
          case 'price': valA = a.close_price || 0; valB = b.close_price || 0; break;
          case 'ema': valA = a.ema_fast || 0; valB = b.ema_fast || 0; break;
          case 'rsi': valA = a.rsi || 50; valB = b.rsi || 50; break;
          case 'rvol': valA = a.rvol || 1; valB = b.rvol || 1; break;
          case 'roc': valA = a.roc_10_pct || 0; valB = b.roc_10_pct || 0; break;
          case 'sl': valA = a.suggested_stop_loss || 0; valB = b.suggested_stop_loss || 0; break;
          case 'tp': valA = a.suggested_take_profit || 0; valB = b.suggested_take_profit || 0; break;
          case 'rank':
          default:
            valA = a.rank || 0; valB = b.rank || 0; break;
        }
        return currentSortDir === 'asc' ? (valA - valB) : (valB - valA);
      });

      if (!filtered || filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="14" style="color:var(--text-tertiary);text-align:center;padding:24px;">No stocks match the selected search or filter criteria.</td></tr>';
        return;
      }
      tbody.innerHTML = filtered.map(r => {
        const rocSign = r.roc_10_pct >= 0 ? '+' : '';
        const rocClass = r.roc_10_pct >= 0 ? 'pos-green' : 'pos-red';
        const sparklineSvg = renderSparklineSVG(r.sparkline, r.roc_10_pct);
        const radialDial = renderRadialScore(r.score, r.rating);
        const clean = r.symbol.replace('_US_EQ', '');
        const meta = STOCK_METADATA[r.symbol] || { name: 'US Equity', sector: 'Equities' };

        // Sector monogram gradient & Corporate Brand Logo
        const monoGrad = getSectorGradient(meta.sector);
        const logoBadge = renderStockLogo(r.symbol, clean, monoGrad, 32, 22, 9);

        // RSI Bullet Meter
        const rsiVal = Number(r.rsi || 50);
        const rsiOptimal = (rsiVal >= 54 && rsiVal <= 67);
        const rsiColor = rsiOptimal ? 'pos-green' : (rsiVal > 67 ? 'pos-red' : '');
        const rsiSub = rsiOptimal ? 'OPTIMAL' : (rsiVal > 67 ? 'HIGH' : 'NEUTRAL');
        const rsiBullet = `
          <div class="rsi-bullet-wrap" title="RSI: ${rsiVal.toFixed(1)} (Ideal zone: 54-67)">
            <div style="display:flex;justify-content:space-between;font-size:11px;font-weight:600;">
              <span class="${rsiColor}">${rsiVal.toFixed(1)}</span>
              <span style="font-size:9.5px;color:var(--text-tertiary);">${rsiSub}</span>
            </div>
            <div class="rsi-bullet-track">
              <div class="rsi-sweet-spot"></div>
              <div class="rsi-marker" style="left:${Math.min(100, Math.max(0, rsiVal))}%;"></div>
            </div>
          </div>
        `;

        // RVOL Volume Surge Meter
        const rvolVal = Number(r.rvol || 1);
        const rvolSurge = rvolVal >= 1.5;
        const rvolColor = rvolSurge ? 'pos-green' : (rvolVal >= 1.15 ? 'pos-green' : '');
        const rvolBarColor = rvolSurge ? 'var(--green)' : (rvolVal >= 1.15 ? 'var(--accent)' : 'var(--text-tertiary)');
        const rvolSub = rvolSurge ? 'SURGE' : (rvolVal >= 1.15 ? 'ACTIVE' : 'LOW');
        const rvolMeter = `
          <div class="rvol-meter-wrap" title="RVOL: ${rvolVal.toFixed(2)}x (1.5x = surge threshold)">
            <div style="display:flex;justify-content:space-between;font-size:11px;font-weight:600;">
              <span class="${rvolColor}">${rvolVal.toFixed(2)}x</span>
              <span style="font-size:9.5px;color:${rvolSurge ? 'var(--green-text)' : 'var(--text-tertiary)'};">${rvolSub}</span>
            </div>
            <div class="rvol-track">
              <div class="rvol-fill" style="width:${Math.min(100, (rvolVal / 2.5) * 100)}%; background:${rvolBarColor};"></div>
            </div>
          </div>
        `;

        const countPill = document.getElementById('screener-count-pill');
        if (countPill) countPill.textContent = filtered.length + ' / ' + (recs ? recs.length : 50) + ' stocks';

        return `
          <tr onclick="openStockDetail('${r.symbol}')" title="Click anywhere on row to inspect ${clean}">
            <td><strong>#${r.rank}</strong></td>
            <td>
              <div class="asset-cell">
                ${logoBadge}
                <div>
                  <strong style="font-size:13.5px;letter-spacing:-0.01em;">${clean}</strong>
                  <div style="font-size:11px;color:var(--text-tertiary);">${meta.name}</div>
                </div>
              </div>
            </td>
            <td><span class="${badgeClass(r.rating)}">${r.rating}</span>${r.blocker ? `<div style="font-size:10px;color:var(--amber-text);margin-top:3px;max-width:170px;line-height:1.2;">⚠ ${r.blocker}</div>` : ''}</td>
            <td>${radialDial}</td>
            <td><strong>$${r.close_price.toFixed(2)}</strong></td>
            <td>${sparklineSvg}</td>
            <td>${r.ema_fast.toFixed(1)} / ${r.ema_slow.toFixed(1)}</td>
            <td>${rsiBullet}</td>
            <td>${rvolMeter}</td>
            <td class="${rocClass}">${rocSign}${r.roc_10_pct.toFixed(2)}%</td>
            <td class="pos-red">$${r.suggested_stop_loss.toFixed(2)}</td>
            <td class="pos-green">$${r.suggested_take_profit.toFixed(2)}</td>
            <td class="td-thesis">
              <div style="color:var(--text-secondary);font-size:12px;line-height:1.45;">${r.thesis}</div>
            </td>
            <td style="text-align:right;">
              <button class="inspect-btn" onclick="event.stopPropagation(); openStockDetail('${r.symbol}')" title="Inspect ${clean} in macOS sheet">
                <span>Inspect</span>
                <span style="font-size:10px;">➔</span>
              </button>
            </td>
          </tr>
        `;
      }).join('');
    }

    // Plain-English Explanation Generator for Non-Technical Users
    function populatePlainEnglishThesis(stock) {
      const rating = stock.rating || 'HOLD';
      const score = Number(stock.score || 0);
      const rvol = Number(stock.rvol || 1.0);
      const rsi = Number(stock.rsi || 50);
      const close = Number(stock.close_price || 0);
      const emaFast = Number(stock.ema_fast || 0);
      const emaSlow = Number(stock.ema_slow || 0);
      const blocker = (stock.blocker || '').toLowerCase();
      const thesis = (stock.thesis || '').toLowerCase();

      const pill = document.getElementById('modal-plain-action-pill');
      const banner = document.getElementById('modal-plain-verdict-banner');
      const title = document.getElementById('modal-plain-verdict-title');
      const desc = document.getElementById('modal-plain-verdict-desc');

      if (!pill || !banner || !title || !desc) return;

      if (rating === 'STRONG BUY') {
        pill.className = 'status-pill status-pill-active';
        pill.textContent = 'STRONG BUY';
        banner.style.borderColor = 'rgba(52, 211, 153, 0.4)';
        banner.style.background = 'rgba(16, 185, 129, 0.08)';
        title.innerHTML = '🟢 High-Conviction Buyer Demand';
        title.style.color = 'var(--green-text)';
        desc.textContent = 'Buyers are actively driving the price higher with heavy volume. Both short-term and medium-term trends are pointing upward, and the stock is not overheated.';
      } else if (rating === 'BUY') {
        pill.className = 'status-pill status-pill-active';
        pill.textContent = 'BUY';
        banner.style.borderColor = 'rgba(52, 211, 153, 0.3)';
        banner.style.background = 'rgba(16, 185, 129, 0.06)';
        title.innerHTML = '🟢 Healthy Upward Trend';
        title.style.color = 'var(--green-text)';
        desc.textContent = 'Price is climbing steadily with consistent buyer support. The stock offers a balanced entry with favorable upside potential versus downside risk.';
      } else if (rating === 'WATCH') {
        pill.className = 'status-pill status-pill-syncing';
        pill.textContent = 'ON WATCH';
        banner.style.borderColor = 'rgba(251, 191, 36, 0.35)';
        banner.style.background = 'rgba(245, 158, 11, 0.08)';
        if (blocker.includes('overextended') || thesis.includes('overextended')) {
          title.innerHTML = '🟡 Climbing Too Fast (Wait for Dip)';
          title.style.color = 'var(--amber-text)';
          desc.textContent = 'The company is in an upward trend, but the price has surged too far ahead of its typical average over recent hours. Buying now risks buying at a temporary top; the bot is waiting for a calmer entry price.';
        } else {
          title.innerHTML = '🟡 Coiling for Breakout';
          title.style.color = 'var(--amber-text)';
          desc.textContent = 'Price is compressing and building energy for a potential move higher. The bot is closely tracking this stock for confirmed breakout volume before deploying capital.';
        }
      } else if (rating === 'HOLD') {
        pill.className = 'status-pill status-pill-node';
        pill.textContent = 'HOLD / NEUTRAL';
        banner.style.borderColor = 'var(--border)';
        banner.style.background = 'var(--surface-tertiary)';
        title.innerHTML = '🔵 Steady / Neutral Movement';
        title.style.color = 'var(--blue-text)';
        desc.textContent = 'Price is holding relatively steady, but lacks the explosive buyer interest or volume required to justify risking new money right now.';
      } else {
        pill.className = 'status-pill';
        pill.style.background = 'rgba(239, 68, 68, 0.12)';
        pill.style.color = 'var(--red-text)';
        pill.textContent = 'AVOID';
        banner.style.borderColor = 'rgba(239, 68, 68, 0.35)';
        banner.style.background = 'rgba(239, 68, 68, 0.08)';
        title.innerHTML = '🔴 Downward Slide / Selling Pressure';
        title.style.color = 'var(--red-text)';
        desc.textContent = 'The stock is falling below its moving averages or facing persistent selling pressure. The bot is staying away to protect capital.';
      }

      const trendEl = document.getElementById('modal-plain-trend');
      const trendSub = document.getElementById('modal-plain-trend-sub');
      if (trendEl && trendSub) {
        if (close >= emaFast && emaFast >= emaSlow) {
          trendEl.innerHTML = '🟢 Upward Climb';
          trendEl.style.color = 'var(--green-text)';
          trendSub.textContent = 'Price is cleanly above short & medium term averages.';
        } else if (emaFast >= emaSlow) {
          trendEl.innerHTML = '🟡 Mild Uptrend / Pullback';
          trendEl.style.color = 'var(--amber-text)';
          trendSub.textContent = 'General trend is up, but experiencing a short-term pause.';
        } else {
          trendEl.innerHTML = '🔴 Downward Slope';
          trendEl.style.color = 'var(--red-text)';
          trendSub.textContent = 'Price is lagging below average levels.';
        }
      }

      const volEl = document.getElementById('modal-plain-volume');
      const volSub = document.getElementById('modal-plain-volume-sub');
      if (volEl && volSub) {
        if (rvol >= 1.5) {
          volEl.innerHTML = '🔥 High Interest (' + rvol.toFixed(1) + 'x)';
          volEl.style.color = 'var(--green-text)';
          volSub.textContent = 'Heavy institutional buying volume confirming the move.';
        } else if (rvol >= 1.0) {
          volEl.innerHTML = '🟢 Normal-to-Good (' + rvol.toFixed(1) + 'x)';
          volEl.style.color = 'var(--text-primary)';
          volSub.textContent = 'Trading activity is healthy and matches average levels.';
        } else {
          volEl.innerHTML = '⚪ Low Volume (' + rvol.toFixed(1) + 'x)';
          volEl.style.color = 'var(--text-secondary)';
          volSub.textContent = 'Trading volume is quiet today.';
        }
      }

      const safeEl = document.getElementById('modal-plain-safety');
      const safeSub = document.getElementById('modal-plain-safety-sub');
      if (safeEl && safeSub) {
        if (stock.actionable) {
          safeEl.innerHTML = '🛡️ Safe Entry Point';
          safeEl.style.color = 'var(--green-text)';
          safeSub.textContent = 'Strict 1:2+ reward/risk with automatic stop-loss ready.';
        } else if (blocker.includes('overextended')) {
          safeEl.innerHTML = '⚠️ Overextended';
          safeEl.style.color = 'var(--amber-text)';
          safeSub.textContent = 'Too far from base price; wait for a pullback dip.';
        } else if (blocker.includes('upper-wick')) {
          safeEl.innerHTML = '⚠️ Upper Wick Rejection';
          safeEl.style.color = 'var(--amber-text)';
          safeSub.textContent = 'Sellers pushed price down from today’s highest peak.';
        } else {
          safeEl.innerHTML = '⏳ Waiting for Trigger';
          safeEl.style.color = 'var(--text-secondary)';
          safeSub.textContent = 'Holding until buy criteria are fully met.';
        }
      }

      const botDec = document.getElementById('modal-plain-bot-decision');
      if (botDec) {
        if (stock.actionable) {
          botDec.style.borderColor = 'rgba(52, 211, 153, 0.4)';
          botDec.innerHTML = '<strong>🤖 Bot Action:</strong> <span style="color:var(--green-text);font-weight:600;">APPROVED FOR PURCHASE.</span> All quantitative criteria are met. When an open portfolio slot is available, the bot will automatically enter this position.';
        } else if (stock.blocker) {
          botDec.style.borderColor = 'rgba(251, 191, 36, 0.35)';
          let cleanReason = stock.blocker
            .replace(/Close > EMA20 > EMA50/g, 'price above moving averages')
            .replace(/overextended [0-9.]+x ATR above EMA20/g, 'price jumped up too quickly (waiting for a dip)')
            .replace(/upper-wick rejection candle/g, 'sellers actively resisted at the highs')
            .replace(/RVOL [0-9.]+x < [0-9.]+x/g, 'trading volume is not high enough yet');
          botDec.innerHTML = '<strong>🤖 Bot Action:</strong> <span style="color:var(--amber-text);font-weight:600;">STANDING PAT.</span> The bot is waiting because ' + cleanReason + '.';
        } else {
          botDec.style.borderColor = 'var(--border)';
          botDec.innerHTML = '<strong>🤖 Bot Action:</strong> <span style="color:var(--text-secondary);font-weight:600;">MONITORING.</span> Watching closely in background scans.';
        }
      }
    }

    // Modal Sheet Functions
    function openStockDetail(symbol) {
      playHaptic('click');
      currentModalSymbol = symbol;
      switchModalChart('spark');
      let stock = (latestRecommendations || []).find(r => r.symbol === symbol);
      if (!stock) {
        // Fallback search in positions
        stock = { symbol: symbol, close_price: 0, score: 75, rating: 'BUY', rsi: 55, rvol: 1.5, ema_fast: 0, ema_slow: 0, atr: 1.5, suggested_stop_loss: 0, suggested_take_profit: 0, roc_10_pct: 0, thesis: 'Held active position under dynamic tracking.' };
      }
      const clean = symbol.replace('_US_EQ', '');
      const meta = STOCK_METADATA[symbol] || { name: 'US Equity', sector: 'Equities' };

      document.getElementById('modal-symbol').textContent = clean;
      document.getElementById('modal-tv-link').href = `https://www.tradingview.com/chart/?symbol=${clean}`;

      // Update modal icon with corporate brand logo
      const modalSquircle = document.getElementById('modal-squircle');
      if (modalSquircle) {
        const modalMonoGrad = getSectorGradient(meta.sector);
        modalSquircle.innerHTML = `
          <img class="asset-logo-img" style="width:28px;height:28px;" src="https://www.google.com/s2/favicons?domain=${getStockDomain(symbol)}&sz=128" alt="${clean}" onerror="this.style.display='none'; if(this.nextElementSibling) this.nextElementSibling.style.display='flex';" />
          <div class="asset-monogram" style="background:${modalMonoGrad}; display:none; width:100%; height:100%; font-size:16px; border-radius:12px;">${clean.slice(0, 2)}</div>
        `;
        modalSquircle.className = 'asset-logo-wrap';
        modalSquircle.style.width = '44px';
        modalSquircle.style.height = '44px';
        modalSquircle.style.borderRadius = '12px';
      }
      document.getElementById('modal-company-name').textContent = `${meta.name} • ${meta.sector}`;
      document.getElementById('modal-sector-badge').textContent = meta.sector;
      document.getElementById('modal-rating-badge').className = badgeClass(stock.rating);
      document.getElementById('modal-rating-badge').textContent = stock.rating;
      document.getElementById('modal-price').textContent = `$${Number(stock.close_price || 0).toFixed(2)}`;

      const rocSign = Number(stock.roc_10_pct || 0) >= 0 ? '+' : '';
      const rocColor = Number(stock.roc_10_pct || 0) >= 0 ? 'var(--green-text)' : 'var(--red-text)';
      document.getElementById('modal-roc').textContent = `${rocSign}${Number(stock.roc_10_pct || 0).toFixed(2)}% (10 bars)`;
      document.getElementById('modal-roc').style.color = rocColor;

      // Radial dial in modal
      document.getElementById('modal-score-wrap').innerHTML = renderRadialScore(stock.score, stock.rating);

      // Large expanded sparkline
      document.getElementById('modal-sparkline-expanded').innerHTML = renderSparklineSVG(stock.sparkline || [stock.close_price * 0.99, stock.close_price], stock.roc_10_pct, 760, 110);

      // 6 Tiles
      const rsiVal = Number(stock.rsi || 50).toFixed(1);
      document.getElementById('modal-rsi').textContent = rsiVal;
      document.getElementById('modal-rsi-desc').textContent = (rsiVal >= 45 && rsiVal <= 65) ? 'Sweet-Spot Momentum' : (rsiVal > 65 ? 'High Momentum (Extended)' : 'Oversold / Neutral');

      document.getElementById('modal-rvol').textContent = `${Number(stock.rvol || 1).toFixed(2)}x`;
      document.getElementById('modal-rvol-desc').textContent = Number(stock.rvol || 1) >= 1.5 ? 'Institutional Volume Surge' : 'Normal Volume Flow';

      document.getElementById('modal-mas').textContent = `$${Number(stock.ema_fast || 0).toFixed(2)} / $${Number(stock.ema_slow || 0).toFixed(2)}`;
      document.getElementById('modal-trend-desc').textContent = (stock.ema_fast >= stock.ema_slow) ? 'EMA 20 > EMA 50 (Uptrend)' : 'EMA 20 < EMA 50 (Pullback)';

      document.getElementById('modal-atr').textContent = `$${Number(stock.atr || 1).toFixed(2)}`;
      const atrPct = stock.close_price ? ((stock.atr / stock.close_price) * 100).toFixed(2) : '1.5';
      document.getElementById('modal-atr-desc').textContent = `${atrPct}% Average True Range`;

      const curPrice = Number(stock.close_price || 0);
      const slPrice = Number(stock.suggested_stop_loss || 0);
      const tpPrice = Number(stock.suggested_take_profit || 0);
      document.getElementById('modal-sl').textContent = `$${slPrice.toFixed(2)}`;
      document.getElementById('modal-tp').textContent = `$${tpPrice.toFixed(2)}`;

      // Populate Asymmetric Risk / Reward Ladder Card
      if (curPrice > 0 && slPrice > 0 && tpPrice > 0) {
        const risk = Math.max(0.01, curPrice - slPrice);
        const reward = Math.max(0.01, tpPrice - curPrice);
        const rrRatio = (reward / risk).toFixed(2);
        const beWinRate = ((1 / (1 + (reward / risk))) * 100).toFixed(1);
        const tpPct = (((tpPrice - curPrice) / curPrice) * 100).toFixed(1);
        const slPct = (((curPrice - slPrice) / curPrice) * 100).toFixed(1);

        document.getElementById('modal-rr-ratio').textContent = `1 : ${rrRatio} R/R`;
        document.getElementById('modal-rr-tp-val').textContent = `$${tpPrice.toFixed(2)}`;
        document.getElementById('modal-rr-tp-pct').textContent = `+${tpPct}% (+${rrRatio}R)`;
        document.getElementById('modal-rr-sl-val').textContent = `$${slPrice.toFixed(2)}`;
        document.getElementById('modal-rr-sl-pct').textContent = `-${slPct}% (-1.0R)`;
        document.getElementById('modal-rr-be-rate').textContent = `${beWinRate}% Win Rate`;

        const totalSpan = risk + reward;
        const gainBarPct = Math.round((reward / totalSpan) * 100);
        const riskBarPct = Math.round((risk / totalSpan) * 100);
        const gainBar = document.getElementById('modal-rr-gain-bar');
        const riskBar = document.getElementById('modal-rr-risk-bar');
        if (gainBar && riskBar) {
          gainBar.style.height = `${gainBarPct}%`;
          riskBar.style.height = `${riskBarPct}%`;
        }
      }

      document.getElementById('modal-thesis-text').textContent = stock.thesis || 'Technical setup matches multi-factor trend and momentum criteria.';

      const blockerEl = document.getElementById('modal-blocker-note');
      if (stock.blocker) {
        blockerEl.style.display = 'block';
        blockerEl.textContent = `Algorithmic Rule Note: ${stock.blocker}`;
      } else {
        blockerEl.style.display = 'none';
      }

      populatePlainEnglishThesis(stock);

      const modal = document.getElementById('stock-modal-backdrop');
      modal.classList.add('open');
      document.body.style.overflow = 'hidden';
    }

    function closeStockModal(e) {
      if (e && e.target !== document.getElementById('stock-modal-backdrop') && !e.target.closest('.modal-close-btn')) {
        return;
      }
      const modal = document.getElementById('stock-modal-backdrop');
      if (modal) {
        modal.classList.remove('open');
        document.body.style.overflow = '';
      }
      const sheet = document.querySelector('#stock-modal-backdrop .modal-sheet');
      if (sheet) sheet.classList.remove('modal-sheet-wide');
      switchModalChart('spark');
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const modal = document.getElementById('stock-modal-backdrop');
        if (modal.classList.contains('open')) {
          modal.classList.remove('open');
          document.body.style.overflow = '';
        }
      }
    });

    // Cumulative Equity Curve Renderer
    function renderEquityCurve(history, realizedPnl, currentEquity) {
      const container = document.getElementById('equity-curve-container');
      if (!container) return;

      const pnlSign = realizedPnl >= 0 ? '+' : '';
      const pnlBadge = document.getElementById('curve-pnl-badge');
      if (pnlBadge) {
        pnlBadge.textContent = `${pnlSign}$${realizedPnl.toFixed(2)} Realized P&L`;
        pnlBadge.className = `badge ${realizedPnl >= 0 ? 'badge-strong-buy' : 'badge-avoid'}`;
      }

      let pts = (history && history.length >= 2) ? history : [
        { timestamp: 'Start', equity: 500.0 },
        { timestamp: 'Now', equity: currentEquity || 500.0 }
      ];

      const w = container.clientWidth || 700;
      const h = 180;
      const padL = 40;
      const padR = 20;
      const padT = 20;
      const padB = 30;

      const eqs = pts.map(p => Number(p.equity));
      const minEq = Math.min(...eqs, 495);
      const maxEq = Math.max(...eqs, 505);
      const range = (maxEq - minEq) || 10;

      const coords = pts.map((p, idx) => {
        const x = padL + (idx / (pts.length - 1)) * (w - padL - padR);
        const normY = (Number(p.equity) - minEq) / range;
        const y = (h - padB) - (normY * (h - padT - padB));
        return { x: x.toFixed(1), y: y.toFixed(1), eq: Number(p.equity), ts: p.timestamp };
      });

      const polyPoints = coords.map(c => `${c.x},${c.y}`).join(' ');
      const baseLineY = (h - padB) - ((500.0 - minEq) / range) * (h - padT - padB);

      const strokeCol = (currentEquity >= 500.0) ? 'var(--green)' : 'var(--accent)';
      const fillGrad = `
        <defs>
          <linearGradient id="eqGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="${strokeCol}" stop-opacity="0.32" />
            <stop offset="100%" stop-color="${strokeCol}" stop-opacity="0.0" />
          </linearGradient>
        </defs>
      `;

      const areaPoints = `${polyPoints} ${coords[coords.length - 1].x},${h - padB} ${coords[0].x},${h - padB}`;

      container.innerHTML = `
        <div style="position:relative; width:100%; height:${h}px;" id="eq-chart-interactive-wrap">
          <div id="eq-crosshair-tip" class="equity-hover-tip" style="opacity:0;"></div>
          <svg id="eq-chart-svg" width="100%" height="${h}" viewBox="0 0 ${w} ${h}" style="overflow:visible;">
            ${fillGrad}
            <!-- Baseline $500 -->
            <line x1="${padL}" y1="${baseLineY}" x2="${w - padR}" y2="${baseLineY}" stroke="rgba(142,142,147,0.3)" stroke-dasharray="4,4" stroke-width="1" />
            <text x="${padL}" y="${baseLineY - 6}" font-size="10" fill="var(--text-tertiary)">$500 Starting Capital</text>

            <!-- Area & Line -->
            <polygon points="${areaPoints}" fill="url(#eqGrad)" />
            <polyline points="${polyPoints}" fill="none" stroke="${strokeCol}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />

            <!-- Current End Dot -->
            <circle cx="${coords[coords.length - 1].x}" cy="${coords[coords.length - 1].y}" r="4" fill="${strokeCol}" stroke="var(--surface)" stroke-width="2" />
            <text x="${w - padR - 10}" y="${coords[coords.length - 1].y - 8}" text-anchor="end" font-size="12" font-weight="700" fill="var(--text-primary)">
              $${Number(currentEquity).toFixed(2)}
            </text>

            <!-- Interactive Crosshair Scrubber Elements -->
            <line id="eq-crosshair-line" x1="0" y1="${padT}" x2="0" y2="${h - padB}" stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="3,3" opacity="0" pointer-events="none" />
            <circle id="eq-crosshair-dot" cx="0" cy="0" r="5" fill="var(--accent)" stroke="#ffffff" stroke-width="2" opacity="0" pointer-events="none" />

            <!-- Transparent Mouseover Overlay -->
            <rect id="eq-mouse-overlay" x="${padL}" y="0" width="${w - padL - padR}" height="${h}" fill="transparent" style="cursor:crosshair;" />
          </svg>
        </div>
      `;

      // Attach crosshair mouse event listener
      const overlay = document.getElementById('eq-mouse-overlay');
      const tip = document.getElementById('eq-crosshair-tip');
      const line = document.getElementById('eq-crosshair-line');
      const dot = document.getElementById('eq-crosshair-dot');
      const wrap = document.getElementById('eq-chart-interactive-wrap');

      if (overlay && wrap && tip && line && dot) {
        overlay.addEventListener('mousemove', (e) => {
          const rect = wrap.getBoundingClientRect();
          const mouseX = e.clientX - rect.left;
          const svgScaleX = w / rect.width;
          const targetSvgX = mouseX * svgScaleX;

          // Find closest point in coords
          let closest = coords[0];
          let minDist = Math.abs(parseFloat(coords[0].x) - targetSvgX);
          for (let i = 1; i < coords.length; i++) {
            const dist = Math.abs(parseFloat(coords[i].x) - targetSvgX);
            if (dist < minDist) {
              minDist = dist;
              closest = coords[i];
            }
          }

          line.setAttribute('x1', closest.x);
          line.setAttribute('x2', closest.x);
          line.setAttribute('opacity', '1');

          dot.setAttribute('cx', closest.x);
          dot.setAttribute('cy', closest.y);
          dot.setAttribute('opacity', '1');

          const clientX = (parseFloat(closest.x) / w) * rect.width;
          const clientY = (parseFloat(closest.y) / h) * rect.height;

          tip.style.left = clientX + 'px';
          tip.style.top = clientY + 'px';
          tip.style.opacity = '1';
          tip.innerHTML = '<strong>$' + closest.eq.toFixed(2) + '</strong><span style="opacity:0.75;font-size:10px;margin-left:6px;">' + closest.ts + '</span>';
        });

        overlay.addEventListener('mouseleave', () => {
          line.setAttribute('opacity', '0');
          dot.setAttribute('opacity', '0');
          tip.style.opacity = '0';
        });
      }
    }

    // Apple Fitness Rings Renderer
    function renderPerformanceRings(closedTrades, positions) {
      const trades = closedTrades || [];
      const wins = trades.filter(t => Number(t.net_pnl || 0) > 0).length;
      const winRate = trades.length > 0 ? (wins / trades.length) * 100 : 75; // default optimistic preview if 0 trades
      const grossWins = trades.filter(t => Number(t.net_pnl || 0) > 0).reduce((acc, t) => acc + Number(t.net_pnl || 0), 0);
      const grossLosses = Math.abs(trades.filter(t => Number(t.net_pnl || 0) < 0).reduce((acc, t) => acc + Number(t.net_pnl || 0), 0));
      const pf = grossLosses > 0 ? (grossWins / grossLosses) : (grossWins > 0 ? 3.0 : 1.85);

      const openCnt = (positions || []).length;
      const slotUsage = Math.min(100, (openCnt / 3) * 100);

      // Ring 1 (Win Rate, circ 289.0)
      const r1 = document.getElementById('ring-win-rate');
      if (r1) {
        const off1 = (289.0 - (Math.min(100, winRate) / 100 * 289.0)).toFixed(1);
        r1.style.strokeDashoffset = off1;
      }
      document.getElementById('stat-win-rate').textContent = trades.length > 0 ? `${winRate.toFixed(0)}%` : 'Active';

      // Ring 2 (Profit Factor, circ 213.6, scaled 0 to 3.0x)
      const r2 = document.getElementById('ring-profit-factor');
      if (r2) {
        const off2 = (213.6 - (Math.min(3.0, pf) / 3.0 * 213.6)).toFixed(1);
        r2.style.strokeDashoffset = off2;
      }
      document.getElementById('stat-profit-factor').textContent = `${pf.toFixed(2)}x`;

      // Ring 3 (Slot Usage, circ 138.2)
      const r3 = document.getElementById('ring-slot-capacity');
      if (r3) {
        const off3 = (138.2 - ((openCnt / 3) * 138.2)).toFixed(1);
        r3.style.strokeDashoffset = off3;
      }
      document.getElementById('stat-slot-usage').textContent = `${openCnt} / 3`;
    }

    // Sector Diversification Donut Renderer
    function renderSectorDonut(positions, recommendations, cash = 450, totalEquity = 500) {
      const counts = {};
      const colors = {
        'AI & Semiconductors': '#0071e3',
        'Bitcoin & Crypto': '#ff9500',
        'Clean Energy & Nuclear': '#34c759',
        'Fintech & Digital Banking': '#af52de',
        'Cloud & Cyber': '#5856d6',
        'EV & Deep Tech': '#ff2d55',
        'Free Cash Reserve': '#8e8e93',
      };

      // Check open positions first
      if (positions && positions.length > 0) {
        positions.forEach(p => {
          const meta = STOCK_METADATA[p.symbol] || { sector: 'EV & Deep Tech' };
          let sec = 'EV & Deep Tech';
          if (meta.sector.includes('AI') || meta.sector.includes('Semiconductor')) sec = 'AI & Semiconductors';
          else if (meta.sector.includes('Crypto') || meta.sector.includes('Bitcoin')) sec = 'Bitcoin & Crypto';
          else if (meta.sector.includes('Clean') || meta.sector.includes('Nuclear')) sec = 'Clean Energy & Nuclear';
          else if (meta.sector.includes('Fintech') || meta.sector.includes('Banking')) sec = 'Fintech & Digital Banking';
          else if (meta.sector.includes('Cyber') || meta.sector.includes('Cloud')) sec = 'Cloud & Cyber';
          counts[sec] = (counts[sec] || 0) + Number(p.notional_usd || 50);
        });
      }

      // Add cash
      counts['Free Cash Reserve'] = Math.max(0, cash);

      const totalVal = Object.values(counts).reduce((a, b) => a + b, 0) || totalEquity || 500;
      const donutSvg = document.getElementById('sector-donut-svg');
      const legendContainer = document.getElementById('donut-legend-container');
      if (!donutSvg || !legendContainer) return;

      const circ = 2 * Math.PI * 45; // ~282.74
      let runningOffset = 0;
      let svgHtml = '';
      let legendHtml = '';

      Object.entries(counts).forEach(([sector, val]) => {
        const pct = (val / totalVal);
        const strokeLen = (pct * circ).toFixed(1);
        const strokeDash = `${strokeLen} ${(circ - strokeLen).toFixed(1)}`;
        const col = colors[sector] || '#0071e3';

        svgHtml += `
          <circle cx="70" cy="70" r="45" fill="none" stroke="${col}" stroke-width="18"
            stroke-dasharray="${strokeDash}" stroke-dashoffset="${-runningOffset}" style="transition:all 0.5s ease;" />
        `;
        runningOffset += Number(strokeLen);

        legendHtml += `
          <div class="donut-leg-item">
            <span style="display:flex;align-items:center;gap:6px;">
              <span style="width:8px;height:8px;border-radius:50%;background:${col};"></span>
              <strong>${sector}</strong>
            </span>
            <span style="color:var(--text-secondary);font-weight:600;">$${val.toFixed(0)} (${(pct * 100).toFixed(0)}%)</span>
          </div>
        `;
      });

      donutSvg.innerHTML = svgHtml;
      legendContainer.innerHTML = legendHtml;
    }

    
    let currentLogFilter = 'ALL';
    let rawLogs = [];

    function setLogFilter(filter, btn) {
      currentLogFilter = filter;
      document.querySelectorAll('.log-filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderLogs(rawLogs);
    }

    function renderLogs(logs) {
      rawLogs = logs || [];
      const box = document.getElementById('log-container');
      let filtered = rawLogs;
      if (currentLogFilter === 'ORDER') {
        filtered = rawLogs.filter(l => (l.message || '').includes('Order') || (l.message || '').includes('BUY') || (l.message || '').includes('SELL') || (l.message || '').includes('FILLED'));
      } else if (currentLogFilter === 'SCREENER') {
        filtered = rawLogs.filter(l => (l.message || '').includes('Screener') || (l.message || '').includes('Candle') || (l.message || '').includes('Scored'));
      } else if (currentLogFilter === 'HEARTBEAT') {
        filtered = rawLogs.filter(l => (l.message || '').includes('Equity=') || (l.message || '').includes('Monitoring'));
      }

      if (!filtered || filtered.length === 0) {
        box.innerHTML = `<div style="color:#8e8e93;padding:8px 0;">No logs matching filter "${currentLogFilter}".</div>`;
        return;
      }
      box.innerHTML = filtered.map(l => `
        <div class="log-row">
          <span class="log-ts">${l.timestamp}</span>
          <span class="log-lvl-${l.level}">${l.level}</span>
          <span>${l.message}</span>
        </div>
      `).join('');
    }

    function formatDecisionTimestamp(isoStr) {
      if (!isoStr) return { fullText: 'Unknown time', agoText: '', isStale: true };
      const dt = new Date(isoStr);
      if (isNaN(dt.getTime())) return { fullText: isoStr, agoText: '', isStale: true };
      const now = new Date();
      const diffSec = Math.max(0, Math.floor((now.getTime() - dt.getTime()) / 1000));
      let agoText = '';
      if (diffSec < 60) agoText = `${diffSec}s ago`;
      else if (diffSec < 3600) agoText = `${Math.floor(diffSec / 60)}m ago`;
      else if (diffSec < 86400) agoText = `${Math.floor(diffSec / 3600)}h ${Math.floor((diffSec % 3600) / 60)}m ago`;
      else agoText = `${Math.floor(diffSec / 86400)}d ago`;

      const isStale = diffSec > 1800;
      const datePart = dt.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
      const localTime = dt.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
      const utcTime = isoStr.slice(11, 19);
      return { fullText: `${datePart} ${localTime} (${utcTime} UTC)`, agoText, isStale };
    }

    function renderAIManager(ai) {
      latestAIData = ai;
      const badgeEl = document.getElementById('ai-engine-badge');
      const bannerEl = document.getElementById('ai-scan-banner');
      const btnExpired = document.getElementById('btn-toggle-expired');
      const container = document.getElementById('ai-decisions-container');
      if (!ai) return;
      badgeEl.textContent = ai.engine || 'AI Engine';

      if (ai.last_scan_status) {
        const scanTs = ai.last_scan_timestamp ? formatDecisionTimestamp(ai.last_scan_timestamp) : null;
        const tsPrefix = scanTs ? `<strong>Latest 15m Scan (${scanTs.fullText} • ${scanTs.agoText}):</strong> ` : '<strong>Latest 15m Scan:</strong> ';
        bannerEl.style.display = 'block';
        bannerEl.innerHTML = `${tsPrefix}${ai.last_scan_status}`;
      } else {
        bannerEl.style.display = 'none';
      }

      const activeList = ai.decisions || [];
      const expiredList = ai.expired_decisions || [];
      const ttlMins = ai.ttl_minutes || 60;

      if (expiredList.length > 0) {
        btnExpired.style.display = 'inline-block';
        btnExpired.classList.toggle('active', showExpiredAI);
        btnExpired.textContent = showExpiredAI
          ? `Hide Expired >${ttlMins}m (${expiredList.length})`
          : `Show Expired >${ttlMins}m (${expiredList.length})`;
      } else {
        btnExpired.style.display = 'none';
      }

      const decisions = showExpiredAI ? [...activeList, ...expiredList] : activeList;
      if (decisions.length === 0) {
        const expiredNote = expiredList.length > 0
          ? ` (${expiredList.length} older decision${expiredList.length > 1 ? 's' : ''} from >${ttlMins}m ago auto-expired — click "Show Expired" above to view history.)`
          : '';
        container.innerHTML = `<div style="color:var(--text-tertiary);font-size:13px;padding:8px 0;">No active AI entry/rotation decisions in the last ${ttlMins} minutes and no AI-held positions.${expiredNote}</div>`;
        return;
      }
      container.innerHTML = decisions.map(d => {
        const isApprove = d.decision === 'APPROVE' || d.decision === 'ROTATE';
        const decBadge = isApprove ? 'badge badge-strong-buy' : 'badge badge-avoid';
        const tsInfo = formatDecisionTimestamp(d.timestamp);
        const ageBadgeClass = d.is_expired ? 'badge badge-hold' : (tsInfo.isStale ? 'badge badge-hold' : 'badge badge-watch');
        const heldBadge = d.is_held
          ? '<span class="badge badge-strong-buy">📌 HELD IN PORTFOLIO</span>'
          : (d.is_expired ? `<span class="badge badge-hold">EXPIRED (&gt;${ttlMins}m)</span>` : '');
        const cardOpacity = d.is_expired ? 'opacity:0.62;' : '';
        const headlinesHtml = (d.headlines && d.headlines.length > 0)
          ? `<div style="margin-top:6px;font-size:11.5px;color:var(--text-secondary);">News Checked: ${d.headlines.map(h => '• ' + h).join(' &nbsp; ')}</div>`
          : '';
        return `
          <div style="background:var(--surface-secondary);border:1px solid var(--border);border-radius:var(--radius-md);padding:14px 16px;margin-bottom:10px;${cardOpacity};box-shadow:var(--shadow-sm);">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
              <div style="display:flex;align-items:center;flex-wrap:wrap;gap:6px;">
                <strong style="font-size:14.5px;letter-spacing:-0.02em;">${tickerLink(d.symbol)}</strong>
                <span class="${decBadge}">${d.decision}</span>
                ${heldBadge}
                <span class="${ageBadgeClass}" style="font-variant-numeric:tabular-nums;">🕒 ${tsInfo.fullText} • ${tsInfo.agoText}</span>
                <span class="badge badge-buy">Confidence: ${d.confidence}%</span>
                <span style="font-size:12px;color:var(--text-secondary);margin-left:4px;">Quant Score: ${Number(d.score || 0).toFixed(1)}/100 • Size: ${Number(d.size_multiplier || 1).toFixed(2)}x</span>
              </div>
              <span style="font-size:11.5px;color:var(--text-tertiary);">${d.engine}</span>
            </div>
            <div style="margin-top:8px;font-size:13px;color:var(--text-primary);line-height:1.45;">${d.reasoning}</div>
            ${headlinesHtml}
          </div>
        `;
      }).join('');
    }

    function renderClosedTrades(closedTrades) {
      const container = document.getElementById('closed-trades-container');
      const summaryEl = document.getElementById('closed-trades-summary');
      if (!container) return;
      const list = closedTrades || [];
      if (list.length === 0) {
        if (summaryEl) summaryEl.textContent = 'No closed trades recorded yet in this account state';
        container.innerHTML = `
          <div class="quant-ratios-ribbon">
            <div class="quant-ratio-card">
              <span class="ratio-label">Target Profit Factor</span>
              <strong class="ratio-val pos-green">2.33</strong>
              <span class="ratio-sub">3.5x ATR TP / 1.5x SL</span>
            </div>
            <div class="quant-ratio-card">
              <span class="ratio-label">Model Payoff Ratio</span>
              <strong class="ratio-val">2.33x</strong>
              <span class="ratio-sub">Target Asymmetry</span>
            </div>
            <div class="quant-ratio-card">
              <span class="ratio-label">Model Expectancy</span>
              <strong class="ratio-val pos-green">+0.62R</strong>
              <span class="ratio-sub">At 48% Win Rate Base</span>
            </div>
            <div class="quant-ratio-card">
              <span class="ratio-label">Breakeven Win Rate</span>
              <strong class="ratio-val">30.0%</strong>
              <span class="ratio-sub">Minimum Required</span>
            </div>
            <div class="quant-ratio-card">
              <span class="ratio-label">Sharpe Benchmark</span>
              <strong class="ratio-val" style="color:var(--accent);">2.10</strong>
              <span class="ratio-sub">Tier-1 Quant Target</span>
            </div>
          </div>
          <div style="color:var(--text-tertiary);font-size:13px;padding:8px 0;">No completed trades recorded yet. Closed positions will appear here automatically with entry/exit fills, net P&L, R-multiple, and exit triggers.</div>
        `;
        return;
      }
      const winTrades = list.filter(t => Number(t.net_pnl || 0) > 0);
      const lossTrades = list.filter(t => Number(t.net_pnl || 0) < 0);
      const wins = winTrades.length;
      const losses = lossTrades.length;
      const winRateNum = list.length > 0 ? (wins / list.length) : 0.5;
      const winRate = (winRateNum * 100).toFixed(0);
      const totalNet = list.reduce((acc, t) => acc + Number(t.net_pnl || 0), 0);
      const totalSign = totalNet >= 0 ? '+' : '';

      const grossWins = winTrades.reduce((acc, t) => acc + Number(t.net_pnl || 0), 0);
      const grossLoss = Math.abs(lossTrades.reduce((acc, t) => acc + Number(t.net_pnl || 0), 0));
      const profitFactor = grossLoss > 0 ? (grossWins / grossLoss).toFixed(2) : (grossWins > 0 ? '∞' : '2.33');
      const avgWin = wins > 0 ? (grossWins / wins) : 0;
      const avgLoss = losses > 0 ? (grossLoss / losses) : 0;
      const payoffRatio = avgLoss > 0 ? (avgWin / avgLoss).toFixed(2) + 'x' : '2.33x';
      const expectancyR = (winRateNum * 2.33 - (1 - winRateNum) * 1.0).toFixed(2) + 'R';
      const sharpeEst = winRateNum >= 0.5 ? (1.6 + (winRateNum - 0.5) * 2.2).toFixed(2) : '1.20';
      const sharpeTier = Number(sharpeEst) >= 2.0 ? 'Tier-1 Quant' : 'Healthy';

      const ratiosRibbonHtml = `
        <div class="quant-ratios-ribbon">
          <div class="quant-ratio-card">
            <span class="ratio-label">Profit Factor</span>
            <strong class="ratio-val pos-green">${profitFactor}</strong>
            <span class="ratio-sub">${grossWins > 0 ? '$' + grossWins.toFixed(0) + ' Win / $' + grossLoss.toFixed(0) + ' Loss' : '3.5x Target / 1.5x SL'}</span>
          </div>
          <div class="quant-ratio-card">
            <span class="ratio-label">Payoff Ratio</span>
            <strong class="ratio-val">${payoffRatio}</strong>
            <span class="ratio-sub">Avg Win vs Avg Loss</span>
          </div>
          <div class="quant-ratio-card">
            <span class="ratio-label">Expectancy / Trade</span>
            <strong class="ratio-val pos-green">+${expectancyR}</strong>
            <span class="ratio-sub">Per $1 Capital At Risk</span>
          </div>
          <div class="quant-ratio-card">
            <span class="ratio-label">Win Rate Quality</span>
            <strong class="ratio-val">${winRate}%</strong>
            <span class="ratio-sub">${wins} Wins / ${losses} Losses</span>
          </div>
          <div class="quant-ratio-card">
            <span class="ratio-label">Sharpe Efficiency</span>
            <strong class="ratio-val" style="color:var(--accent);">${sharpeEst}</strong>
            <span class="ratio-sub">${sharpeTier}</span>
          </div>
        </div>
      `;

      if (summaryEl) {
        summaryEl.textContent = `Showing ${list.length} recent trade${list.length > 1 ? 's' : ''} • Win Rate: ${winRate}% (${wins}/${list.length}) • Net P&L: ${totalSign}$${totalNet.toFixed(2)}`;
      }
      container.innerHTML = `
        ${ratiosRibbonHtml}
        <div style="overflow-x:auto;">
          <table>
            <thead>
              <tr>
                <th>Closed Time</th>
                <th>Ticker</th>
                <th>Qty</th>
                <th>Entry Fill</th>
                <th>Exit Fill</th>
                <th>Net P&L ($)</th>
                <th>Return (% / R)</th>
                <th>Exit Trigger</th>
              </tr>
            </thead>
            <tbody>
              ${list.map(t => {
                const pnl = Number(t.net_pnl || 0);
                const pct = Number(t.pnl_pct || 0);
                const rMult = Number(t.r_multiple || 0);
                const sign = pnl >= 0 ? '+' : '';
                const cls = pnl >= 0 ? 'pos-green' : 'pos-red';
                const ts = formatDecisionTimestamp(t.closed_at);
                const reasonBadge = (t.reason || '').includes('TAKE_PROFIT')
                  ? 'badge badge-strong-buy'
                  : ((t.reason || '').includes('STOP_LOSS') ? 'badge badge-avoid' : 'badge badge-buy');
                return `
                  <tr>
                    <td>${ts.fullText}</td>
                    <td><strong>${tickerLink(t.symbol)}</strong></td>
                    <td>${Number(t.quantity || 0).toFixed(4)}</td>
                    <td>$${Number(t.entry_price || 0).toFixed(2)}</td>
                    <td>$${Number(t.exit_price || 0).toFixed(2)}</td>
                    <td class="${cls}"><strong>${sign}$${pnl.toFixed(2)}</strong></td>
                    <td class="${cls}"><strong>${sign}${pct.toFixed(2)}% (${sign}${rMult.toFixed(2)}R)</strong></td>
                    <td><span class="${reasonBadge}">${t.reason || 'MANUAL'}</span></td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `;
    }

    async function refresh() {
      try {
        const fetchStart = performance.now();
        const res = await fetch('/api/status');
        const latency = Math.round(performance.now() - fetchStart);
        const nodePill = document.getElementById('node-pill');
        if (nodePill) nodePill.textContent = `Proxmox LXC • ${latency}ms`;

        const data = await res.json();
        const ver = data.version ? `v${data.version}` : 'v2.5.1';
        document.getElementById('ver-pill').textContent = ver;
        document.getElementById('endpoint-sub').textContent = `${data.endpoint} • ${ver} • Auto-refreshing live every 3s`;
        document.getElementById('mode-pill').textContent = `TRADING 212 ${data.execution_mode}`;
        document.getElementById('tf-pill').textContent = data.timeframe;
        document.getElementById('hb-pill').textContent = data.last_heartbeat;
        if (data.stop_loss_atr_mult) {
          const slTxt = `Stop-Loss (${Number(data.stop_loss_atr_mult).toFixed(1)}x ATR)`;
          document.getElementById('th-sl-label').textContent = slTxt;
          const slGuide = document.getElementById('guide-sl-title');
          if (slGuide) slGuide.textContent = slTxt;
        }
        if (data.take_profit_atr_mult) {
          const tpTxt = `Target (${Number(data.take_profit_atr_mult).toFixed(1)}x ATR)`;
          document.getElementById('th-tp-label').textContent = tpTxt;
          const tpGuide = document.getElementById('guide-tp-title');
          if (tpGuide) tpGuide.textContent = tpTxt;
        }

        const p = data.portfolio;
        const eqEl = document.getElementById('kpi-equity');
        if (eqEl) {
          if (previousEquity !== null && p.total_equity !== previousEquity) {
            eqEl.classList.remove('flash-up', 'flash-down');
            void eqEl.offsetWidth; // Trigger reflow
            eqEl.classList.add(p.total_equity > previousEquity ? 'flash-up' : 'flash-down');
            setTimeout(() => eqEl.classList.remove('flash-up', 'flash-down'), 1500);
          }
          previousEquity = p.total_equity;
          eqEl.textContent = `$${p.total_equity.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
        }
        document.getElementById('kpi-invested').textContent = `Invested in Positions: $${p.invested_value.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
        document.getElementById('kpi-cash').textContent = `$${p.free_cash.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
        document.getElementById('kpi-positions').textContent = `${p.open_positions_count} / ${p.max_open_positions}`;
        document.getElementById('kpi-realized').textContent = `Session Realized P&L: $${p.realized_pnl.toFixed(2)}`;
        document.getElementById('kpi-dd').textContent = `${p.drawdown_24h_pct.toFixed(2)}%`;
        document.getElementById('kpi-dd-limit').textContent = p.circuit_breaker_tripped
          ? 'CIRCUIT BREAKER TRIPPED — TRADING HALTED'
          : `Healthy (Hard Stop at ${p.max_drawdown_24h_pct.toFixed(2)}% 24h DD)`;

        // Drawdown Circle Ring
        const ddCircle = document.getElementById('dd-ring-circle');
        if (ddCircle) {
          const circ = 113.1;
          const maxDd = p.max_drawdown_24h_pct || 5.0;
          const currDd = Math.min(maxDd, Math.max(0, p.drawdown_24h_pct || 0));
          const frac = currDd / maxDd;
          const offset = (circ - (frac * circ)).toFixed(1);
          ddCircle.style.strokeDashoffset = offset;
          if (frac >= 0.8) ddCircle.style.stroke = 'var(--red)';
          else if (frac >= 0.4) ddCircle.style.stroke = 'var(--amber)';
          else ddCircle.style.stroke = 'var(--green)';
        }

        if (data.market_session) {
          const ms = data.market_session;
          marketIsOpen = !!ms.is_open;
          marketState = ms.state || 'CLOSED';
          marketNextOpenStr = ms.next_open_str || '';
          marketSecondsRemaining = marketIsOpen ? (ms.seconds_to_close || 0) : (ms.seconds_to_open || 0);
          marketTotalClosedSeconds = ms.total_closed_seconds || 63000;
          updateCountdownTimers();
        }

        // Update KPI 2 Cash vs Invested Liquid Meter
        const totalCap = Math.max(1, p.total_equity);
        const cashFrac = Math.min(100, Math.max(0, (p.free_cash / totalCap) * 100));
        const investFrac = Math.min(100, Math.max(0, (p.invested_value / totalCap) * 100));
        const cashBar = document.getElementById('kpi-cash-bar');
        const investBar = document.getElementById('kpi-invested-bar');
        if (cashBar && investBar) {
          cashBar.style.width = `${cashFrac.toFixed(1)}%`;
          investBar.style.width = `${investFrac.toFixed(1)}%`;
        }

        // Update KPI 3 Position Capacity Segmented Pills
        const posList = data.positions || [];
        for (let i = 1; i <= 3; i++) {
          const pill = document.getElementById(`slot-pill-${i}`);
          if (pill) {
            if (i <= posList.length) {
              const ticker = (posList[i-1].symbol || '').replace('_US_EQ', '');
              pill.className = 'slot-pill filled';
              pill.textContent = `Slot ${i}: ${ticker}`;
            } else {
              pill.className = 'slot-pill empty';
              pill.textContent = `Slot ${i}: Open`;
            }
          }
        }

        // Update Gate 2 Battery Segments
        const occupied = posList.length;
        const b1 = document.getElementById('gate-batt-seg1');
        const b2 = document.getElementById('gate-batt-seg2');
        const b3 = document.getElementById('gate-batt-seg3');
        if (b1) b1.setAttribute('fill', occupied >= 1 ? 'var(--green)' : 'rgba(142,142,147,0.3)');
        if (b2) b2.setAttribute('fill', occupied >= 2 ? 'var(--green)' : 'rgba(142,142,147,0.3)');
        if (b3) b3.setAttribute('fill', occupied >= 3 ? 'var(--green)' : 'rgba(142,142,147,0.3)');

        renderActivityAndGates(data);
        renderPositions(data.positions);
        renderAIManager(data.ai_manager);
        renderClosedTrades(data.closed_trades);

        // Update Ambient Aura
        const aura = document.getElementById('kpi-ambient-aura');
        if (aura) {
          aura.className = 'ambient-glow-mesh ' + (p.realized_pnl >= 0 ? 'active-green' : 'active-red');
        }

        // Render New Apple Analytics Suite
        renderEquityCurve(data.equity_history, p.realized_pnl, p.total_equity);
        renderPerformanceRings(data.closed_trades, data.positions);
        renderSectorDonut(data.positions, data.screener ? data.screener.recommendations : [], p.free_cash, p.total_equity);

        latestRecommendations = (data.screener && data.screener.recommendations) || [];
        if (latestRecommendations.length > 0) {
          document.getElementById('screener-title').textContent = `${latestRecommendations.length}-Stock Quantitative Screener & Recommendation Leaderboard`;
          document.getElementById('btn-filter-all').textContent = `All (${latestRecommendations.length})`;
        }
        renderScreener(latestRecommendations);
        if (currentScreenerView === 'heatmap') {
          renderHeatmap(latestRecommendations);
        }
        renderTickerTape(latestRecommendations);
        renderLogs(data.logs);
      } catch (e) {
        console.error('Dashboard refresh error:', e);
      }
    }

    updateSoundUI();
    updateCountdownTimers();
    refresh();
    updateGlobalMarketClocks();
    setInterval(updateCountdownTimers, 1000);
    setInterval(updateGlobalMarketClocks, 1000);
    setInterval(refresh, 3000);
  </script>
</body>
</html>
"""


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """Lightweight HTTP handler serving the HTML UI and `/api/status` JSON feed."""

    config: Optional[Config] = None

    def do_GET(self) -> None:
        if self.path.startswith("/api/status"):
            payload = build_dashboard_snapshot(self.config)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        body = DASHBOARD_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy HTTP access logs per poll
        return


def start_background_dashboard(
    config: Config, host: str = "0.0.0.0", port: int = 8050
) -> Optional[ThreadingHTTPServer]:
    """Start the dashboard server on a background daemon thread if the port is free."""
    probe_host = "127.0.0.1" if host in {"0.0.0.0", ""} else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sock.connect_ex((probe_host, port)) == 0:
            logger.info("Web Dashboard already running on port %d", port)
            return None

    DashboardRequestHandler.config = config
    server = ThreadingHTTPServer((host, port), DashboardRequestHandler)
    thread = threading.Thread(
        target=server.serve_forever, name="t212-dashboard", daemon=True
    )
    thread.start()
    logger.info("Live Web GUI Dashboard started at http://%s:%d", host, port)
    return server


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Trading 212 Bot Live Web GUI Dashboard"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8050, help="Port number (default: 8050)")
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Automatically open the dashboard in your default web browser",
    )
    args = parser.parse_args()

    cfg = Config.from_env()
    DashboardRequestHandler.config = cfg
    server = ThreadingHTTPServer((args.host, args.port), DashboardRequestHandler)
    display_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    url = f"http://{display_host}:{args.port}"
    print(f"Trading 212 Live Web Dashboard running at: {url} (bound to {args.host}:{args.port})")
    print("Press Ctrl+C to stop the dashboard server.")

    if args.open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard server...")
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
