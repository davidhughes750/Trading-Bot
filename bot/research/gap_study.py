"""Does buying a big gap-down (an earnings or news crash) make money afterwards?

Prompted by DKNG, which gapped down 26% overnight on 2026-11-06 and bounced about 7% from the open.
The question: across the stocks the bot scans, after a stock opens 10%+ below its previous close on a
day the market as a whole did not fall, does it beat the same stocks on an ordinary day?

Rules are fixed before running and nothing is tuned:
  Event      open / previous close - 1 <= -10%, SPY's own gap above -2% (so it is a stock-specific shock),
             at most one event per stock per 10 trading days.
  Entries    A: buy the gap-day open (an upper bound: the live bot waits 15 minutes after the open)
             B: buy the gap-day close
             C: buy the next day's open (after the bounce or the slide is visible)
  Exits      the close 1, 3, 5 or 10 trading days after the gap day.
  Costs      0.7% round trip (0.3% Trading 212 FX fee plus slippage on a wide-spread day); entry A pays a further
             0.5% because opening spreads are the widest of the day.
  Baseline   the same stocks on every ordinary day with the same entry and exit rule, so a stock's general drift
             is not mistaken for a gap effect.

Known bias, which flatters the result: the universe is today's list of stocks, so companies that gapped down
and never recovered are missing (survivorship). Read any positive number as an upper bound.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from bot.config import Config
from bot.data_handler import DataHandler

GAP_THRESHOLD = -0.10
SPY_GAP_LIMIT = -0.02
COOLDOWN_DAYS = 10
HORIZONS = [1, 3, 5, 10]
COST_ROUND_TRIP = 0.007
OPEN_EXTRA_COST = 0.005
SENSITIVITY_THRESHOLDS = [-0.07, -0.15]
SCHEMES = {"A": "buy gap-day open", "B": "buy gap-day close", "C": "buy next-day open"}


def scan_symbols(config: Config) -> List[str]:
    """US symbols the bot scans, as Trading 212 tickers."""
    from bot.screener import StockScreener
    from bot.strategy_engine import StrategyEngine

    dh = DataHandler(config)
    universe = StockScreener(config, dh, StrategyEngine(config)).get_scan_universe()
    return sorted({s for s in universe if str(s).endswith("_US_EQ")})


def load_daily(
    config: Config, symbols: List[str], cache_dir: Path = Path("logs/backtest_cache"), refresh: bool = False
) -> Dict[str, pd.DataFrame]:
    """Daily open/close (split-adjusted, not dividend-adjusted) for each symbol, indexed by date."""
    dh = DataHandler(config)
    today = datetime.now().strftime("%Y%m%d")
    cache_dir.mkdir(parents=True, exist_ok=True)
    out: Dict[str, pd.DataFrame] = {}
    for sym in symbols + ["SPY_US_EQ"]:
        cache = cache_dir / f"{sym}_1d_max_raw_{today}.csv"
        try:
            if cache.exists() and not refresh:
                df = pd.read_csv(cache)
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            else:
                df = dh.download_ohlcv(sym, period="max", interval="1d", auto_adjust=False)
                df.to_csv(cache, index=False)
        except Exception:
            continue
        df = df.dropna(subset=["open", "close"])
        df = df[(df["open"] > 0) & (df["close"] > 0)].copy()
        df["date"] = df["timestamp"].dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
        out[sym] = df.drop_duplicates("date").set_index("date")[["open", "close"]]
    return out


def _forward_returns(df: pd.DataFrame) -> pd.DataFrame:
    """For every day: return of each (scheme, horizon) if the stock were entered and exited by the rules."""
    o, c = df["open"], df["close"]
    cols = {}
    for h in HORIZONS:
        cols[f"A{h}"] = c.shift(-h) / o - 1.0
        cols[f"B{h}"] = c.shift(-h) / c - 1.0
        cols[f"C{h}"] = c.shift(-h) / o.shift(-1) - 1.0
    return pd.DataFrame(cols, index=df.index)


def find_events(df: pd.DataFrame, spy_gap: pd.Series, threshold: float = GAP_THRESHOLD) -> pd.DatetimeIndex:
    """Gap-down days for one stock: stock-specific, with a cooldown so one slide is not counted many times."""
    gap = df["open"] / df["close"].shift(1) - 1.0
    market_gap = spy_gap.reindex(df.index)
    hits = df.index[(gap <= threshold) & (market_gap > SPY_GAP_LIMIT)]
    kept: List[pd.Timestamp] = []
    last_pos = -10**9
    for d in hits:
        pos = df.index.get_loc(d)
        if pos - last_pos >= COOLDOWN_DAYS:
            kept.append(d)
            last_pos = pos
    return pd.DatetimeIndex(kept)


def collect(data: Dict[str, pd.DataFrame], threshold: float = GAP_THRESHOLD) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """(events, baseline): one row per event / per ordinary stock-day with every forward return."""
    spy = data["SPY_US_EQ"]
    spy_gap = spy["open"] / spy["close"].shift(1) - 1.0
    ev_rows, base_rows = [], []
    for sym, df in data.items():
        if sym == "SPY_US_EQ" or len(df) < 60:
            continue
        fwd = _forward_returns(df)
        ev_idx = find_events(df, spy_gap, threshold)
        ev = fwd.loc[ev_idx].copy()
        ev["gap"] = (df["open"] / df["close"].shift(1) - 1.0).loc[ev_idx]
        ev["symbol"] = sym
        ev_rows.append(ev)
        base_rows.append(fwd)
    events = pd.concat(ev_rows) if ev_rows else pd.DataFrame()
    baseline = pd.concat(base_rows) if base_rows else pd.DataFrame()
    return events, baseline


def _cost(scheme: str) -> float:
    return COST_ROUND_TRIP + (OPEN_EXTRA_COST if scheme == "A" else 0.0)


def _boot_ci(x: np.ndarray, n: int = 5000, seed: int = 7) -> Tuple[float, float]:
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(n, len(x)), replace=True).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def summarise(events: pd.DataFrame, baseline: pd.DataFrame) -> List[Dict[str, float]]:
    rows = []
    for scheme in SCHEMES:
        for h in HORIZONS:
            col = f"{scheme}{h}"
            x = events[col].dropna().to_numpy()
            if len(x) < 5:
                continue
            net = x - _cost(scheme)
            lo, hi = _boot_ci(net)
            ev_dates = events[col].dropna().index
            half = ev_dates.sort_values()[len(ev_dates) // 2]
            first = (events[col].dropna()[ev_dates < half] - _cost(scheme)).mean()
            second = (events[col].dropna()[ev_dates >= half] - _cost(scheme)).mean()
            rows.append({
                "scheme": scheme, "h": h, "n": len(x), "gross": float(x.mean()), "net": float(net.mean()),
                "median_net": float(np.median(net)), "win": float((net > 0).mean()),
                "base": float(baseline[col].dropna().mean()), "ci_lo": lo, "ci_hi": hi,
                "first_half": float(first), "second_half": float(second),
            })
    return rows


def run(config: Config, refresh: bool = False) -> Dict[str, object]:
    symbols = scan_symbols(config)
    data = load_daily(config, symbols, refresh=refresh)
    events, baseline = collect(data)
    sens = {}
    for thr in SENSITIVITY_THRESHOLDS:
        ev_s, base_s = collect(data, thr)
        sens[thr] = summarise(ev_s, base_s)
    by_year = events.groupby(events.index.year).size().to_dict() if len(events) else {}
    return {
        "n_symbols": len(data) - 1, "events": events, "baseline": baseline, "rows": summarise(events, baseline),
        "sensitivity": sens, "by_year": by_year,
    }


def _pct(v: float) -> str:
    return f"{v * 100:+.2f}%"


def format_report(res: Dict[str, object]) -> str:
    rows = res["rows"]
    events: pd.DataFrame = res["events"]
    lines = [
        "# Gap-down study: does buying a stock-specific crash pay?", "",
        f"Stocks tested: {res['n_symbols']} (the bot's US scan list, as it stands today).",
        f"Events: {len(events)} gap-downs of {abs(GAP_THRESHOLD) * 100:.0f}%+ on days SPY did not fall more than "
        f"{abs(SPY_GAP_LIMIT) * 100:.0f}% at the open.",
        f"Costs: {COST_ROUND_TRIP * 100:.1f}% round trip; entry A pays a further {OPEN_EXTRA_COST * 100:.1f}%.", "",
        "Survivorship bias flatters these numbers: stocks that gapped down and never came back are not in the list.", "",
        "## Results (main rule: 10% gap)", "",
        "| Entry | Exit (days after gap) | Events | Gross avg | Net avg | Net median | Win rate | Ordinary-day avg (gross) | 95% range of net avg | Net, first half | Net, second half |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['scheme']} ({SCHEMES[r['scheme']]}) | {r['h']} | {r['n']} | {_pct(r['gross'])} | {_pct(r['net'])} | "
            f"{_pct(r['median_net'])} | {r['win'] * 100:.0f}% | {_pct(r['base'])} | {_pct(r['ci_lo'])} to {_pct(r['ci_hi'])} | "
            f"{_pct(r['first_half'])} | {_pct(r['second_half'])} |"
        )
    lines += ["", "## Sensitivity to the gap size", "", "| Gap | Entry | Exit | Events | Net avg | Net median | Win rate |", "|---|---|---|---|---|---|---|"]
    for thr, srows in res["sensitivity"].items():
        for r in srows:
            if r["h"] in (1, 5):
                lines.append(f"| {abs(thr) * 100:.0f}%+ | {r['scheme']} | {r['h']} | {r['n']} | {_pct(r['net'])} | {_pct(r['median_net'])} | {r['win'] * 100:.0f}% |")
    lines += ["", "## Events per year", "", ", ".join(f"{y}: {n}" for y, n in sorted(res["by_year"].items()))]
    return "\n".join(lines) + "\n"
