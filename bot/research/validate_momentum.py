"""Out-of-sample check of 12-month momentum rotation.

The rule (hold the top 3 of a universe by 12-month return each month, only if that return is positive,
otherwise cash) was noticed AFTER looking at results on UK ETFs, so it has not been properly tested.
This runs it, with the rules fixed in advance, on a different universe and period:
ten US-listed ETFs across stocks, bonds, gold, commodities and property, Feb 2006 to today
(which includes 2008, 2020 and 2022).

Nothing is tuned here. A grid of neighbouring settings is shown to check the result does not depend on
one lucky number, and a bootstrap estimates how often a gap this size would appear by luck.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from bot.config import Config
from bot.data_handler import DataHandler
from bot.research.crash_test import load_tbill
from bot.research.engine import build_panel, compute_metrics, simulate
from bot.research.strategies import buy_and_hold, momentum_rotation

UNIVERSE = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "VNQ"]
DESCRIPTIONS = {
    "SPY": "US large caps", "QQQ": "Nasdaq-100", "IWM": "US small caps", "EFA": "Developed markets ex-US",
    "EEM": "Emerging markets", "TLT": "Long US Treasuries", "IEF": "Mid US Treasuries", "GLD": "Gold",
    "DBC": "Commodities", "VNQ": "US property",
}
# The rule exactly as first noticed. Fixed before this test was run.
RULE = {"lookback_days": 252, "top_n": 3}
GRID_LOOKBACKS = [126, 189, 252, 315]
GRID_TOP_N = [2, 3, 4]
ERAS = [("2007–2012", "2007-01-01", "2012-12-31"), ("2013–2019", "2013-01-01", "2019-12-31"), ("2020–today", "2020-01-01", "2099-12-31")]


@dataclass
class Row:
    name: str
    metrics: Dict[str, float]
    equity: pd.Series  # measured from the common start date, so every row covers the same days


def load_panel(config: Config, cache_dir: Path = Path("logs/backtest_cache"), refresh: bool = False) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Dividend-adjusted daily opens and closes for the universe on their common dates."""
    dh = DataHandler(config)
    today = datetime.now().strftime("%Y%m%d")
    data: Dict[str, pd.DataFrame] = {}
    cache_dir.mkdir(parents=True, exist_ok=True)
    for sym in UNIVERSE:
        cache = cache_dir / f"{sym}_1d_max_adj_{today}.csv"
        if cache.exists() and not refresh:
            df = pd.read_csv(cache)
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        else:
            df = dh.download_ohlcv(f"{sym}_US_EQ", period="max", interval="1d", auto_adjust=True)
            df.to_csv(cache, index=False)
        data[sym] = df
    return build_panel(data)


def annual_returns(equity: pd.Series) -> pd.Series:
    """Calendar-year returns (the first and last years may be partial)."""
    year_end = equity.groupby(equity.index.year).last()
    start = pd.concat([pd.Series([equity.iloc[0]]), year_end.iloc[:-1]]).to_numpy()
    return pd.Series(year_end.to_numpy() / start - 1.0, index=year_end.index)


def monthly_returns(equity: pd.Series) -> pd.Series:
    return equity.resample("ME").last().pct_change().dropna()


def _sharpe_monthly(r: np.ndarray) -> float:
    sd = r.std(ddof=1)
    return float(r.mean() / sd * math.sqrt(12)) if sd > 0 else 0.0


def bootstrap_difference(
    strategy: pd.Series, benchmark: pd.Series, block: int = 6, draws: int = 5000, seed: int = 7
) -> Dict[str, float]:
    """Circular block bootstrap of paired monthly returns.

    Resamples whole `block`-month stretches so that streaks (a bad year) stay together, and measures how
    the strategy's Sharpe ratio and yearly return compare with the benchmark's in each resample. The share
    of resamples where the strategy is ahead is a rough measure of how likely the edge is to be luck.
    """
    df = pd.concat([strategy, benchmark], axis=1, keys=["s", "b"]).dropna()
    s, b = df["s"].to_numpy(), df["b"].to_numpy()
    n = len(df)
    if n < block * 3:
        return {}
    rng = np.random.default_rng(seed)
    n_blocks = math.ceil(n / block)
    sharpe_diff, cagr_diff = [], []
    for _ in range(draws):
        starts = rng.integers(0, n, size=n_blocks)
        idx = ((starts[:, None] + np.arange(block)[None, :]) % n).ravel()[:n]
        rs, rb = s[idx], b[idx]
        sharpe_diff.append(_sharpe_monthly(rs) - _sharpe_monthly(rb))
        cagr_diff.append((np.prod(1 + rs) ** (12 / n) - 1) - (np.prod(1 + rb) ** (12 / n) - 1))
    sd, cd = np.array(sharpe_diff), np.array(cagr_diff)
    return {
        "months": n,
        "sharpe_diff_mean": float(sd.mean()),
        "sharpe_diff_lo": float(np.percentile(sd, 5)),
        "sharpe_diff_hi": float(np.percentile(sd, 95)),
        "prob_sharpe_ahead": float((sd > 0).mean()),
        "cagr_diff_mean": float(cd.mean()),
        "prob_cagr_ahead": float((cd > 0).mean()),
    }


def run(config: Config, cost_per_side: float = 0.001, refresh: bool = False) -> Dict[str, object]:
    opens, closes = load_panel(config, refresh=refresh)
    tbill = load_tbill(config)
    start = closes.index[0]

    # The slowest rule needs 315 trading days of history before it can hold anything. Everything is
    # measured from that date so the benchmarks do not get a head start.
    common_start = closes.index[max(GRID_LOOKBACKS)]

    def sim(name: str, weights: pd.DataFrame) -> Row:
        res = simulate(name, weights, opens, closes, cost_per_side=cost_per_side, cash_rate=tbill)
        eq = res.equity[res.equity.index >= common_start]
        held = res.held[res.held.index >= common_start]
        return Row(name, compute_metrics(eq, held), eq)

    rule = sim("Momentum: 12-month, top 3", momentum_rotation(closes, UNIVERSE, RULE["lookback_days"], RULE["top_n"], safe=None))
    spy = sim("Hold SPY (US stocks)", buy_and_hold(closes, "SPY"))
    sixty_forty = sim("60/40 SPY + IEF", pd.DataFrame({"SPY": 0.6, "IEF": 0.4}, index=closes.index))
    equal = sim("Equal weight, all 10", pd.DataFrame({s: 1.0 / len(UNIVERSE) for s in UNIVERSE}, index=closes.index))

    grid: List[Row] = []
    for lb in GRID_LOOKBACKS:
        for n in GRID_TOP_N:
            grid.append(sim(f"{lb}d, top {n}", momentum_rotation(closes, UNIVERSE, lb, n, safe=None)))

    # Compare all rows over the same dates (the rule needs ~a year of history before it can hold anything)
    first_held = common_start
    eras: List[Tuple[str, Dict[str, Dict[str, float]]]] = []
    for label, a, b in ERAS:
        window = {}
        for row in (rule, spy, sixty_forty, equal):
            eq = row.equity[(row.equity.index >= max(pd.Timestamp(a), common_start)) & (row.equity.index <= pd.Timestamp(b))]
            window[row.name] = compute_metrics(eq) if len(eq) > 60 else {}
        eras.append((label, window))

    yearly = pd.DataFrame({"rule": annual_returns(rule.equity), "spy": annual_returns(spy.equity)})
    boot = bootstrap_difference(monthly_returns(rule.equity), monthly_returns(spy.equity))
    boot_6040 = bootstrap_difference(monthly_returns(rule.equity), monthly_returns(sixty_forty.equity))
    return {
        "start": start, "end": closes.index[-1], "first_held": first_held, "cost": cost_per_side,
        "rows": [rule, spy, sixty_forty, equal], "grid": grid, "eras": eras, "yearly": yearly,
        "bootstrap_spy": boot, "bootstrap_6040": boot_6040,
    }


def _m(m: Dict[str, float], key: str, fmt: str) -> str:
    return fmt.format(m[key]) if m and key in m else "–"


def format_report(r: Dict[str, object]) -> str:
    rows: List[Row] = r["rows"]  # type: ignore[assignment]
    grid: List[Row] = r["grid"]  # type: ignore[assignment]
    yearly: pd.DataFrame = r["yearly"]  # type: ignore[assignment]
    out = [
        "# Does 12-month momentum hold up on data it was not found on?",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M}. Ten US-listed ETFs ({', '.join(UNIVERSE)}), "
        f"{r['start']:%b %Y} to {r['end']:%b %Y}, dividend-adjusted, trades at the next open, "
        f"{r['cost'] * 100:.2f}% cost per side, cash earns US T-bill rates.",
        "",
        "**Rule, fixed before testing:** each month-end hold the top 3 ETFs by 12-month (252-day) return, equally "
        "weighted, but only those with a positive return; the rest of the money sits in cash. "
        "The rule came out of a UK-ETF test, so this is a different universe, different dates and different currency.",
        "",
        "## Headline",
        "",
        "| | Yearly return | Volatility | Sharpe | Worst drop | Time invested |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        m = row.metrics
        out.append(
            f"| {'**' + row.name + '**' if row is rows[0] else row.name} | {_m(m, 'cagr_pct', '{:+.1f}%')} | {_m(m, 'volatility_pct', '{:.1f}%')} | "
            f"{_m(m, 'sharpe', '{:.2f}')} | {_m(m, 'max_drawdown_pct', '{:.0f}%')} | {_m(m, 'time_in_market_pct', '{:.0f}%')} |"
        )
    out += ["", f"Everything is measured from {r['first_held']:%b %Y}, the first date every setting in the grid below "
            "has enough history to act, so no row gets a head start.", ""]

    out += ["## By era", ""]
    for label, window in r["eras"]:  # type: ignore[assignment]
        out += [f"**{label}**", "", "| | Yearly return | Sharpe | Worst drop |", "|---|---|---|---|"]
        for row in rows:
            m = window.get(row.name, {})
            out.append(f"| {row.name} | {_m(m, 'cagr_pct', '{:+.1f}%')} | {_m(m, 'sharpe', '{:.2f}')} | {_m(m, 'max_drawdown_pct', '{:.0f}%')} |")
        out.append("")

    out += ["## Calendar years: rule vs holding SPY", "", "| Year | Rule | SPY | Difference |", "|---|---|---|---|"]
    for year, row in yearly.iterrows():
        out.append(f"| {year} | {row['rule'] * 100:+.1f}% | {row['spy'] * 100:+.1f}% | {(row['rule'] - row['spy']) * 100:+.1f} pts |")
    ahead = int((yearly["rule"] > yearly["spy"]).sum())
    out += ["", f"The rule beat SPY in {ahead} of {len(yearly)} calendar years. "
            f"Worst single year relative to SPY: {(yearly['rule'] - yearly['spy']).min() * 100:+.1f} points.", ""]

    out += ["## Neighbouring settings (nothing tuned)", "",
            "If the idea is real, nearby settings should behave similarly. If only one cell looks good, it was luck.",
            "", "| Setting | Yearly return | Sharpe | Worst drop |", "|---|---|---|---|"]
    for row in grid:
        m = row.metrics
        mark = "**" if row.name == "252d, top 3" else ""
        out.append(f"| {mark}{row.name}{mark} | {_m(m, 'cagr_pct', '{:+.1f}%')} | {_m(m, 'sharpe', '{:.2f}')} | {_m(m, 'max_drawdown_pct', '{:.0f}%')} |")
    spy_sharpe = rows[1].metrics.get("sharpe", 0)
    beating = sum(1 for g in grid if g.metrics.get("sharpe", 0) > spy_sharpe)
    out += ["", f"{beating} of {len(grid)} settings have a higher Sharpe ratio than holding SPY ({spy_sharpe:.2f}).", ""]

    for label, key in (("SPY", "bootstrap_spy"), ("a 60/40 portfolio", "bootstrap_6040")):
        b = r[key]  # type: ignore[assignment]
        if not b:
            continue
        out += [f"## Could the gap vs {label} be luck?", "",
                f"Resampling the {b['months']} monthly returns in 6-month blocks 5,000 times: the rule's Sharpe ratio "
                f"minus {label}'s averaged {b['sharpe_diff_mean']:+.2f} (90% range {b['sharpe_diff_lo']:+.2f} to {b['sharpe_diff_hi']:+.2f}). "
                f"The rule came out ahead on Sharpe in {b['prob_sharpe_ahead'] * 100:.0f}% of resamples and ahead on yearly return in "
                f"{b['prob_cagr_ahead'] * 100:.0f}%. Anything under about 90-95% is not convincing, "
                "and about 130 strategy variants have been tried on this project in total, which makes lucky winners likelier.", ""]

    out += ["## How to read this", "",
            "- **Sharpe** is return per unit of volatility; **worst drop** is the largest fall from a previous high.",
            "- A rule is only worth building into the bot if it holds up here as well as on the UK ETFs, in most eras and "
            "for neighbouring settings, and if it either earns more than holding SPY or protects clearly better.",
            "- Limits: one 20-year history, free Yahoo data, US-listed ETFs (a UK investor would hold London equivalents, "
            "with similar but not identical returns), and costs are estimates."]
    return "\n".join(out)
