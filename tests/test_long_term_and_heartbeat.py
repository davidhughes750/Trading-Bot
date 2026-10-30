"""Tests for permanent equity history, long-term journal stats and the heartbeat."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from bot.analysis import journal_performance
from bot.equity_history import EquityHistory, downsample, drawdown_stats, load_equity_history
from bot.heartbeat import Heartbeat


def test_equity_history_records_once_per_interval(tmp_path: Path):
    eh = EquityHistory(tmp_path / "equity_history.jsonl", interval_sec=300)
    t0 = datetime(2026, 10, 30, 14, 0, tzinfo=timezone.utc)
    assert eh.maybe_record(500.0, 400.0, now=t0)
    assert not eh.maybe_record(501.0, 400.0, now=t0 + timedelta(seconds=60))  # same 5-min bucket
    assert eh.maybe_record(502.0, 400.0, now=t0 + timedelta(minutes=5))
    assert [p["equity"] for p in load_equity_history(eh.path)] == [500.0, 502.0]


def test_seed_from_rotated_logs_in_order(tmp_path: Path):
    line = "{ts} | INFO     | trading212_bot       | Trading 212 Portfolio | Total Equity={c}{eq:.2f} | Free Cash={c}{eq:.2f} | Open Positions=0/4 | 24h DD=0.00%\n"
    (tmp_path / "trading_bot.log.2").write_text(line.format(ts="2026-10-20 10:00:00", c="$", eq=500))
    (tmp_path / "trading_bot.log.1").write_text(line.format(ts="2026-10-25 10:00:00", c="$", eq=480))
    (tmp_path / "trading_bot.log").write_text(
        line.format(ts="2026-10-30 10:00:00", c="£", eq=490) + line.format(ts="2026-10-30 10:00:30", c="£", eq=491)
    )
    eh = EquityHistory(tmp_path / "equity_history.jsonl")
    assert eh.seed_from_logs(tmp_path / "trading_bot.log") == 3  # two lines share a 5-min bucket
    assert [p["equity"] for p in load_equity_history(eh.path)] == [500.0, 480.0, 490.0]
    assert eh.seed_from_logs(tmp_path / "trading_bot.log") == 0  # only seeds once


def test_drawdown_stats_and_downsample():
    pts = [{"ts": f"2026-10-{d:02d}T00:00:00+00:00", "equity": e} for d, e in
           [(1, 100), (2, 120), (3, 90), (4, 110), (5, 108)]]
    st = drawdown_stats(pts)
    assert st["peak_equity"] == 120
    assert st["max_drawdown_pct"] == pytest.approx(25.0)
    assert st["current_drawdown_pct"] == pytest.approx(10.0)
    assert st["change_pct"] == pytest.approx(8.0)

    many = [{"ts": str(i), "equity": 100 + (i % 50)} for i in range(5000)]
    many[1234]["equity"] = 1  # trough must survive downsampling
    thin = downsample(many, 400)
    assert len(thin) <= 404 and thin[0] is many[0] and thin[-1] is many[-1]
    assert min(p["equity"] for p in thin) == 1


def test_journal_performance_totals_weeks_and_execution():
    recs = [
        {"closed_at": "2026-10-26T15:00:00+00:00", "symbol": "NVDA_US_EQ", "market": "US", "net_pnl": 10.0,
         "r_multiple": 1.5, "fee_paid": 0.5, "exit_slippage_pct": 0.02, "entry_slippage_pct": 0.01,
         "exit_price_source": "broker_fill", "currency": "GBP"},
        {"closed_at": "2026-10-27T15:00:00+00:00", "symbol": "QQQ3_UK_EQ", "market": "UK", "net_pnl": -4.0,
         "r_multiple": -1.0, "fee_paid": 0.0, "currency": "GBP"},
        {"closed_at": "2026-11-02T15:00:00+00:00", "symbol": "AMD_US_EQ", "net_pnl": -2.0, "r_multiple": -0.5,
         "fee_paid": 0.4, "currency": "GBP"},
    ]
    perf = journal_performance(recs)
    assert perf["trades"] == 3
    assert perf["net_pnl"] == pytest.approx(4.0)
    assert perf["profit_factor"] == pytest.approx(10.0 / 6.0, abs=0.01)
    assert [c["cum_pnl"] for c in perf["cumulative"]] == [10.0, 6.0, 4.0]
    assert [w["week_start"] for w in perf["weekly"]] == ["2026-11-02", "2026-10-26"]
    assert perf["by_market"]["UK"]["trades"] == 1 and perf["by_market"]["US"]["trades"] == 2
    assert perf["execution"]["avg_exit_slippage_pct"] == pytest.approx(0.02)
    assert perf["execution"]["exit_price_sources"] == {"broker_fill": 1, "before tracking": 2}
    assert journal_performance([]) == {"trades": 0}


def test_heartbeat_pings_rate_limited_and_reports_failures():
    with patch("bot.heartbeat.requests.post") as post:
        Heartbeat("").ok()  # disabled: no request
        assert post.call_count == 0

        hb = Heartbeat("https://hc-ping.com/abc/", min_interval_sec=60)
        hb.ok()
        hb.ok()  # within a minute: skipped
        assert post.call_count == 1
        assert post.call_args[0][0] == "https://hc-ping.com/abc"
        hb.fail("ValueError: boom")
        assert post.call_args[0][0] == "https://hc-ping.com/abc/fail"


def test_dashboard_includes_long_term_section(tmp_path: Path):
    from bot.config import Config
    from dashboard import build_long_term_performance

    (tmp_path / "trade_journal.jsonl").write_text(json.dumps(
        {"closed_at": "2026-10-26T15:00:00+00:00", "symbol": "NVDA_US_EQ", "net_pnl": 5.0, "r_multiple": 1.0}
    ) + "\n")
    EquityHistory(tmp_path / "equity_history.jsonl").maybe_record(500.0, 500.0)
    lt = build_long_term_performance(tmp_path)
    assert lt["journal"]["trades"] == 1
    assert lt["equity"]["stats"]["current_equity"] == 500.0
