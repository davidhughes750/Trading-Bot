"""Reports built from the bot's own logs.

- `analyze_scans`: does a higher screener score lead to better forward returns?
  Uses logs/scan_log.jsonl (every symbol scored on every candle).
- `analyze_ai_decisions`: what did setups the AI approved vs vetoed go on to do?
  Uses logs/ai_entry_decisions.jsonl.
- `analyze_journal`: performance, slippage and price-source summary of real trades.
  Uses logs/trade_journal.jsonl.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

import pandas as pd

from bot.backtest import MAX_DAYS_BY_INTERVAL, load_history, simulate_bracket
from bot.config import Config

HORIZONS = (4, 8, 26)  # bars ahead: 1h, 2h and ~1 trading day on 15m bars
SCORE_BUCKETS = (90, 85, 80, 76, 70, 60, 50)


def score_bucket(score: float) -> str:
    for lo in SCORE_BUCKETS:
        if score >= lo:
            return f"{lo}+"
    return f"<{SCORE_BUCKETS[-1]}"


def _history_for(config: Config, records: List[Dict[str, Any]], ts_key: str) -> Dict[str, pd.DataFrame]:
    interval = config.timeframe.lower()
    oldest = min(pd.Timestamp(r[ts_key]) for r in records)
    if oldest.tzinfo is None:
        oldest = oldest.tz_localize("UTC")
    days_back = (datetime.now(timezone.utc) - oldest.to_pydatetime()).days + 3
    days = min(max(days_back, 5), MAX_DAYS_BY_INTERVAL.get(interval, 59))
    symbols = sorted({r["symbol"] for r in records})
    return load_history(config, symbols, days, interval)


def _bar_index(df: pd.DataFrame, ts: Any) -> Optional[int]:
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    idx = df.index[df["timestamp"] == stamp]
    return int(idx[0]) if len(idx) else None


def _table(title: str, header: List[str], rows: Iterable[List[Any]]) -> str:
    rows = list(rows)
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) if rows else len(str(h)) for i, h in enumerate(header)]
    out = ["", title, "  " + "  ".join(str(h).rjust(w) for h, w in zip(header, widths))]
    out += ["  " + "  ".join(str(v).rjust(w) for v, w in zip(r, widths)) for r in rows]
    return "\n".join(out)


def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def analyze_scans(config: Config, records: List[Dict[str, Any]], history: Optional[Dict[str, pd.DataFrame]] = None) -> str:
    """Forward returns of every scanned candidate, grouped by score bucket."""
    records = [r for r in records if r.get("candle_ts") and r.get("symbol")]
    if not records:
        return "No scan records yet (logs/scan_log.jsonl). Let the bot run through a few sessions."
    history = history if history is not None else _history_for(config, records, "candle_ts")

    groups: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    missing = 0
    for r in records:
        df = history.get(r["symbol"])
        i = _bar_index(df, r["candle_ts"]) if df is not None else None
        if i is None:
            missing += 1
            continue
        close = float(df["close"].iloc[i])
        atr = float(r.get("atr") or 0.0)
        for key in (score_bucket(float(r["score"])), "actionable" if r.get("actionable") else "not actionable", "ALL"):
            g = groups[key]
            for h in HORIZONS:
                if i + h < len(df):
                    g[f"fwd{h}"].append((float(df["close"].iloc[i + h]) / close - 1.0) * 100.0)
            if atr > 0 and i + 1 < len(df):
                res = simulate_bracket(
                    df.iloc[i + 1:],
                    entry_price=float(df["open"].iloc[i + 1]),
                    stop_loss=float(df["open"].iloc[i + 1]) - config.stop_loss_atr_mult * atr,
                    take_profit=float(df["open"].iloc[i + 1]) + config.take_profit_atr_mult * atr,
                )
                g["bracket_r"].append(res["r_multiple"])

    order = [f"{lo}+" for lo in SCORE_BUCKETS] + [f"<{SCORE_BUCKETS[-1]}", "actionable", "not actionable", "ALL"]
    rows = []
    for key in order:
        g = groups.get(key)
        if not g:
            continue
        n = len(g.get("bracket_r", [])) or len(g.get(f"fwd{HORIZONS[0]}", []))
        row = [key, n]
        for h in HORIZONS:
            xs = g.get(f"fwd{h}", [])
            row.append(f"{_mean(xs):+.3f}%" if xs else "-")
        xs = g.get(f"fwd{HORIZONS[0]}", [])
        row.append(f"{sum(1 for x in xs if x > 0) / len(xs) * 100:.0f}%" if xs else "-")
        br = g.get("bracket_r", [])
        row.append(f"{_mean(br):+.3f}R" if br else "-")
        rows.append(row)

    header = ["score", "n"] + [f"+{h} bars" for h in HORIZONS] + [f"up after {HORIZONS[0]}", "bracket avg R"]
    text = _table(
        f"Screener score vs what happened next ({len(records)} scan records)",
        header,
        rows,
    )
    text += (
        "\n\n  'bracket avg R' replays a plain stop/target bracket "
        f"({config.stop_loss_atr_mult}x / {config.take_profit_atr_mult}x ATR, max 26 bars) from the next open."
        "\n  If higher score buckets do not show better numbers, the score is not adding information."
    )
    if missing:
        text += f"\n  {missing} records had no matching bar (older than the data window or a data gap)."
    return text


def analyze_ai_decisions(config: Config, records: List[Dict[str, Any]], history: Optional[Dict[str, pd.DataFrame]] = None) -> str:
    """Replay approved and vetoed setups with the same bracket to see if the veto helps."""
    records = [r for r in records if r.get("candle_ts") and r.get("symbol")]
    if not records:
        return "No AI decisions logged yet (logs/ai_entry_decisions.jsonl)."
    history = history if history is not None else _history_for(config, records, "candle_ts")

    groups: Dict[str, List[float]] = defaultdict(list)
    outcomes: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in records:
        df = history.get(r["symbol"])
        i = _bar_index(df, r["candle_ts"]) if df is not None else None
        if i is None or i + 1 >= len(df):
            continue
        res = simulate_bracket(
            df.iloc[i + 1:],
            entry_price=float(r["reference_price"]),
            stop_loss=float(r["stop_loss"]),
            take_profit=float(r["take_profit"]),
        )
        groups[r["decision"]].append(res["r_multiple"])
        outcomes[r["decision"]][res["outcome"]] += 1

    rows = []
    for decision, rs in sorted(groups.items()):
        o = outcomes[decision]
        rows.append([
            decision, len(rs),
            f"{sum(1 for x in rs if x > 0) / len(rs) * 100:.0f}%",
            f"{_mean(rs):+.3f}R",
            o.get("target", 0), o.get("stop", 0), o.get("timeout", 0),
        ])
    text = _table(
        "AI entry decisions replayed with the same stop/target bracket",
        ["decision", "n", "win%", "avg R", "targets", "stops", "timeouts"],
        rows,
    )
    text += (
        "\n\n  If VETO setups did about as well as APPROVE ones, the AI is not filtering out bad trades."
        "\n  You need a few dozen decisions of each kind before reading much into this."
    )
    return text


def analyze_journal(records: List[Dict[str, Any]]) -> str:
    """Summary of real closed trades from the permanent journal."""
    recs = [r for r in records if not r.get("backfilled")]
    if not recs:
        return "No trades in the journal yet (logs/trade_journal.jsonl)."
    n = len(recs)
    net = [float(r.get("net_pnl", 0.0)) for r in recs]
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x <= 0]
    ccy = recs[-1].get("currency", "")
    lines = [
        "",
        f"Trade journal: {n} trades",
        f"  Win rate        {len(wins) / n * 100:.1f}%",
        f"  Avg R           {_mean([float(r.get('r_multiple', 0.0)) for r in recs]):+.3f}R",
        f"  Net P&L         {sum(net):+.2f} {ccy}  (expectancy {sum(net) / n:+.2f} per trade)",
        f"  Avg win / loss  {_mean(wins) if wins else 0:+.2f} / {_mean(losses) if losses else 0:+.2f}",
        f"  Fees            {sum(float(r.get('fee_paid', 0.0)) for r in recs):.2f} {ccy}",
    ]

    def _slip(key: str) -> str:
        xs = [float(r[key]) for r in recs if r.get(key) is not None]
        return f"{_mean(xs):+.3f}% avg over {len(xs)} fills" if xs else "no data yet"

    lines.append(f"  Entry slippage  {_slip('entry_slippage_pct')}  (positive = paid more than the quote)")
    lines.append(f"  Exit slippage   {_slip('exit_slippage_pct')}")
    sources: Dict[str, int] = defaultdict(int)
    for r in recs:
        sources[str(r.get("exit_price_source", "unknown (older record)"))] += 1
    lines.append("  Exit price source: " + ", ".join(f"{k} {v}" for k, v in sorted(sources.items())))

    by_tag: Dict[str, List[float]] = defaultdict(list)
    for r in recs:
        by_tag[str(r.get("outcome_tag", "?"))].append(float(r.get("net_pnl", 0.0)))
    lines.append(_table("By outcome", ["outcome", "n", "net"], [[k, len(v), f"{sum(v):+.2f}"] for k, v in sorted(by_tag.items())]))
    if n < 30:
        lines.append("\n  Fewer than 30 trades: too few to judge the strategy yet.")
    return "\n".join(lines)


def run_named(name: str, config: Config, loader: Callable[[str], List[Dict[str, Any]]]) -> str:
    if name == "scans":
        return analyze_scans(config, loader("scan_log.jsonl"))
    if name == "ai":
        return analyze_ai_decisions(config, loader("ai_entry_decisions.jsonl"))
    if name == "journal":
        return analyze_journal(loader("trade_journal.jsonl"))
    raise ValueError(name)
