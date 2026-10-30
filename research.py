#!/usr/bin/env python3
"""Test daily strategies on ~10 years of pound-priced ETF data, against buy-and-hold.

    python research.py                       # default periods, 0.10% cost per trade side
    python research.py --cost-pct 0.2        # harsher cost assumption
    python research.py --cash-rate 3         # assume cash earns 3% a year

Settings are chosen on a TUNE period and then judged on a later TEST period.
The report is printed and saved to logs/research_report.md.
"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import replace
from pathlib import Path

import pandas as pd

from bot.backtest import load_history
from bot.config import Config
from bot.research.engine import build_panel
from bot.research.runner import ASSETS, Period, format_report, run_walk_forward


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tune", default="2017-11-01:2021-12-31", help="Tune period START:END")
    p.add_argument("--test", default="2022-01-01:2099-12-31", help="Test period START:END")
    p.add_argument("--cost-pct", type=float, default=0.10, help="Cost per trade side in percent (spread + slippage)")
    p.add_argument("--cash-rate", type=float, default=0.0, help="Yearly interest on uninvested cash, in percent")
    p.add_argument("--refresh", action="store_true", help="Ignore cached downloads")
    p.add_argument("--out", default="logs/research_report.md")
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    os.environ.setdefault("EXECUTION_MODE", "paper")
    config = replace(Config.from_env(), execution_mode="paper", timeframe="1d")

    print(f"Downloading ~10 years of daily data for {len(ASSETS)} ETFs (cached in logs/backtest_cache)...")
    raw = load_history(
        config,
        [f"{key}_UK_EQ:{yf}" for key, (yf, _) in ASSETS.items()],
        days=3650,
        interval="1d",
        refresh=args.refresh,
        auto_adjust=True,
    )
    data = {k.replace("_UK_EQ", ""): v for k, v in raw.items()}
    missing = set(ASSETS) - set(data)
    if missing:
        print(f"Warning: no data for {', '.join(sorted(missing))}")
    opens, closes = build_panel(data)
    print(f"{len(closes)} trading days, {closes.index[0]:%Y-%m-%d} to {closes.index[-1]:%Y-%m-%d}")

    def period(name: str, spec: str) -> Period:
        a, b = spec.split(":")
        start = max(pd.Timestamp(a), closes.index[0])
        end = min(pd.Timestamp(b), closes.index[-1])
        return Period(name, start, end)

    tune, test = period("tune", args.tune), period("test", args.test)
    results, benchmarks = run_walk_forward(
        opens,
        closes,
        tune,
        test,
        cost_per_side=args.cost_pct / 100.0,
        cash_rate=args.cash_rate / 100.0,
        progress=lambda msg: print(f"  running {msg}"),
    )
    report = format_report(results, benchmarks, tune, test, args.cost_pct / 100.0, args.cash_rate / 100.0)
    print()
    print(report)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"\nSaved to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
