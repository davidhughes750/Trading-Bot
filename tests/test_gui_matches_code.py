"""The pages must not quote numbers the code does not use.

Static text drifts: the desktop page once claimed a 3.5x/1.5x stop-target pair, "3 slots", "55 stocks", a Sharpe
estimate and AI "expected alpha" tiers that no code produced. Rule numbers now come from /api/status "rules"
(built from the Config); these tests catch the old claims coming back and check that the rules follow the config.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import dashboard
from bot.config import Config

ROOT = Path(__file__).resolve().parent.parent
PAGES = {
    "index.html": (ROOT / "web/templates/index.html").read_text(encoding="utf-8"),
    "dashboard.js": (ROOT / "web/static/js/dashboard.js").read_text(encoding="utf-8"),
    "mobile.js": (ROOT / "web/static/js/mobile.js").read_text(encoding="utf-8"),
}

# Phrases that were wrong (invented or stale) and must not come back
BANNED = [
    "Sharpe Efficiency", "Sharpe Benchmark", "sharpeEst", "0.7x Sizing", "Full Alpha (1.0x", "SPY > 50", "SPY &gt; 50",
    "defaultWinRate", "defaultReturn", "Model baseline simulation", "+0.62R", "2.33R", "1 : 2.33", "3.5x ATR TP / 1.5x SL",
    "Analyzing 50 assets", "All (55)", "US (50)", "UK 3x ETPs (5)", "50 stocks analyzed", "Search 55 stocks",
    "Session Realized P&L", "Math Expectancy", "3 Slots Max", "Max 2.0% Risk", "Defensive Guard",
    "(+4.5x ATR)", "+3.5x ATR Momentum Exit", "/ 4`", "/4`",
]


@pytest.mark.parametrize("phrase", BANNED)
def test_stale_or_invented_claims_do_not_come_back(phrase):
    hits = [name for name, text in PAGES.items() if phrase in text]
    assert not hits, f"{phrase!r} is back in {hits}"


def test_every_element_the_rules_loader_fills_exists_in_the_page():
    js = PAGES["dashboard.js"]
    body = js[js.index("function applyRules"):js.index("function updateScreenerStaleBanner")]
    ids = set(re.findall(r"set\('([a-z0-9-]+)'", body))
    assert ids, "applyRules sets nothing?"
    html = PAGES["index.html"]
    missing = sorted(i for i in ids if f'id="{i}"' not in html)
    assert not missing, f"applyRules fills ids that are not in the page: {missing}"


def test_rules_follow_the_config():
    cfg = Config(
        execution_mode="paper", stop_loss_atr_mult=1.7, take_profit_atr_mult=3.4, risk_per_trade_pct=0.02,
        max_open_positions=5, max_us_positions=4, max_daily_drawdown_pct=0.07, enable_gap_rebound=True,
        gap_rebound_max_positions=3, cooldown_minutes_after_loss=90,
    )
    recs = [{"symbol": "AAA_US_EQ"}, {"symbol": "BBB_US_EQ"}, {"symbol": "CCC_UK_EQ"}]
    r = dashboard.build_rules(cfg, recs)
    assert r["stop_loss_atr_mult"] == 1.7 and r["take_profit_atr_mult"] == 3.4 and r["reward_risk"] == 2.0
    assert r["risk_per_trade_pct"] == 2.0 and r["circuit_breaker_pct"] == 7.0 and r["cooldown_minutes"] == 90
    assert r["max_open_positions"] == 5 and r["max_us_positions"] == 4
    assert r["total_position_capacity"] == 8 and r["gap_rebound_enabled"] is True  # 5 intraday + 3 gap
    assert r["universe"] == {"us": 2, "uk": 1, "total": 3}


def test_capacity_counts_the_gap_pool_only_when_the_sleeve_is_on():
    on = Config(execution_mode="paper", max_open_positions=4, enable_gap_rebound=True, gap_rebound_max_positions=2)
    off = Config(execution_mode="paper", max_open_positions=4, enable_gap_rebound=False, gap_rebound_max_positions=2)
    assert on.total_position_capacity == 6 and off.total_position_capacity == 4
