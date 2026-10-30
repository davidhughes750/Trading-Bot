"""Permanent equity history (logs/equity_history.jsonl).

The bot logs equity every poll, but log files rotate, so the dashboard used to
lose its history. This module saves one equity reading per `interval_sec` to its
own append-only file, which the dashboard reads for the all-time chart and the
drawdown from the all-time high.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bot.utils import append_jsonl, atomic_write_text, read_jsonl

logger = logging.getLogger(__name__)

# Matches the bot's "Trading 212 Portfolio | Total Equity=£474.61 | Free Cash=..." log line
PORTFOLIO_LINE_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?"
    r"Total Equity=[^0-9]*(?P<equity>[0-9.]+)\s*\|\s*"
    r"Free Cash=[^0-9]*(?P<cash>[0-9.]+)\s*\|\s*"
    r"Open Positions=(?P<open>\d+)/(?P<max_open>\d+)\s*\|\s*"
    r"24h DD=(?P<dd>[0-9.]+)%"
)


class EquityHistory:
    def __init__(self, path: str | Path, interval_sec: int = 300) -> None:
        self.path = Path(path)
        self.interval_sec = interval_sec
        self._last_bucket: Optional[int] = None

    def maybe_record(self, equity: float, cash: float, now: Optional[datetime] = None) -> bool:
        """Append a reading if this is the first one in the current interval."""
        if equity <= 0:
            return False
        now = now or datetime.now(timezone.utc)
        bucket = int(now.timestamp()) // self.interval_sec
        if bucket == self._last_bucket:
            return False
        self._last_bucket = bucket
        try:
            append_jsonl(self.path, {"ts": now.isoformat(), "equity": round(equity, 2), "cash": round(cash, 2)})
            return True
        except Exception as exc:
            logger.warning("Could not write equity history: %s", exc)
            return False

    def seed_from_logs(self, log_file: str | Path) -> int:
        """Build the history from the bot's existing (rotated) log files, once.

        Does nothing if the history file already exists. Log timestamps are in the
        machine's local time and are converted to UTC.
        """
        if self.path.exists():
            return 0
        log_path = Path(log_file)
        # Rotated logs are trading_bot.log.1 (newest) ... .N (oldest); read oldest first
        rotated = [
            f for f in log_path.parent.glob(log_path.name + ".*")
            if f.suffix.lstrip(".").isdigit()
        ]
        rotated.sort(key=lambda f: int(f.suffix.lstrip(".")), reverse=True)
        files = rotated + ([log_path] if log_path.is_file() else [])
        buckets: Dict[int, Dict[str, Any]] = {}
        for f in files:
            try:
                for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                    if "Total Equity=" not in line:
                        continue
                    m = PORTFOLIO_LINE_RE.search(line)
                    if not m:
                        continue
                    ts = datetime.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S").astimezone().astimezone(timezone.utc)
                    equity = float(m.group("equity"))
                    if equity <= 0:
                        continue
                    b = int(ts.timestamp()) // self.interval_sec
                    if b not in buckets:
                        buckets[b] = {"ts": ts.isoformat(), "equity": round(equity, 2), "cash": round(float(m.group("cash")), 2)}
            except Exception as exc:
                logger.warning("Could not read %s while seeding equity history: %s", f, exc)
        if not buckets:
            return 0
        atomic_write_text(self.path, "".join(json.dumps(buckets[b]) + "\n" for b in sorted(buckets)))
        self._last_bucket = max(buckets)
        logger.info("Seeded equity history with %d readings from old log files.", len(buckets))
        return len(buckets)


def load_equity_history(path: str | Path) -> List[Dict[str, Any]]:
    points = [p for p in read_jsonl(path) if isinstance(p, dict) and p.get("equity")]
    points.sort(key=lambda p: p["ts"])
    return points


def downsample(points: List[Dict[str, Any]], max_points: int = 400) -> List[Dict[str, Any]]:
    """Thin a long series for charting, keeping the first, last, peak and trough."""
    if len(points) <= max_points:
        return points
    step = len(points) / float(max_points)
    keep = {int(i * step) for i in range(max_points)} | {0, len(points) - 1}
    keep.add(max(range(len(points)), key=lambda i: points[i]["equity"]))
    keep.add(min(range(len(points)), key=lambda i: points[i]["equity"]))
    return [points[i] for i in sorted(keep)]


def drawdown_stats(points: List[Dict[str, Any]]) -> Dict[str, Any]:
    """All-time peak, current drawdown from it, and the worst drawdown so far."""
    if not points:
        return {}
    peak = -1.0
    peak_ts = ""
    max_dd = 0.0
    max_dd_ts = ""
    for p in points:
        eq = float(p["equity"])
        if eq > peak:
            peak, peak_ts = eq, p["ts"]
        dd = (peak - eq) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd, max_dd_ts = dd, p["ts"]
    first, last = float(points[0]["equity"]), float(points[-1]["equity"])
    return {
        "start_ts": points[0]["ts"],
        "start_equity": round(first, 2),
        "current_equity": round(last, 2),
        "change": round(last - first, 2),
        "change_pct": round((last / first - 1.0) * 100.0, 2) if first > 0 else 0.0,
        "peak_equity": round(peak, 2),
        "peak_ts": peak_ts,
        "current_drawdown_pct": round((peak - last) / peak * 100.0, 2) if peak > 0 else 0.0,
        "max_drawdown_pct": round(max_dd * 100.0, 2),
        "max_drawdown_ts": max_dd_ts,
    }
