"""Historical backtester for the screener + strategy + risk rules.

Replays historical bars through the same code the live bot uses
(`StockScreener.evaluate_dataframe`, `StrategyEngine`, `RiskManager`,
`classify_market_regime`, the session rules in `bot.market_calendar`) and
simulates fills, fees and portfolio limits.

What it does NOT model (read results with these in mind):
- The AI manager (Gemini veto and slot rotation): its answers cannot be replayed.
  `analyze.py ai` measures its effect on live decisions instead.
- The real order of prices inside a bar. Stops are assumed to be hit before
  targets when both are inside the same bar (pessimistic).
- Exchange-rate movement: one fixed rate is used for the whole run.
- Yahoo data gaps, delayed UK data, and partial fills.

Timing: bars are stamped with their open time. A bar's signal is acted on
after it closes, and the entry fills at the next bar's open plus slippage,
matching the live bot (which enters just after the close).
"""

from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from bot.config import Config
from bot.data_handler import DataHandler
from bot.market_calendar import (
    in_opening_window,
    in_pre_close_window,
    is_session_open,
    is_uk_symbol,
)
from bot.models import OrderBookSnapshot, Position, Side, SignalAction
from bot.risk_manager import RiskManager, has_open_slot, required_min_score
from bot.screener import StockScreener
from bot.strategy_engine import StrategyEngine, classify_market_regime

logger = logging.getLogger(__name__)

# yfinance only serves limited intraday history
MAX_DAYS_BY_INTERVAL = {"1m": 7, "2m": 59, "5m": 59, "15m": 59, "30m": 59, "60m": 729, "1h": 729, "1d": 3650}


# -----------------------------------------------------------------------------
# Data loading
# -----------------------------------------------------------------------------
def load_history(
    config: Config,
    symbols: List[str],
    days: int,
    interval: str,
    cache_dir: Optional[Path] = Path("logs/backtest_cache"),
    refresh: bool = False,
    workers: int = 6,
    auto_adjust: bool = False,
) -> Dict[str, pd.DataFrame]:
    """Download (or load cached) OHLCV bars keyed by Trading 212 symbol.

    The still-forming last bar is dropped. Cache files are named by date, so a
    re-run on the same day reuses them.
    """
    dh = DataHandler(config)
    tf_sec = dh.timeframe_to_seconds(interval)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")

    def _one(raw: str) -> Tuple[str, Optional[pd.DataFrame]]:
        t212, _ = dh.resolve_ticker_pair(raw)
        tag = "_adj" if auto_adjust else ""
        cache_file = cache_dir / f"{t212}_{interval}_{days}d{tag}_{today}.csv" if cache_dir else None
        try:
            if cache_file is not None and cache_file.exists() and not refresh:
                df = pd.read_csv(cache_file)
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            else:
                df = dh.download_ohlcv(raw, period=f"{days}d", interval=interval, auto_adjust=auto_adjust)
                if cache_file is not None:
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    df.to_csv(cache_file, index=False)
            now = datetime.now(timezone.utc)
            if len(df) and (now - df["timestamp"].iloc[-1].to_pydatetime()).total_seconds() < tf_sec:
                df = df.iloc[:-1]
            return t212, df.reset_index(drop=True)
        except Exception as exc:
            logger.warning("[%s] No history: %s", t212, exc)
            return t212, None

    out: Dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for t212, df in pool.map(_one, symbols):
            if df is not None and len(df) > 0:
                out[t212] = df
    return out


# -----------------------------------------------------------------------------
# Single-trade replay (also used by analyze.py)
# -----------------------------------------------------------------------------
def simulate_bracket(
    bars: pd.DataFrame,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    max_bars: int = 26,
) -> Dict[str, Any]:
    """Replay a simple stop/target bracket over `bars` (the bars after entry).

    Stops are checked before targets inside a bar. If neither is hit within
    `max_bars`, the trade exits at the last close. Returns exit price, R multiple,
    bars held and outcome ('stop' | 'target' | 'timeout' | 'no_data').
    """
    one_r = abs(entry_price - stop_loss)
    if one_r <= 0 or bars is None or len(bars) == 0:
        return {"exit_price": entry_price, "r_multiple": 0.0, "bars_held": 0, "outcome": "no_data"}
    for n, (_, bar) in enumerate(bars.head(max_bars).iterrows(), start=1):
        o, h, low = float(bar["open"]), float(bar["high"]), float(bar["low"])
        if o <= stop_loss:
            return {"exit_price": o, "r_multiple": (o - entry_price) / one_r, "bars_held": n, "outcome": "stop"}
        if low <= stop_loss:
            return {"exit_price": stop_loss, "r_multiple": (stop_loss - entry_price) / one_r, "bars_held": n, "outcome": "stop"}
        if h >= take_profit:
            px = max(o, take_profit)
            return {"exit_price": px, "r_multiple": (px - entry_price) / one_r, "bars_held": n, "outcome": "target"}
    last = bars.head(max_bars).iloc[-1]
    px = float(last["close"])
    return {"exit_price": px, "r_multiple": (px - entry_price) / one_r, "bars_held": min(len(bars), max_bars), "outcome": "timeout"}


# -----------------------------------------------------------------------------
# Portfolio backtest
# -----------------------------------------------------------------------------
@dataclass
class BacktestTrade:
    symbol: str
    market: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    quantity: float
    r_multiple: float
    gross_pnl: float
    fees: float
    net_pnl: float
    reason: str
    score: float
    bars_held: int
    regime: str


@dataclass
class BacktestResult:
    trades: List[BacktestTrade]
    equity_curve: List[Tuple[datetime, float]]
    starting_equity: float
    start: Optional[datetime]
    end: Optional[datetime]
    account_currency: str
    benchmark_return_pct: Optional[float] = None
    notes: List[str] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        trades = self.trades
        n = len(trades)
        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]
        gross_win = sum(t.net_pnl for t in wins)
        gross_loss = -sum(t.net_pnl for t in losses)
        net = sum(t.net_pnl for t in trades)
        end_equity = self.equity_curve[-1][1] if self.equity_curve else self.starting_equity

        peak, max_dd = -math.inf, 0.0
        for _, eq in self.equity_curve:
            peak = max(peak, eq)
            if peak > 0:
                max_dd = max(max_dd, (peak - eq) / peak)

        days = max(1.0, ((self.end - self.start).total_seconds() / 86400.0)) if self.start and self.end else 1.0
        return {
            "trades": n,
            "win_rate_pct": round(len(wins) / n * 100.0, 1) if n else 0.0,
            "avg_r": round(sum(t.r_multiple for t in trades) / n, 3) if n else 0.0,
            "expectancy": round(net / n, 2) if n else 0.0,
            "avg_win": round(gross_win / len(wins), 2) if wins else 0.0,
            "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0.0,
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else (math.inf if gross_win > 0 else 0.0),
            "net_pnl": round(net, 2),
            "fees": round(sum(t.fees for t in trades), 2),
            "return_pct": round((end_equity / self.starting_equity - 1.0) * 100.0, 2) if self.starting_equity else 0.0,
            "max_drawdown_pct": round(max_dd * 100.0, 2),
            "trades_per_day": round(n / days, 2),
            "avg_bars_held": round(sum(t.bars_held for t in trades) / n, 1) if n else 0.0,
            "benchmark_return_pct": self.benchmark_return_pct,
        }

    def breakdown(self, key: Callable[[BacktestTrade], str]) -> List[Tuple[str, int, float, float, float]]:
        """Rows of `(group, trades, win_rate_pct, avg_r, net_pnl)`."""
        groups: Dict[str, List[BacktestTrade]] = {}
        for t in self.trades:
            groups.setdefault(key(t), []).append(t)
        rows = []
        for name, ts in sorted(groups.items()):
            rows.append((
                name,
                len(ts),
                round(sum(1 for t in ts if t.net_pnl > 0) / len(ts) * 100.0, 1),
                round(sum(t.r_multiple for t in ts) / len(ts), 3),
                round(sum(t.net_pnl for t in ts), 2),
            ))
        return rows

    def format_report(self) -> str:
        s = self.summary()
        c = self.account_currency
        span = f"{self.start:%Y-%m-%d} to {self.end:%Y-%m-%d}" if self.start and self.end else "n/a"
        pf = "inf" if s["profit_factor"] == math.inf else f"{s['profit_factor']:.2f}"
        lines = [
            "",
            "=" * 72,
            f"  BACKTEST RESULTS  ({span})",
            "=" * 72,
            f"  Trades            {s['trades']}  ({s['trades_per_day']}/day, avg {s['avg_bars_held']} bars held)",
            f"  Win rate          {s['win_rate_pct']}%",
            f"  Avg R per trade   {s['avg_r']:+.3f}R",
            f"  Expectancy        {s['expectancy']:+.2f} {c} per trade (avg win {s['avg_win']:+.2f}, avg loss {s['avg_loss']:+.2f})",
            f"  Profit factor     {pf}",
            f"  Net P&L           {s['net_pnl']:+.2f} {c} after {s['fees']:.2f} {c} fees",
            f"  Return            {s['return_pct']:+.2f}% on {self.starting_equity:,.0f} {c}",
            f"  Max drawdown      {s['max_drawdown_pct']:.2f}%",
        ]
        if s["benchmark_return_pct"] is not None:
            lines.append(f"  Benchmark (hold)  {s['benchmark_return_pct']:+.2f}% over the same period")

        def _table(title: str, rows: List[Tuple[str, int, float, float, float]]) -> None:
            if not rows:
                return
            lines.append("")
            lines.append(f"  {title:<26} {'trades':>7} {'win%':>7} {'avg R':>8} {'net ' + c:>10}")
            for name, n, wr, ar, net in rows:
                lines.append(f"  {name[:26]:<26} {n:>7} {wr:>7.1f} {ar:>+8.3f} {net:>+10.2f}")

        _table("By market", self.breakdown(lambda t: t.market))
        _table("By exit reason", self.breakdown(lambda t: t.reason.split(" (")[0].split(":")[0]))
        _table("By entry score", self.breakdown(_score_bucket))
        _table("By market regime", self.breakdown(lambda t: t.regime))
        if self.notes:
            lines.append("")
            lines.extend(f"  Note: {n}" for n in self.notes)
        lines.append("=" * 72)
        return "\n".join(lines)


def _score_bucket(t: BacktestTrade) -> str:
    for lo in (90, 85, 80, 76, 70):
        if t.score >= lo:
            return f"score {lo}+"
    return "score <70"


@dataclass
class _Pending:
    symbol: str
    quantity: float
    atr: float
    score: float
    regime: str
    decided_at: datetime


class Backtester:
    """Portfolio-level replay of the live entry/exit rules over historical bars."""

    def __init__(
        self,
        config: Config,
        fx_rates: Optional[Dict[str, float]] = None,
        slippage_pct: float = 0.05,
        starting_equity: Optional[float] = None,
    ) -> None:
        # Paper mode with the default state path keeps RiskManager from writing files.
        self.config = replace(
            config,
            execution_mode="paper",
            state_file="logs/t212_state.json",
            enable_ai_manager=False,
        )
        self.fx_rates = {k.upper(): v for k, v in (fx_rates or {}).items()}
        self.slippage = slippage_pct / 100.0
        self.starting_equity = float(starting_equity or config.paper_initial_equity)
        self.data_handler = DataHandler(self.config)
        self.strategy = StrategyEngine(self.config)
        self.screener = StockScreener(self.config, self.data_handler, self.strategy)
        self.tf = timedelta(seconds=self.data_handler.timeframe_to_seconds())

    def _fx(self, symbol: str) -> float:
        ccy = "GBP" if is_uk_symbol(symbol) else "USD"
        if ccy == self.config.account_currency:
            return 1.0
        return self.fx_rates.get(ccy, 1.0)

    def _fee_rate(self, symbol: str) -> float:
        return 0.0 if is_uk_symbol(symbol) else self.config.fx_fee_rate

    def run(
        self,
        data: Dict[str, pd.DataFrame],
        benchmark: Optional[pd.DataFrame] = None,
        progress: Optional[Callable[[int, int], None]] = None,
        trade_from: Optional[datetime] = None,
        trade_until: Optional[datetime] = None,
    ) -> BacktestResult:
        """Replay `data`. Earlier bars still warm up indicators, but trading and the
        reported results are limited to `trade_from`..`trade_until` (UTC) when given.
        """
        cfg = self.config
        risk = RiskManager(cfg, self.strategy)
        warmup = cfg.ema_slow_period + 10

        frames: Dict[str, pd.DataFrame] = {}
        index_of: Dict[str, Dict[pd.Timestamp, int]] = {}
        next_day_change: Dict[str, List[bool]] = {}
        for sym, raw in data.items():
            if len(raw) <= warmup + 2:
                continue
            df = self.data_handler.compute_indicators(raw.reset_index(drop=True))
            frames[sym] = df
            index_of[sym] = {ts: i for i, ts in enumerate(df["timestamp"])}
            # True where the next bar belongs to a different session day (last bar of the day)
            local_dates = [
                ts.tz_convert("Europe/London" if is_uk_symbol(sym) else "America/New_York").date()
                for ts in df["timestamp"]
            ]
            next_day_change[sym] = [
                i == len(local_dates) - 1 or local_dates[i + 1] != local_dates[i]
                for i in range(len(local_dates))
            ]

        bench_df = None
        bench_idx: Dict[pd.Timestamp, int] = {}
        if benchmark is not None and len(benchmark) > warmup:
            bench_df = self.data_handler.compute_indicators(benchmark.reset_index(drop=True))
            bench_idx = {ts: i for i, ts in enumerate(bench_df["timestamp"])}

        timeline = sorted({ts for df in frames.values() for ts in df["timestamp"]})
        notes: List[str] = []
        if not timeline:
            return BacktestResult([], [], self.starting_equity, None, None, cfg.account_currency, notes=["No data."])

        cash = self.starting_equity
        positions: Dict[str, Position] = {}
        pos_meta: Dict[str, Dict[str, Any]] = {}
        pending: Dict[str, _Pending] = {}
        last_close: Dict[str, float] = {}
        last_atr: Dict[str, float] = {}
        last_trend: Dict[str, bool] = {}
        cooldown_until: Dict[str, datetime] = {}
        trades: List[BacktestTrade] = []
        equity_curve: List[Tuple[datetime, float]] = []
        regime_state, min_score = "BULLISH", cfg.min_recommendation_score

        def close_position(sym: str, price: float, when: datetime, reason: str, bar_i: int) -> None:
            nonlocal cash
            pos = positions.pop(sym)
            meta = pos_meta.pop(sym)
            fx = self._fx(sym)
            proceeds = pos.quantity * price * fx
            exit_fee = proceeds * self._fee_rate(sym)
            cash += proceeds - exit_fee
            gross = pos.quantity * (price - pos.entry_price) * fx
            fees = pos.entry_fee_paid + exit_fee
            net = gross - fees
            trades.append(BacktestTrade(
                symbol=sym,
                market="UK" if is_uk_symbol(sym) else "US",
                entry_time=pos.opened_at,
                exit_time=when.isoformat(),
                entry_price=round(pos.entry_price, 4),
                exit_price=round(price, 4),
                quantity=round(pos.quantity, 6),
                r_multiple=round(pos.current_r_multiple(price), 3),
                gross_pnl=round(gross, 2),
                fees=round(fees, 2),
                net_pnl=round(net, 2),
                reason=reason,
                score=meta["score"],
                bars_held=bar_i - meta["entry_bar"] + 1,
                regime=meta["regime"],
            ))
            if net < 0 and cfg.cooldown_minutes_after_loss > 0:
                cooldown_until[sym] = when + timedelta(minutes=cfg.cooldown_minutes_after_loss)

        def equity_now() -> float:
            return cash + sum(p.quantity * last_close.get(s, p.entry_price) * self._fx(s) for s, p in positions.items())

        if trade_until is not None:
            timeline = [ts for ts in timeline if (ts + self.tf).to_pydatetime() <= trade_until]
        if trade_from is not None:
            start_ts = next((ts for ts in timeline if (ts + self.tf).to_pydatetime() >= trade_from), None)
        else:
            start_ts = timeline[0] if timeline else None
        if not timeline or start_ts is None:
            return BacktestResult([], [], self.starting_equity, None, None, cfg.account_currency, notes=["No data in range."])

        for step, ts in enumerate(timeline):
            bar_close_time = (ts + self.tf).to_pydatetime()
            if progress and step % 200 == 0:
                progress(step, len(timeline))
            in_window = ts >= start_ts

            if bench_df is not None and ts in bench_idx and bench_idx[ts] >= warmup:
                regime_state, _, min_score = (
                    classify_market_regime(bench_df.iloc[bench_idx[ts]], cfg.min_recommendation_score)
                    if cfg.market_regime_filter
                    else ("BULLISH", "", cfg.min_recommendation_score)
                )

            recs = []
            for sym, df in frames.items():
                i = index_of[sym].get(ts)
                if i is None:
                    continue
                bar = df.iloc[i]
                o, h, low, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])

                # 1. Pending entry fills at this bar's open
                pend = pending.pop(sym, None)
                if pend is not None:
                    fill = o * (1.0 + self.slippage)
                    fx = self._fx(sym)
                    cost = pend.quantity * fill * fx
                    fee = cost * self._fee_rate(sym)
                    if cost + fee <= cash and pend.quantity > 0:
                        cash -= cost + fee
                        sl, tp = self.strategy.compute_initial_stops(fill, pend.atr, Side.LONG)
                        positions[sym] = Position(
                            symbol=sym, side=Side.LONG, quantity=pend.quantity, entry_price=fill,
                            initial_stop_loss=sl, stop_loss=sl, take_profit=tp, atr_at_entry=pend.atr,
                            entry_order_id="backtest", opened_at=ts.isoformat(), entry_fee_paid=fee,
                            fx_rate_at_entry=fx,
                        )
                        pos_meta[sym] = {"score": pend.score, "regime": pend.regime, "entry_bar": i}

                # 2. Intra-bar stop / target management (stops before targets)
                pos = positions.get(sym)
                if pos is not None:
                    atr_ref = last_atr.get(sym) or pos.atr_at_entry
                    stop_eff = pos.stop_loss if pos.trailing_active else pos.stop_loss - cfg.intrabar_stop_buffer_atr * atr_ref
                    kind = "Trailing Stop-Loss" if pos.trailing_active else "Stop-Loss"
                    if o <= stop_eff:
                        close_position(sym, o * (1.0 - self.slippage), bar_close_time, f"{kind} (gap)", i)
                    elif low <= stop_eff:
                        close_position(sym, stop_eff * (1.0 - self.slippage), bar_close_time, kind, i)
                    else:
                        tp_before = pos.take_profit
                        action, _ = self.strategy.evaluate_position_exit_and_trail(
                            pos, current_price=h, current_atr=atr_ref,
                            is_candle_close=False, trend_strong=last_trend.get(sym),
                        )
                        if action == SignalAction.SELL:
                            px = max(o, tp_before) if h >= tp_before else h
                            close_position(sym, px * (1.0 - self.slippage), bar_close_time, "Take-Profit", i)

                last_close[sym] = c
                if i < warmup:
                    continue

                # 3. Score the closed bar (same code as the live screener)
                window = df.iloc[max(0, i - 30): i + 1]
                try:
                    rec = self.screener.evaluate_dataframe(
                        sym, window, open_position=positions.get(sym), include_chart=False
                    )
                except Exception:
                    continue
                last_atr[sym] = rec.atr
                last_trend[sym] = rec.trend_strong

                # 4. Candle-close exits: reversal signal, stop/target on close, end of day
                pos = positions.get(sym)
                if pos is not None:
                    if rec.signal.is_exit:
                        close_position(sym, c * (1.0 - self.slippage), bar_close_time, "Bearish crossover", i)
                    else:
                        action, reason = self.strategy.evaluate_position_exit_and_trail(
                            pos, current_price=c, current_atr=rec.atr,
                            is_candle_close=True, trend_strong=rec.trend_strong,
                        )
                        if action == SignalAction.SELL:
                            close_position(sym, c * (1.0 - self.slippage), bar_close_time,
                                           reason.split(" hit")[0] + " (close)", i)
                pos = positions.get(sym)
                if pos is not None and cfg.eod_flat_enabled and next_day_change[sym][i]:
                    if is_uk_symbol(sym) or pos.current_r_multiple(c) < cfg.eod_hold_min_r:
                        close_position(sym, c * (1.0 - self.slippage), bar_close_time, "End-of-day flat", i)

                recs.append(rec)

            # 5. Equity and circuit breaker
            eq = equity_now()
            if not in_window:
                continue
            equity_curve.append((bar_close_time, eq))
            risk.record_equity(eq, now=bar_close_time)
            if risk.circuit_breaker_tripped:
                for sym in list(positions):
                    close_position(sym, last_close[sym] * (1.0 - self.slippage), bar_close_time,
                                   "Circuit breaker flatten", index_of[sym].get(ts, 0))
                pending.clear()
                continue

            # 6. Entries decided at this bar's close, filled at the next open
            candidates = []
            for rec in recs:
                sym = rec.symbol
                if not rec.actionable or sym in positions or sym in pending:
                    continue
                if not is_session_open(sym, bar_close_time):
                    continue
                if in_opening_window(sym, bar_close_time, cfg.skip_opening_minutes):
                    continue
                if cfg.eod_flat_enabled and in_pre_close_window(sym, bar_close_time, cfg.eod_flat_minutes_before_close):
                    continue
                if sym in cooldown_until and bar_close_time < cooldown_until[sym]:
                    continue
                req = required_min_score(cfg, sym, regime_state, min_score)
                if rec.score < req:
                    continue
                candidates.append(rec)
            candidates.sort(key=lambda r: (r.actionable, r.score, r.roc_10_pct), reverse=True)

            for rec in candidates:
                held = list(positions) + list(pending)
                if not has_open_slot(cfg, rec.symbol, held):
                    continue
                reserved = sum(p.quantity * last_close.get(s, 0.0) * self._fx(s) for s, p in pending.items())
                ob = OrderBookSnapshot(symbol=rec.symbol, bid=rec.close_price, ask=rec.close_price, last=rec.close_price)
                plan = risk.validate_and_build_trade_plan(
                    signal=rec.signal,
                    order_book=ob,
                    total_equity=eq,
                    available_quote=max(0.0, cash - reserved),
                    open_positions_count=len(held),
                    now=bar_close_time,
                    fx_rate=self._fx(rec.symbol),
                )
                if plan is None:
                    continue
                pending[rec.symbol] = _Pending(
                    symbol=rec.symbol, quantity=plan.quantity, atr=rec.atr,
                    score=rec.score, regime=regime_state, decided_at=bar_close_time,
                )

        end_time = (timeline[-1] + self.tf).to_pydatetime()
        for sym in list(positions):
            close_position(sym, last_close[sym], end_time, "End of backtest", len(frames[sym]) - 1)
        if equity_curve:
            equity_curve.append((end_time, cash))

        bench_ret = None
        if benchmark is not None and len(benchmark) > 1:
            window = benchmark[(benchmark["timestamp"] >= start_ts) & (benchmark["timestamp"] <= timeline[-1])]
            if len(window) > 1:
                b0, b1 = float(window["close"].iloc[0]), float(window["close"].iloc[-1])
                bench_ret = round((b1 / b0 - 1.0) * 100.0, 2) if b0 > 0 else None

        notes.append("AI veto / slot rotation not simulated; fixed FX rate; stops assumed hit before targets within a bar.")
        return BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            starting_equity=self.starting_equity,
            start=start_ts.to_pydatetime(),
            end=end_time,
            account_currency=cfg.account_currency,
            benchmark_return_pct=bench_ret,
            notes=notes,
        )
