#!/usr/bin/env python3
"""Backtest the bot's screener, entry and exit rules on historical Yahoo Finance bars.

Examples:
    python backtest.py                         # last 59 days of 15m bars, full universe
    python backtest.py --symbols NVDA_US_EQ,TSLA_US_EQ --days 30
    python backtest.py --equity 500 --min-score 80
    python backtest.py --timeframe 1h --days 365   # longer history (different bar size)
    python backtest.py --set INTRABAR_STOP_BUFFER_ATR=0 --set MIN_TARGET_MOVE_PCT_FX=2.5
    python backtest.py --timeframe 1h --from 2025-11-01 --until 2026-05-01   # tune on one period...
    python backtest.py --timeframe 1h --from 2026-05-01                      # ...check on another

Strategy settings come from your .env, so a backtest reflects what the live bot
would do. Command-line options override them for the run only.
Trades are written to logs/backtest_trades.csv.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from bot.backtest import MAX_DAYS_BY_INTERVAL, Backtester, load_history
from bot.config import Config
from bot.data_handler import DataHandler
from bot.fx import FxConverter, FxUnavailableError
from bot.screener import StockScreener
from bot.strategy_engine import StrategyEngine


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env", default=None, help="Path to .env file")
    p.add_argument("--days", type=int, default=None, help="Days of history (default: max for the timeframe)")
    p.add_argument("--timeframe", default=None, help="Bar size, e.g. 15m or 1h (default: TIMEFRAME)")
    p.add_argument("--symbols", default=None, help="Comma-separated Trading 212 symbols (default: scan universe)")
    p.add_argument("--equity", type=float, default=None, help="Starting equity in account currency (default: PAPER_INITIAL_EQUITY)")
    p.add_argument("--min-score", type=float, default=None, help="Override MIN_RECOMMENDATION_SCORE")
    p.add_argument("--slippage-pct", type=float, default=0.05, help="Slippage per fill in percent (default 0.05)")
    p.add_argument("--fx", type=float, default=None, help="Account currency per USD (default: today's rate)")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                   help="Override any setting for this run, using its .env name (repeatable)")
    p.add_argument("--from", dest="date_from", default=None, help="Only trade from this date (YYYY-MM-DD, UTC)")
    p.add_argument("--until", dest="date_until", default=None, help="Only trade until this date (YYYY-MM-DD, UTC)")
    p.add_argument("--refresh", action="store_true", help="Ignore cached downloads")
    p.add_argument("--out", default="logs/backtest_trades.csv", help="CSV file for the trade list")
    return p.parse_args()


def _parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def apply_overrides(config: Config, pairs: list) -> Config:
    """Apply KEY=VALUE overrides (KEY as in .env, e.g. MIN_RECOMMENDATION_SCORE=85)."""
    changes = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--set expects KEY=VALUE, got '{pair}'")
        key, raw = pair.split("=", 1)
        name = key.strip().lower()
        if not hasattr(config, name):
            raise ValueError(f"Unknown setting '{key}'")
        current = getattr(config, name)
        if isinstance(current, bool):
            value = raw.strip().lower() in {"1", "true", "yes", "y", "on"}
        elif isinstance(current, int):
            value = int(raw)
        elif isinstance(current, float):
            value = float(raw)
        elif isinstance(current, list):
            value = [v.strip() for v in raw.split(",") if v.strip()]
        else:
            value = raw.strip()
        changes[name] = value
    return replace(config, **changes)


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    # Backtests never need broker credentials
    import os
    os.environ.setdefault("EXECUTION_MODE", "paper")
    config = Config.from_env(args.env) if args.env else Config.from_env()
    config = replace(config, execution_mode="paper")
    if args.timeframe:
        config = replace(config, timeframe=args.timeframe)
    if args.min_score is not None:
        config = replace(config, min_recommendation_score=args.min_score)
    try:
        config = apply_overrides(config, args.set)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    interval = config.timeframe.lower()
    max_days = MAX_DAYS_BY_INTERVAL.get(interval, 59)
    days = min(args.days or max_days, max_days)

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        dh = DataHandler(config)
        symbols = StockScreener(config, dh, StrategyEngine(config)).get_scan_universe()

    fx_usd = args.fx
    if fx_usd is None and config.account_currency != "USD":
        try:
            fx_usd = FxConverter(config).rate("USD")
        except FxUnavailableError as exc:
            print(f"Could not fetch an exchange rate ({exc}); pass --fx.", file=sys.stderr)
            return 1
    fx_rates = {"USD": fx_usd or 1.0}

    print(f"Downloading {days} days of {interval} bars for {len(symbols)} symbols (cached in logs/backtest_cache)...")
    data = load_history(config, symbols, days, interval, refresh=args.refresh)
    bench = load_history(config, [config.market_benchmark_symbol], days, interval, refresh=args.refresh)
    benchmark = next(iter(bench.values()), None)
    print(f"Loaded {len(data)} symbols. Replaying...")

    bt = Backtester(config, fx_rates=fx_rates, slippage_pct=args.slippage_pct, starting_equity=args.equity)

    def progress(i: int, n: int) -> None:
        print(f"\r  {i / max(1, n) * 100:5.1f}%", end="", flush=True)

    result = bt.run(
        data,
        benchmark=benchmark,
        progress=progress,
        trade_from=_parse_date(args.date_from),
        trade_until=_parse_date(args.date_until),
    )
    print("\r", end="")
    print(result.format_report())
    print(f"  USD->{config.account_currency} rate used: {fx_rates['USD']:.4f} | slippage {args.slippage_pct}% per fill")
    if args.set:
        print(f"  Overrides: {', '.join(args.set)}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        rows = [asdict(t) for t in result.trades]
        if rows:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    print(f"  Trade list: {out}")
    if len(result.trades) < 30:
        print("  Fewer than 30 trades: too few to judge the strategy. Try more symbols or a longer period.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
