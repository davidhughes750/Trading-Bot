#!/usr/bin/env python3
"""Reports on the bot's own logs.

    python analyze.py scans     # does a higher screener score predict better returns?
    python analyze.py ai        # did AI-vetoed setups do worse than approved ones?
    python analyze.py journal   # real trade results, slippage and fill-price sources
    python analyze.py all

`scans` and `ai` download recent bars from Yahoo Finance to see what happened
after each logged decision, so they only cover roughly the last 59 days.
"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import replace
from pathlib import Path

from bot.analysis import run_named
from bot.config import Config
from bot.utils import read_jsonl


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("report", choices=["scans", "ai", "journal", "all"])
    p.add_argument("--env", default=None, help="Path to .env file")
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    os.environ.setdefault("EXECUTION_MODE", "paper")
    config = Config.from_env(args.env) if args.env else Config.from_env()
    config = replace(config, execution_mode="paper")
    logs_dir = Path(config.state_file).parent

    names = ["journal", "scans", "ai"] if args.report == "all" else [args.report]
    for name in names:
        print(run_named(name, config, lambda fname: read_jsonl(logs_dir / fname)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
