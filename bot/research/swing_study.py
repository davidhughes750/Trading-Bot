"""Do multi-day (swing) rules on daily bars beat simply holding the bot's US stocks?

Run after the intraday strategy was retired (it lost in backtests even with zero fees). The question: is there
a slower rule worth building into the bot instead?

Rules are fixed before running. One setting per family is chosen on the TUNE period (best Sharpe) and judged
on the later TEST period:
  Portfolio  5 slots of 20% each. Signals use a day's close; trades happen at the next day's open.
  Families   Dip buy: close above its 200-day average and 2-day RSI below a level; sell when the close is above
             its 5-day average, or after 10 days.
             Breakout: close at an N-day high while above the 200-day average; sell at an M-day low.
             Momentum rotation: each week hold the 5 stocks with the best return over a lookback, among those
             above their 200-day average. A second version holds cash while SPY is below its 200-day average.
  Costs      per trade side: 0.20% (0.15% Trading 212 FX fee plus slippage) and 0.05% (a US dollar balance).
  Benchmarks SPY buy-and-hold, and an equal-weight hold of the same stock list.

Known bias, which flatters every strategy here: the list is today's popular stocks, so it is made of past
winners (survivorship). The equal-weight hold of the same list carries the same bias, which makes it the fair
comparison. A rule that fails to beat it has shown no skill, however large its return looks next to SPY.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from bot.config import Config
from bot.research.gap_study import load_daily, scan_symbols
from bot.research.strategies import rsi

SLOTS = 5
TUNE = ("2012-01-01", "2019-12-31")
TEST = ("2020-01-01", "2099-12-31")
COSTS = {"0.20% a side (pound account: FX fee plus slippage)": 0.0020, "0.05% a side (US dollar balance)": 0.0005}
BENCHMARK = "SPY_US_EQ"

Trade = Tuple[pd.Timestamp, str, float, int]  # exit date, symbol, net return, days held


def simulate(
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    entry: pd.DataFrame,
    exit_: pd.DataFrame,
    rank: pd.DataFrame,
    cost: float,
    start: pd.Timestamp,
    end: pd.Timestamp,
    max_hold: Optional[int] = None,
    slots: int = SLOTS,
) -> Tuple[pd.Series, List[Trade]]:
    """Replay close-of-day signals, trading at the next open. Returns (equity from 1.0, closed trades).

    `entry` and `exit_` are true/false tables for each day's close; `rank` orders the entries (higher first).
    Sells happen before buys, each new position gets equity / slots (or the cash left), and each side pays `cost`.
    """
    dates = closes.index[(closes.index >= start) & (closes.index <= end)]
    row_of = {d: i for i, d in enumerate(closes.index)}
    cash, held, trades, equity = 1.0, {}, [], []
    for d in dates:
        i = row_of[d]
        if i == 0:
            equity.append(cash)
            continue
        prev = closes.index[i - 1]
        op, cl = opens.iloc[i], closes.iloc[i]
        for sym in list(held):
            qty, entry_px, age = held[sym]
            if not np.isfinite(op[sym]):
                continue
            if bool(exit_.at[prev, sym]) or (max_hold and age >= max_hold):
                px = op[sym] * (1.0 - cost)
                cash += qty * px
                trades.append((d, sym, px / entry_px - 1.0, age))
                del held[sym]
            else:
                held[sym] = (qty, entry_px, age + 1)
        free = slots - len(held)
        if free > 0:
            sig = entry.loc[prev]
            cands = [
                s for s in sig.index[sig.to_numpy(dtype=bool)]
                if s not in held and np.isfinite(op[s]) and np.isfinite(rank.at[prev, s])
            ]
            cands.sort(key=lambda s: rank.at[prev, s], reverse=True)
            equity_open = cash + sum(q * (op[s] if np.isfinite(op[s]) else e) for s, (q, e, _) in held.items())
            for sym in cands[:free]:
                spend = min(equity_open / slots, cash)
                if spend <= 0:
                    break
                px = op[sym] * (1.0 + cost)
                held[sym] = (spend / px, px, 0)
                cash -= spend
        equity.append(cash + sum(q * (cl[s] if np.isfinite(cl[s]) else e) for s, (q, e, _) in held.items()))
    return pd.Series(equity, index=dates), trades


def metrics(equity: pd.Series, trades: Optional[List[Trade]] = None) -> Dict[str, float]:
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    rets = equity.pct_change().dropna()
    out = {
        "cagr": float((equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0),
        "sharpe": float(rets.mean() / rets.std() * math.sqrt(252)) if rets.std() > 0 else 0.0,
        "max_dd": float((equity / equity.cummax() - 1.0).min()),
        "years": years,
    }
    if trades is not None:
        r = np.array([t[2] for t in trades]) if trades else np.array([0.0])
        out.update(trades=len(trades), win=float((r > 0).mean()), avg=float(r.mean()), median=float(np.median(r)))
    return out


def families(closes: pd.DataFrame, spy: pd.Series) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Each family's variants, as keyword arguments for `simulate`."""
    up = closes > closes.rolling(200, min_periods=200).mean()
    out: Dict[str, Dict[str, Dict[str, Any]]] = {}

    r2 = closes.apply(lambda col: rsi(col, 2))
    sma5 = closes.rolling(5).mean()
    out["Buy dips in an uptrend, sell the bounce"] = {
        f"2-day RSI under {x}": dict(entry=up & (r2 < x), exit_=closes > sma5, rank=-r2, max_hold=10)
        for x in (5, 10, 15)
    }

    roc20 = closes / closes.shift(20) - 1.0
    out["Buy new highs, sell new lows"] = {}
    for n, m in ((20, 10), (55, 20), (100, 20)):
        high = closes >= closes.rolling(n, min_periods=n).max()
        low = closes <= closes.rolling(m, min_periods=m).min()
        out["Buy new highs, sell new lows"][f"{n}-day high, {m}-day low"] = dict(entry=high & up, exit_=low, rank=roc20)

    week = pd.Series(closes.index.to_period("W"), index=closes.index)
    week_end = (week != week.shift(-1)).to_numpy()[:, None]
    spy_up = (spy > spy.rolling(200).mean()).reindex(closes.index).fillna(False).to_numpy(dtype=bool)[:, None]
    plain, filtered = {}, {}
    for lookback in (63, 126, 252):
        mom = (closes / closes.shift(lookback) - 1.0).where(up)
        top = mom.rank(axis=1, ascending=False) <= SLOTS
        name = f"{lookback}-day return"
        plain[name] = dict(entry=top & week_end, exit_=(~top) & week_end, rank=mom)
        filtered[name] = dict(entry=top & week_end & spy_up, exit_=((~top) & week_end) | ~spy_up, rank=mom)
    out["Hold the 5 strongest, re-pick weekly"] = plain
    out["Same, in cash while SPY is in a downtrend"] = filtered
    return out


def benchmarks(closes: pd.DataFrame, spy: pd.Series, start: str, end: str) -> Dict[str, pd.Series]:
    s = spy.loc[start:end].dropna()
    rets = closes.pct_change(fill_method=None).loc[start:end]
    return {
        "Hold SPY": s / s.iloc[0],
        "Hold every stock on the list equally": (1.0 + rets.mean(axis=1).fillna(0.0)).cumprod(),
    }


def _by_year(equity: pd.Series) -> Dict[int, float]:
    return {int(y): float(x.iloc[-1] / x.iloc[0] - 1.0) for y, x in equity.groupby(equity.index.year)}


def run_panel(opens: pd.DataFrame, closes: pd.DataFrame, spy: pd.Series) -> Dict[str, Any]:
    fams = families(closes, spy)
    t0, t1 = pd.Timestamp(TUNE[0]), pd.Timestamp(TUNE[1])
    s0, s1 = pd.Timestamp(TEST[0]), min(pd.Timestamp(TEST[1]), closes.index[-1])
    res: Dict[str, Any] = {
        "n_symbols": closes.shape[1],
        "span": (closes.index[0], closes.index[-1]),
        "listed_at_tune_start": int(closes.loc[TUNE[0]:].iloc[:5].notna().any().sum()),
        "listed_at_test_start": int(closes.loc[TEST[0]:].iloc[:5].notna().any().sum()),
        "bench": {}, "rows": {},
    }
    for label, (a, b) in (("tune", TUNE), ("test", TEST)):
        res["bench"][label] = {k: (metrics(v), _by_year(v)) for k, v in benchmarks(closes, spy, a, b).items()}
    for cost_label, cost in COSTS.items():
        rows = []
        for fam, variants in fams.items():
            tuned = {
                name: metrics(*simulate(opens, closes, cost=cost, start=t0, end=t1, **kw))
                for name, kw in variants.items()
            }
            best = max(tuned, key=lambda n: tuned[n]["sharpe"])
            eq, trades = simulate(opens, closes, cost=cost, start=s0, end=s1, **variants[best])
            rows.append({"family": fam, "setting": best, "tune": tuned[best], "test": metrics(eq, trades), "by_year": _by_year(eq)})
        res["rows"][cost_label] = rows
    return res


def run(config: Config, refresh: bool = False) -> Dict[str, Any]:
    data = load_daily(config, scan_symbols(config), refresh=refresh)
    spy = data.pop(BENCHMARK)["close"]
    opens = pd.DataFrame({s: d["open"] for s, d in data.items()}).sort_index().loc["2010-01-01":]
    closes = pd.DataFrame({s: d["close"] for s, d in data.items()}).sort_index().loc["2010-01-01":]
    return run_panel(opens, closes, spy)


def _pct(v: float, digits: int = 1) -> str:
    return f"{v * 100:+.{digits}f}%"


def format_report(res: Dict[str, Any]) -> str:
    a, b = res["span"]
    lines = [
        "# Swing study: do multi-day rules beat holding the bot's US stocks?", "",
        f"Stocks: {res['n_symbols']} (the bot's US scan list, as it stands today), {a:%Y-%m-%d} to {b:%Y-%m-%d}. "
        f"{res['listed_at_tune_start']} were listed at the start of the tune period and "
        f"{res['listed_at_test_start']} at the start of the test period.",
        f"Tune {TUNE[0]} to {TUNE[1]}; test {TEST[0]} onwards. {SLOTS} slots; signals at the close, trades at the next open.", "",
        "Survivorship bias flatters every strategy: the list is today's winners. Compare each one with the "
        "equal-weight hold of the same list, which carries the same bias, and not with SPY.", "",
        "## Benchmarks", "", "| Benchmark | Period | Return a year | Sharpe | Worst fall |", "|---|---|---|---|---|",
    ]
    for period in ("tune", "test"):
        for name, (m, _) in res["bench"][period].items():
            lines.append(f"| {name} | {period} | {_pct(m['cagr'])} | {m['sharpe']:.2f} | {_pct(m['max_dd'], 0)} |")
    for cost_label, rows in res["rows"].items():
        lines += [
            "", f"## Costs: {cost_label}", "",
            "| Strategy | Setting chosen on tune | Tune return a year | Test return a year | Test Sharpe | Test worst fall | Trades (a year) | Win rate | Average trade | Median trade |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in rows:
            t = r["test"]
            lines.append(
                f"| {r['family']} | {r['setting']} | {_pct(r['tune']['cagr'])} | {_pct(t['cagr'])} | {t['sharpe']:.2f} | "
                f"{_pct(t['max_dd'], 0)} | {t['trades']} ({t['trades'] / t['years']:.0f}) | {t['win'] * 100:.0f}% | "
                f"{_pct(t['avg'], 2)} | {_pct(t['median'], 2)} |"
            )
        lines += ["", "Test period by year:", ""]
        for r in rows:
            lines.append(f"- {r['family']}: " + ", ".join(f"{y} {_pct(v, 0)}" for y, v in r["by_year"].items()))
    lines += ["", "Benchmarks by year (test period):", ""]
    for name, (_, years) in res["bench"]["test"].items():
        lines.append(f"- {name}: " + ", ".join(f"{y} {_pct(v, 0)}" for y, v in years.items()))
    return "\n".join(lines) + "\n"
