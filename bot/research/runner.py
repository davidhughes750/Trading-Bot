"""Walk-forward comparison of daily strategies against buy-and-hold.

For each strategy family, every parameter combination is run on a TUNE period;
the combination with the best Sharpe ratio there is then judged on a later TEST
period it has never seen. Results are compared with simply holding the index.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

from bot.research.engine import SimResult, simulate
from bot.research.strategies import buy_and_hold, dip_buy, momentum_rotation, trend_filter

# Pound-priced ETFs on the London Stock Exchange (no Trading 212 FX fee).
# Key -> (Yahoo symbol, description)
ASSETS: Dict[str, Tuple[str, str]] = {
    "VUSA": ("VUSA.L", "S&P 500"),
    "EQQQ": ("EQQQ.L", "Nasdaq-100"),
    "VUKE": ("VUKE.L", "FTSE 100"),
    "VMID": ("VMID.L", "FTSE 250"),
    "VEUR": ("VEUR.L", "Developed Europe"),
    "VJPN": ("VJPN.L", "Japan"),
    "VFEM": ("VFEM.L", "Emerging markets"),
    "SGLN": ("SGLN.L", "Gold"),
    "IGLT": ("IGLT.L", "UK gilts"),
}
SAFE = "IGLT"


@dataclass
class Period:
    name: str
    start: pd.Timestamp
    end: pd.Timestamp


@dataclass
class FamilyResult:
    family: str
    description: str
    chosen: Dict[str, object]
    tune: Dict[str, float]
    test: Dict[str, float]
    benchmark_name: str
    benchmark_tune: Dict[str, float]
    benchmark_test: Dict[str, float]
    share_beating_benchmark_in_test: float  # fraction of ALL parameter sets beating the benchmark's test Sharpe
    n_variants: int
    top_tune: List[Tuple[Dict[str, object], Dict[str, float], Dict[str, float]]]


def _grid(**axes) -> List[Dict[str, object]]:
    keys = list(axes)
    return [dict(zip(keys, combo)) for combo in itertools.product(*axes.values())]


def families(closes: pd.DataFrame) -> Dict[str, Tuple[str, Callable[[Dict[str, object]], pd.DataFrame], List[Dict[str, object]], Callable[[Dict[str, object]], str]]]:
    """name -> (description, weights builder, parameter grid, benchmark symbol for a param set)."""
    rotation_universe = [k for k in ASSETS if k in closes.columns]
    return {
        "Trend filter": (
            "Hold an index ETF while it is above its N-day average, otherwise cash or gilts.",
            lambda p: trend_filter(closes, p["symbol"], p["sma_days"], p["safe"]),
            _grid(symbol=["VUSA", "EQQQ", "VUKE"], sma_days=[50, 100, 150, 200], safe=[None, SAFE]),
            lambda p: p["symbol"],
        ),
        "Momentum rotation": (
            "Each month, hold the top N of 9 ETFs by past return (only if that return is positive).",
            lambda p: momentum_rotation(
                closes,
                [s for s in rotation_universe if not (p["safe"] and s == p["safe"])],
                p["lookback_days"],
                p["top_n"],
                p["safe"],
            ),
            _grid(lookback_days=[63, 126, 252], top_n=[1, 2, 3], safe=[None, SAFE]),
            lambda p: "VUSA",
        ),
        "Dip buying": (
            "Buy an index ETF after a sharp 2-day drop while above its 200-day average; sell on the bounce.",
            lambda p: dip_buy(closes, p["symbol"], entry_rsi=p["entry_rsi"], max_hold_days=p["max_hold_days"]),
            _grid(symbol=["VUSA", "EQQQ"], entry_rsi=[5, 10, 15], max_hold_days=[5, 10]),
            lambda p: p["symbol"],
        ),
    }


def run_walk_forward(
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    tune: Period,
    test: Period,
    cost_per_side: float = 0.001,
    cash_rate: float = 0.0,
    progress: Optional[Callable[[str], None]] = None,
) -> Tuple[List[FamilyResult], Dict[str, Dict[str, Dict[str, float]]]]:
    def run(name: str, w: pd.DataFrame, period: Period, params: Dict[str, object]) -> SimResult:
        return simulate(name, w, opens, closes, cost_per_side, period.start, period.end, cash_rate, params)

    benchmarks: Dict[str, Dict[str, Dict[str, float]]] = {}
    for sym in ["VUSA", "EQQQ", "VUKE"]:
        if sym in closes.columns:
            w = buy_and_hold(closes, sym)
            benchmarks[sym] = {
                "tune": run(f"Hold {sym}", w, tune, {}).metrics(),
                "test": run(f"Hold {sym}", w, test, {}).metrics(),
            }

    results: List[FamilyResult] = []
    for fam, (desc, build, grid, bench_of) in families(closes).items():
        if progress:
            progress(f"{fam}: {len(grid)} variants")
        rows = []
        for params in grid:
            w = build(params)
            rows.append((params, run(fam, w, tune, params).metrics(), run(fam, w, test, params).metrics()))
        rows.sort(key=lambda r: r[1].get("sharpe", float("-inf")), reverse=True)
        best_params, best_tune, best_test = rows[0]
        bench = bench_of(best_params)
        beating = sum(
            1 for p, _, te in rows if te.get("sharpe", 0) > benchmarks[bench_of(p)]["test"].get("sharpe", 0)
        )
        results.append(FamilyResult(
            family=fam,
            description=desc,
            chosen=best_params,
            tune=best_tune,
            test=best_test,
            benchmark_name=f"Hold {bench} ({ASSETS[bench][1]})",
            benchmark_tune=benchmarks[bench]["tune"],
            benchmark_test=benchmarks[bench]["test"],
            share_beating_benchmark_in_test=beating / len(rows),
            n_variants=len(rows),
            top_tune=rows[:5],
        ))
    return results, benchmarks


def _fmt_params(p: Dict[str, object]) -> str:
    parts = []
    for k, v in p.items():
        if k == "safe":
            parts.append(f"else {'gilts' if v else 'cash'}")
        else:
            parts.append(f"{k}={v}")
    return ", ".join(parts)


def _row(label: str, m: Dict[str, float]) -> str:
    if not m:
        return f"| {label} | – | – | – | – | – | – |"
    return (
        f"| {label} | {m['cagr_pct']:+.1f}% | {m['total_return_pct']:+.0f}% | {m['max_drawdown_pct']:.0f}% | "
        f"{m['sharpe']:.2f} | {m['time_in_market_pct']:.0f}% | {m['entries_per_year']:.1f} |"
    )


def format_report(
    results: List[FamilyResult],
    benchmarks: Dict[str, Dict[str, Dict[str, float]]],
    tune: Period,
    test: Period,
    cost_per_side: float,
    cash_rate: float,
) -> str:
    header = "| | Yearly return | Total | Worst drop | Sharpe | Invested | Trades/yr |\n|---|---|---|---|---|---|---|"
    out = [
        "# Daily strategy research",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M}. Pound-priced London ETFs, dividend-adjusted prices.",
        f"Costs {cost_per_side * 100:.2f}% per trade side; cash earns {cash_rate * 100:.1f}% a year.",
        f"Settings were picked on the **tune period** ({tune.start:%b %Y} – {tune.end:%b %Y}) by best Sharpe ratio, "
        f"then judged on the **test period** ({test.start:%b %Y} – {test.end:%b %Y}), which they never saw.",
        "",
        "## Benchmarks: just holding the ETF",
        "",
        header,
    ]
    for sym, m in benchmarks.items():
        out.append(_row(f"Hold {sym} ({ASSETS[sym][1]}) – tune", m["tune"]))
        out.append(_row(f"Hold {sym} ({ASSETS[sym][1]}) – test", m["test"]))
    for r in results:
        out += [
            "",
            f"## {r.family}",
            "",
            r.description,
            "",
            f"Chosen on the tune period: **{_fmt_params(r.chosen)}** (best of {r.n_variants}).",
            "",
            header,
            _row("Strategy – tune", r.tune),
            _row(f"{r.benchmark_name} – tune", r.benchmark_tune),
            _row("**Strategy – test (unseen)**", r.test),
            _row(f"**{r.benchmark_name} – test**", r.benchmark_test),
            "",
            f"{r.share_beating_benchmark_in_test * 100:.0f}% of all {r.n_variants} variants beat their benchmark's "
            "Sharpe ratio in the test period (a robustness check: a real effect should not depend on one lucky setting).",
            "",
            "Top 5 on the tune period and how they then did:",
            "",
            "| Settings | Tune Sharpe | Test Sharpe | Test yearly | Test worst drop |",
            "|---|---|---|---|---|",
        ]
        for p, tu, te in r.top_tune:
            out.append(
                f"| {_fmt_params(p)} | {tu.get('sharpe', 0):.2f} | {te.get('sharpe', 0):.2f} | "
                f"{te.get('cagr_pct', 0):+.1f}% | {te.get('max_drawdown_pct', 0):.0f}% |"
            )
    out += [
        "",
        "## How to read this",
        "",
        "- **Sharpe** is return per unit of volatility. Higher is better; the benchmark's is the bar to clear.",
        "- **Worst drop** is the largest fall from a previous high.",
        "- A strategy is only interesting if its *test* results beat holding the index on Sharpe or worst "
        "drop without giving up too much return, and if many of its variants do so (not just the chosen one).",
        "- Limitations: one ten-year history, Yahoo data, costs are estimates, trades assumed at the next "
        "open, and cash interest is ignored unless set.",
    ]
    return "\n".join(out)
