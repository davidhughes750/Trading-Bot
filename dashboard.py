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
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from pathlib import Path
from typing import Any, Dict, List, Optional

from bot import __version__
from bot.config import Config
from bot.market_calendar import (
    holiday_name,
    is_early_close,
    is_trading_day,
    market_close_minute,
    next_trading_day,
)

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
    candles_by_symbol: Dict[str, List[Dict[str, Any]]] = {
        str(r["symbol"]): list(r.get("candles") or [])
        for r in recommendations
        if "symbol" in r
    }

    # 3. Parse recent log lines and latest portfolio heartbeat
    recent_logs: List[Dict[str, str]] = []
    latest_equity = cfg.paper_initial_equity
    latest_cash = cfg.paper_initial_equity
    latest_dd_pct = 0.0
    last_heartbeat_ts = "Waiting for bot tick..."
    bot_mode = cfg.execution_mode.upper()
    equity_history: List[Dict[str, Any]] = []
    equity_history_24h: List[Dict[str, Any]] = []
    session_info: Dict[str, Any] = {}

    if log_path.exists():
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            scan_lines = lines[-12000:] if len(lines) > 12000 else lines
            all_records: List[Dict[str, Any]] = []
            for line in scan_lines:
                if "Total Equity=" in line:
                    m = PORTFOLIO_LINE_RE.search(line)
                    if m:
                        all_records.append(
                            {
                                "ts": m.group("ts"),
                                "equity": float(m.group("equity")),
                                "cash": float(m.group("cash")),
                                "dd": float(m.group("dd")),
                            }
                        )

            if all_records:
                last_rec = all_records[-1]
                last_heartbeat_ts = last_rec["ts"]
                latest_equity = last_rec["equity"]
                latest_cash = last_rec["cash"]
                latest_dd_pct = last_rec["dd"]

                et_tz = ZoneInfo("America/New_York")
                now_et = datetime.now(et_tz)
                today_et_date = now_et.date()

                converted_records: List[Dict[str, Any]] = []
                for r in all_records:
                    try:
                        dt_utc = datetime.strptime(r["ts"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        dt_et = dt_utc.astimezone(et_tz)
                        converted_records.append(
                            {
                                "dt_et": dt_et,
                                "ts": r["ts"],
                                "equity": r["equity"],
                                "cash": r["cash"],
                                "dd": r["dd"],
                            }
                        )
                    except Exception:
                        continue

                # Determine target trading session date (today in ET, or most recent date in logs)
                available_dates = {r["dt_et"].date() for r in converted_records}
                target_date = today_et_date if today_et_date in available_dates else (max(available_dates) if available_dates else today_et_date)

                close_min = market_close_minute(target_date) if is_trading_day(target_date) else 960
                open_min = 570  # 09:30 ET
                session_total_mins = max(60, close_min - open_min)

                # Find opening anchor (equity right at or before 09:30 ET)
                anchor_equity = latest_equity
                session_raw_points: List[Dict[str, Any]] = []
                for r in converted_records:
                    if r["dt_et"].date() == target_date:
                        mins = r["dt_et"].hour * 60 + r["dt_et"].minute
                        if mins <= open_min:
                            anchor_equity = r["equity"]
                        elif mins <= close_min + 5:
                            session_raw_points.append(r)

                # Downsample session into 1-minute buckets spanning the entire trading day
                minute_buckets: Dict[int, Dict[str, Any]] = {}
                minute_buckets[0] = {
                    "timestamp": f"{target_date} 09:30:00 ET",
                    "time_et": "09:30 AM",
                    "session_min": 0,
                    "minute_of_day": open_min,
                    "equity": round(anchor_equity, 2),
                    "cash": round(latest_cash, 2),
                }

                for r in session_raw_points:
                    m_of_day = r["dt_et"].hour * 60 + r["dt_et"].minute
                    s_min = max(0, min(session_total_mins, m_of_day - open_min))
                    minute_buckets[s_min] = {
                        "timestamp": r["ts"],
                        "time_et": r["dt_et"].strftime("%I:%M %p"),
                        "session_min": s_min,
                        "minute_of_day": m_of_day,
                        "equity": round(r["equity"], 2),
                        "cash": round(r["cash"], 2),
                    }

                # Ensure current real-time point is anchored
                if converted_records and converted_records[-1]["dt_et"].date() == target_date:
                    latest_r = converted_records[-1]
                    latest_m_of_day = latest_r["dt_et"].hour * 60 + latest_r["dt_et"].minute
                    latest_s_min = max(0, min(session_total_mins, latest_m_of_day - open_min))
                    minute_buckets[latest_s_min] = {
                        "timestamp": latest_r["ts"],
                        "time_et": latest_r["dt_et"].strftime("%I:%M %p"),
                        "session_min": latest_s_min,
                        "minute_of_day": latest_m_of_day,
                        "equity": round(latest_r["equity"], 2),
                        "cash": round(latest_r["cash"], 2),
                    }

                equity_history = [minute_buckets[k] for k in sorted(minute_buckets.keys())]

                # Compute session metadata
                eq_values = [p["equity"] for p in equity_history]
                start_eq = equity_history[0]["equity"] if equity_history else latest_equity
                curr_eq = equity_history[-1]["equity"] if equity_history else latest_equity
                day_high = max(eq_values) if eq_values else curr_eq
                day_low = min(eq_values) if eq_values else curr_eq
                day_pnl = round(curr_eq - start_eq, 2)
                day_pnl_pct = round((day_pnl / start_eq) * 100, 2) if start_eq > 0 else 0.0

                session_info = {
                    "target_date": target_date.strftime("%Y-%m-%d"),
                    "session_date_formatted": target_date.strftime("%A, %b %d, %Y"),
                    "open_time_et": "09:30 AM",
                    "close_time_et": f"{close_min // 60:02d}:{close_min % 60:02d} {'PM' if close_min >= 720 else 'AM'}",
                    "total_session_minutes": session_total_mins,
                    "start_equity": round(start_eq, 2),
                    "current_equity": round(curr_eq, 2),
                    "day_high": round(day_high, 2),
                    "day_low": round(day_low, 2),
                    "day_pnl": day_pnl,
                    "day_pnl_pct": day_pnl_pct,
                    "is_current_day": target_date == today_et_date,
                }

                # Rolling 24-hour history
                cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
                points_24h = []
                for r in all_records:
                    try:
                        dt = datetime.strptime(r["ts"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        if dt >= cutoff_24h:
                            points_24h.append({
                                "timestamp": r["ts"],
                                "equity": round(r["equity"], 2),
                                "cash": round(r["cash"], 2),
                            })
                    except Exception:
                        pass
                if len(points_24h) > 100:
                    step = max(1, len(points_24h) // 80)
                    equity_history_24h = points_24h[::step]
                    if points_24h and (not equity_history_24h or equity_history_24h[-1] != points_24h[-1]):
                        equity_history_24h.append(points_24h[-1])
                else:
                    equity_history_24h = points_24h

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
        except Exception as e:
            logger.warning("Error parsing log for session equity history: %s", e)

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

        opened_at_str = str(pos.get("opened_at", ""))
        highest_p = max(entry, current_price, float(pos.get("highest_price") or entry))
        lowest_p = min(entry, current_price, float(pos.get("lowest_price") or entry))

        # Build trade journey trajectory from BUY anchor -> intermediate bars/ticks -> live mark
        raw_history = list(pos.get("price_history") or [])
        journey_points: List[Dict[str, Any]] = [
            {"ts": opened_at_str, "price": round(entry, 4), "event": "BUY"}
        ]

        # Backfill from 15m candles if position was opened before live price_history tracking
        if len(raw_history) <= 2 and candles_by_symbol.get(sym):
            try:
                opened_dt = datetime.fromisoformat(opened_at_str.replace("Z", "+00:00"))
                if opened_dt.tzinfo is None:
                    opened_dt = opened_dt.replace(tzinfo=timezone.utc)
                for c in candles_by_symbol.get(sym, []):
                    c_iso = str(c.get("ts_iso") or "")
                    c_dt = None
                    if c_iso:
                        try:
                            c_dt = datetime.fromisoformat(c_iso.replace("Z", "+00:00"))
                            if c_dt.tzinfo is None:
                                c_dt = c_dt.replace(tzinfo=timezone.utc)
                        except Exception:
                            c_dt = None
                    elif c.get("datetime"):
                        try:
                            parsed = datetime.strptime(
                                f"{opened_dt.year} {c['datetime']}", "%Y %b %d, %H:%M UTC"
                            ).replace(tzinfo=timezone.utc)
                            c_dt = parsed
                            c_iso = parsed.isoformat()
                        except Exception:
                            c_dt = None
                    if c_dt is not None and c_dt >= opened_dt:
                        c_price = float(c.get("c") or entry)
                        if c_price > 0:
                            journey_points.append(
                                {"ts": c_iso or str(c.get("datetime") or ""), "price": round(c_price, 4)}
                            )
            except Exception:
                pass

        for pt in raw_history:
            if not isinstance(pt, dict):
                continue
            pt_price = float(pt.get("price") or 0.0)
            pt_ts = str(pt.get("ts") or "")
            if pt_price <= 0:
                continue
            # Avoid duplicating the entry anchor
            if len(journey_points) == 1 and abs(pt_price - entry) < 1e-5 and pt_ts == opened_at_str:
                continue
            journey_points.append({"ts": pt_ts, "price": round(pt_price, 4)})

        # Always end with live mark
        now_iso = datetime.now(timezone.utc).isoformat()
        if len(journey_points) == 1 or abs(journey_points[-1]["price"] - current_price) >= 1e-4:
            journey_points.append({"ts": now_iso, "price": round(current_price, 4), "event": "NOW"})
        else:
            journey_points[-1]["event"] = "NOW"

        for jp in journey_points:
            highest_p = max(highest_p, float(jp["price"]))
            lowest_p = min(lowest_p, float(jp["price"]))

        enriched_positions.append(
            {
                "symbol": sym,
                "side": side,
                "quantity": round(qty, 4),
                "entry_price": round(entry, 4),
                "current_price": round(current_price, 4),
                "highest_price": round(highest_p, 4),
                "lowest_price": round(lowest_p, 4),
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
                "opened_at": opened_at_str,
                "price_history": journey_points,
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

    # Compute UK Market Session status (Europe/London: 08:00-16:30 London time, Mon-Fri)
    uk_session_state = "CLOSED"
    uk_session_badge = "AMBER"
    uk_session_detail = "London Stock Exchange (08:00–16:30 UK)"
    seconds_to_uk_open = 0
    seconds_to_uk_close = 0
    total_uk_closed_seconds = 55800  # 15.5 hours weekday night (16:30 to 08:00)
    uk_market_is_open = False
    next_uk_open_str = ""
    next_uk_open_iso = ""

    try:
        now_uk = now_utc.astimezone(ZoneInfo("Europe/London"))
        uk_str = now_uk.strftime("%H:%M UK")
        mins_uk = now_uk.hour * 60 + now_uk.minute
        uk_open_min = 8 * 60  # 08:00
        uk_close_min = 16 * 60 + 30  # 16:30
        is_uk_weekday = now_uk.weekday() < 5

        if is_uk_weekday and mins_uk < uk_open_min:
            next_uk_open_date = now_uk.date()
        elif is_uk_weekday and mins_uk < uk_close_min:
            next_uk_open_date = now_uk.date()
        else:
            days_ahead = (7 - now_uk.weekday()) if now_uk.weekday() >= 4 else 1
            next_uk_open_date = now_uk.date() + timedelta(days=days_ahead)

        next_uk_open_dt = datetime(
            next_uk_open_date.year,
            next_uk_open_date.month,
            next_uk_open_date.day,
            8,
            0,
            tzinfo=ZoneInfo("Europe/London"),
        )
        next_uk_open_iso = next_uk_open_dt.isoformat()
        next_uk_open_str = next_uk_open_date.strftime("%a %d %b") + " 08:00 UK"

        if not is_uk_weekday:
            uk_session_state = "WEEKEND (CLOSED)"
            uk_session_badge = "AMBER"
            uk_session_detail = f"Weekend ({uk_str}) • Reopens {next_uk_open_str}"
            seconds_to_uk_open = max(0, int((next_uk_open_dt - now_uk).total_seconds()))
            total_uk_closed_seconds = int(63.5 * 3600)
        elif mins_uk < uk_open_min:
            wait_m = uk_open_min - mins_uk
            uk_session_state = "PRE-MARKET"
            uk_session_badge = "AMBER"
            uk_session_detail = f"London Pre-Market ({uk_str}) • LSE opens in {wait_m // 60}h {wait_m % 60}m"
            seconds_to_uk_open = max(0, int((next_uk_open_dt - now_uk).total_seconds()))
            total_uk_closed_seconds = 55800
        elif mins_uk >= uk_close_min:
            uk_session_state = "MARKET CLOSED"
            uk_session_badge = "AMBER"
            uk_session_detail = f"LSE Closed ({uk_str}) • Reopens {next_uk_open_str}"
            seconds_to_uk_open = max(0, int((next_uk_open_dt - now_uk).total_seconds()))
            total_uk_closed_seconds = 55800 if now_uk.weekday() < 4 else int(63.5 * 3600)
        elif mins_uk < uk_open_min + cfg.skip_opening_minutes:
            rem_m = (uk_open_min + cfg.skip_opening_minutes) - mins_uk
            uk_session_state = "OPENING GUARD"
            uk_session_badge = "AMBER"
            uk_session_detail = f"LSE Opening Guard ({uk_str}) • Entries unlock in {rem_m}m"
            uk_market_is_open = True
            close_uk_dt = datetime(
                now_uk.year,
                now_uk.month,
                now_uk.day,
                16,
                30,
                tzinfo=ZoneInfo("Europe/London"),
            )
            seconds_to_uk_close = max(0, int((close_uk_dt - now_uk).total_seconds()))
        else:
            rem_m = uk_close_min - mins_uk
            uk_session_state = "MARKET OPEN"
            uk_session_badge = "GREEN"
            uk_session_detail = f"LSE 3x ETP Session ({uk_str}) • Closes in {rem_m // 60}h {rem_m % 60}m"
            uk_market_is_open = True
            close_uk_dt = datetime(
                now_uk.year,
                now_uk.month,
                now_uk.day,
                16,
                30,
                tzinfo=ZoneInfo("Europe/London"),
            )
            seconds_to_uk_close = max(0, int((close_uk_dt - now_uk).total_seconds()))
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
    us_cnt = sum(1 for p in enriched_positions if not str(p.get("symbol", "")).endswith("_UK_EQ"))
    uk_cnt = sum(1 for p in enriched_positions if str(p.get("symbol", "")).endswith("_UK_EQ"))
    max_us = getattr(cfg, "max_us_positions", 3)
    max_uk = getattr(cfg, "max_uk_positions", 1)
    slots_free = max(0, max_cnt - open_cnt)
    gate2_status = (
        f"US {us_cnt}/{max_us} • UK {uk_cnt}/{max_uk} ({slots_free} OPEN)"
        if slots_free > 0
        else f"{max_cnt}/{max_cnt} SLOTS FULL"
    )
    gate2_badge = "GREEN" if slots_free > 0 else "AMBER"
    gate2_detail = (
        f"{open_cnt}/{max_cnt} active (🇺🇸 {us_cnt}/{max_us} US • 🇬🇧 {uk_cnt}/{max_uk} UK ETP) • ${latest_cash:.2f} free cash ready"
        if slots_free > 0
        else f"All {max_cnt}/{max_cnt} slots full (🇺🇸 {us_cnt}/{max_us} US • 🇬🇧 {uk_cnt}/{max_uk} UK) • AI rotation active (>=80 score)"
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

    closed_trades_list: List[Dict[str, Any]] = [
        dict(t) for t in list(state_data.get("closed_trades") or [])[:25] if isinstance(t, dict)
    ]
    postmortems_list: List[Dict[str, Any]] = []
    try:
        pm_path = Path(cfg.ai_decisions_file).parent / "loss_postmortems.json"
        if pm_path.exists():
            pm_raw = json.loads(pm_path.read_text(encoding="utf-8"))
            if isinstance(pm_raw, dict):
                postmortems_list = [x for x in pm_raw.get("postmortems", []) if isinstance(x, dict)]
    except Exception:
        postmortems_list = []

    pm_by_key = {
        (str(x.get("symbol", "")), str(x.get("closed_at", ""))[:16]): x
        for x in postmortems_list
    }
    try:
        from bot.ai_manager import AIPortfolioManager

        pm_helper = AIPortfolioManager(cfg)
    except Exception:
        pm_helper = None

    for t in closed_trades_list:
        if float(t.get("net_pnl") or 0.0) < 0.0:
            k = (str(t.get("symbol", "")), str(t.get("closed_at", ""))[:16])
            pm_obj = pm_by_key.get(k)
            if pm_obj is None and pm_helper is not None:
                pm_obj = pm_helper._build_deterministic_postmortem(t)
            if pm_obj is not None:
                t["postmortem"] = pm_obj
                t["outcome_tag"] = pm_obj.get("outcome_tag", t.get("outcome_tag", "STOPPED_OUT"))

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
        "uk_market_session": {
            "state": uk_session_state,
            "badge": uk_session_badge,
            "detail": uk_session_detail,
            "is_open": uk_market_is_open,
            "seconds_to_open": seconds_to_uk_open,
            "seconds_to_close": seconds_to_uk_close,
            "total_closed_seconds": total_uk_closed_seconds,
            "next_open_str": next_uk_open_str,
            "next_open_iso": next_uk_open_iso,
        },
        "gates": gates,
        "cooldowns": active_cooldowns,
        "watch_radar": watch_radar[:4],
        "closed_trades": closed_trades_list,
        "equity_history": locals().get("equity_history", []),
        "equity_history_24h": locals().get("equity_history_24h", []),
        "session_info": locals().get("session_info", {}),
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


WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"


def _load_dashboard_html() -> str:
    html_file = TEMPLATES_DIR / "index.html"
    if html_file.exists():
        return html_file.read_text(encoding="utf-8")
    return "<!DOCTYPE html><html><body><h1>Trading Bot Dashboard</h1><p>Template not found.</p></body></html>"


DASHBOARD_HTML: str = _load_dashboard_html()


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """Lightweight HTTP handler serving the HTML UI, static assets, and `/api/status` JSON feed."""

    config: Optional[Config] = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/status"):
            payload = build_dashboard_snapshot(self.config)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith("/static/"):
            rel_path = path[len("/static/") :].lstrip("/")
            file_path = (STATIC_DIR / rel_path).resolve()
            if file_path.is_file() and str(file_path).startswith(str(STATIC_DIR.resolve())):
                mime_type, _ = mimetypes.guess_type(str(file_path))
                if not mime_type:
                    mime_type = "application/octet-stream"
                body = file_path.read_bytes()
                self.send_response(200)
                content_type = (
                    f"{mime_type}; charset=utf-8"
                    if "text" in mime_type or "javascript" in mime_type
                    else mime_type
                )
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "public, max-age=3600")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            else:
                self.send_error(404, "Static file not found")
                return

        html_file = TEMPLATES_DIR / "index.html"
        if html_file.exists():
            body = html_file.read_bytes()
        else:
            body = DASHBOARD_HTML.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
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
