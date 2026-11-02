"""Does a trend filter protect capital in crashes? Tested over decades of index history.

Rules are fixed in advance (no tuning): a daily 200-day moving-average filter and
a monthly 10-month filter, each holding cash (earning US 3-month T-bill rates)
when out of the market. Old index data has unreliable opening prices, so trades
happen at the NEXT day's close (a full day's delay; conservative).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from bot.config import Config
from bot.data_handler import DataHandler
from bot.research.engine import SimResult, simulate
from bot.research.strategies import buy_and_hold, monthly_trend_filter, trend_filter


@dataclass
class Dataset:
    key: str
    yahoo: str
    name: str
    note: str
    start: Optional[str] = None  # trim history before this date


DATASETS = [
    Dataset("SPXTR", "^SP500TR", "S&P 500 (with dividends)", "Total return; the fairest comparison."),
    Dataset("SPX", "^GSPC", "S&P 500 (price only)", "No dividends: holding the index is understated by "
            "~2-4%/yr, which flatters the trend rules. Cash earns 0% before 1960."),
    Dataset("NDX", "^NDX", "Nasdaq-100 (price only)", "Dividends are small (~1%/yr)."),
    Dataset("FTSE", "^FTSE", "FTSE 100 (price only)", "No dividends (~3-4%/yr), which flatters the trend "
            "rules. Cash uses US T-bill rates as a stand-in for UK rates."),
]

CRASHES: List[Tuple[str, str, str]] = [
    ("Great Depression", "1929-09-01", "1932-07-31"),
    ("1973-74 bear market", "1973-01-01", "1974-12-31"),
    ("1987 crash", "1987-08-01", "1987-12-31"),
    ("Dot-com crash", "2000-03-01", "2003-03-31"),
    ("Financial crisis", "2007-10-01", "2009-03-31"),
    ("Covid crash", "2020-02-15", "2020-04-30"),
    ("2022 bear market", "2022-01-01", "2022-10-31"),
]
REBOUNDS: List[Tuple[str, str, str]] = [
    ("Rebound 2009-10", "2009-03-09", "2010-03-31"),
    ("Rebound 2020", "2020-03-23", "2020-12-31"),
]

VARIANTS = {
    "Hold the index": lambda c, s: buy_and_hold(c, s),
    "Daily 200-day average": lambda c, s: trend_filter(c, s, 200),
    "Monthly 10-month average": lambda c, s: monthly_trend_filter(c, s, 10),
}
ROBUSTNESS = {
    "Daily 100-day": lambda c, s: trend_filter(c, s, 100),
    "Daily 150-day": lambda c, s: trend_filter(c, s, 150),
    "Daily 250-day": lambda c, s: trend_filter(c, s, 250),
    "Monthly 8-month": lambda c, s: monthly_trend_filter(c, s, 8),
    "Monthly 12-month": lambda c, s: monthly_trend_filter(c, s, 12),
}


def _closes(dh: DataHandler, yahoo: str) -> pd.Series:
    df = dh.download_ohlcv(f"X_UK_EQ:{yahoo}", period="max", interval="1d", auto_adjust=True)
    ts = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    s = pd.Series(df["close"].to_numpy(dtype=float), index=ts)
    return s[~s.index.duplicated(keep="last")].sort_index()


def load_data(config: Config) -> Tuple[Dict[str, pd.Series], pd.Series]:
    dh = DataHandler(replace(config, timeframe="1d"))
    series = {d.key: _closes(dh, d.yahoo) for d in DATASETS}
    tbill = (_closes(dh, "^IRX").clip(0, 25) / 100.0)
    return series, tbill


def window_stats(equity: pd.Series, start: str, end: str) -> Optional[Tuple[float, float]]:
    """(worst fall within the window, return over the window) in percent."""
    w = equity[(equity.index >= pd.Timestamp(start)) & (equity.index <= pd.Timestamp(end))]
    if len(w) < 5:
        return None
    dd = float((w / w.cummax() - 1.0).min()) * 100.0
    ret = float(w.iloc[-1] / w.iloc[0] - 1.0) * 100.0
    return dd, ret


def run_dataset(px: pd.Series, tbill: pd.Series, key: str, cost: float) -> Dict[str, SimResult]:
    closes = px.to_frame(key).dropna()
    opens = closes.copy()  # trade at the next day's close (see module docstring)
    out = {}
    for name, build in {**VARIANTS, **ROBUSTNESS}.items():
        out[name] = simulate(name, build(closes, key), opens, closes, cost_per_side=cost, cash_rate=tbill)
    return out


def calendar_year_lag(strategy: pd.Series, bench: pd.Series) -> Tuple[int, int, float]:
    """(years the strategy trailed by >5 points, total years, worst yearly shortfall in points)."""
    s = strategy.groupby(strategy.index.year).apply(lambda x: x.iloc[-1] / x.iloc[0] - 1.0) * 100
    b = bench.groupby(bench.index.year).apply(lambda x: x.iloc[-1] / x.iloc[0] - 1.0) * 100
    diff = (s - b).dropna()
    return int((diff < -5).sum()), int(len(diff)), float(diff.min()) if len(diff) else 0.0


def build_report(config: Config, cost: float = 0.001) -> str:
    series, tbill = load_data(config)
    out = [
        "# Does a trend filter protect capital in crashes?",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M}. Rules fixed in advance, no tuning. Out of the market = "
        f"cash earning US 3-month T-bill rates (from 1960). Costs {cost * 100:.2f}% per trade side. "
        "Trades at the next day's close.",
    ]
    crash_rows: Dict[str, List[str]] = {}
    for d in DATASETS:
        px = series[d.key]
        res = run_dataset(px, tbill, d.key, cost)
        bench = res["Hold the index"]
        out += [
            "",
            f"## {d.name}: {px.index[0]:%Y} – {px.index[-1]:%Y}",
            "",
            d.note,
            "",
            "| | Yearly return | Worst drop | Sharpe | Invested | Switches/yr | Years trailing index by >5 pts | Worst year vs index |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for name, r in res.items():
            m = r.metrics()
            if name == "Hold the index":
                lag = "–"
                worst = "–"
            else:
                n_bad, n_years, worst_gap = calendar_year_lag(r.equity, bench.equity)
                lag, worst = f"{n_bad} of {n_years}", f"{worst_gap:+.0f} pts"
            label = name if name in VARIANTS else f"_{name}_"
            out.append(
                f"| {label} | {m['cagr_pct']:+.1f}% | {m['max_drawdown_pct']:.0f}% | {m['sharpe']:.2f} | "
                f"{m['time_in_market_pct']:.0f}% | {m['entries_per_year']:.1f} | {lag} | {worst} |"
            )
        for title, a, b in CRASHES + REBOUNDS:
            stats = {name: window_stats(res[name].equity, a, b) for name in VARIANTS}
            if any(v is None for v in stats.values()) or px.index[0] > pd.Timestamp(a):
                continue
            cells = " | ".join(f"{stats[n][0]:.0f}% / {stats[n][1]:+.0f}%" for n in VARIANTS)
            crash_rows.setdefault(title, []).append(f"| {title} | {d.name} | {cells} |")

    out += [
        "",
        "## Crash by crash",
        "",
        "Each cell: **worst fall during the window / return over the window**.",
        "",
        "| Period | Index | " + " | ".join(VARIANTS) + " |",
        "|---|---|" + "---|" * len(VARIANTS),
    ]
    for title, _, _ in CRASHES + REBOUNDS:
        out += crash_rows.get(title, [])
    out += [
        "",
        "Italic rows are robustness checks with nearby settings: a real effect should not depend on the exact number.",
    ]
    return "\n".join(out)
