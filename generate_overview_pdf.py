#!/usr/bin/env python3
"""Generate a publication-grade 2-page vector PDF overview of the Trading 212 Quant Bot.

Uses native PDF 1.4 vector graphics and standard Type1 fonts (Helvetica,
Helvetica-Bold, Courier) so it runs with zero external dependencies.
Output: /Users/david/Desktop/Trading Bot/Trading_212_Quant_Bot_Overview.pdf
"""

from __future__ import annotations

import zlib
from pathlib import Path
from typing import List, Tuple

PAGE_W = 595.28  # A4 width in points
PAGE_H = 841.89  # A4 height in points


def _pdf_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


class PDFCanvas:
    """Lightweight vector PDF page builder (top-left origin `(0, 0)` for convenience)."""

    def __init__(self, width: float = PAGE_W, height: float = PAGE_H) -> None:
        self.w = width
        self.h = height
        self.ops: List[str] = []

    def _y(self, y_top: float) -> float:
        return self.h - y_top

    def set_fill_rgb(self, r: int, g: int, b: int) -> None:
        self.ops.append(f"{r/255:.3f} {g/255:.3f} {b/255:.3f} rg")

    def set_stroke_rgb(self, r: int, g: int, b: int) -> None:
        self.ops.append(f"{r/255:.3f} {g/255:.3f} {b/255:.3f} RG")

    def set_line_width(self, width: float) -> None:
        self.ops.append(f"{width:.2f} w")

    def rect(
        self,
        x: float,
        y_top: float,
        w: float,
        h: float,
        fill: Tuple[int, int, int] | None = None,
        stroke: Tuple[int, int, int] | None = None,
        line_width: float = 1.0,
    ) -> None:
        if fill:
            self.set_fill_rgb(*fill)
        if stroke:
            self.set_stroke_rgb(*stroke)
            self.set_line_width(line_width)
        y_bot = self._y(y_top + h)
        mode = "B" if (fill and stroke) else ("f" if fill else "S")
        self.ops.append(f"{x:.2f} {y_bot:.2f} {w:.2f} {h:.2f} re {mode}")

    def line(
        self,
        x1: float,
        y1_top: float,
        x2: float,
        y2_top: float,
        color: Tuple[int, int, int] = (200, 210, 225),
        width: float = 1.0,
    ) -> None:
        self.set_stroke_rgb(*color)
        self.set_line_width(width)
        self.ops.append(
            f"{x1:.2f} {self._y(y1_top):.2f} m {x2:.2f} {self._y(y2_top):.2f} l S"
        )

    def text(
        self,
        x: float,
        y_top: float,
        content: str,
        font: str = "F1",
        size: float = 10.0,
        color: Tuple[int, int, int] = (20, 30, 45),
    ) -> None:
        self.set_fill_rgb(*color)
        escaped = _pdf_escape(content)
        self.ops.append(
            f"BT /{font} {size:.2f} Tf {x:.2f} {self._y(y_top):.2f} Td ({escaped}) Tj ET"
        )

    def badge(
        self,
        x: float,
        y_top: float,
        w: float,
        h: float,
        label: str,
        bg: Tuple[int, int, int],
        fg: Tuple[int, int, int],
        font_size: float = 8.0,
    ) -> None:
        self.rect(x, y_top, w, h, fill=bg)
        text_w = len(label) * (font_size * 0.52)
        tx = x + max(4.0, (w - text_w) / 2.0)
        ty = y_top + (h * 0.68)
        self.text(tx, ty, label, font="F2", size=font_size, color=fg)

    def get_stream_bytes(self) -> bytes:
        raw = "\n".join(self.ops).encode("latin-1", errors="replace")
        return zlib.compress(raw)


def build_page_1() -> PDFCanvas:
    c = PDFCanvas()

    # Background
    c.rect(0, 0, PAGE_W, PAGE_H, fill=(248, 250, 252))

    # Top Navy Header Banner
    c.rect(0, 0, PAGE_W, 108, fill=(11, 18, 32))
    c.rect(0, 105, PAGE_W, 3, fill=(0, 184, 255))

    c.text(36, 36, "TRADING 212 QUANTITATIVE ALGORITHMIC TRADING BOT", font="F2", size=16.5, color=(255, 255, 255))
    c.text(
        36,
        56,
        "High-Beta Momentum Screener, Compounding Position Sizing & Proxmox LXC Architecture",
        font="F1",
        size=9.5,
        color=(165, 185, 212),
    )

    # Header Status Pills
    c.badge(36, 70, 122, 20, "PLATFORM: TRADING 212 API v0", bg=(22, 36, 62), fg=(0, 200, 255), font_size=7.2)
    c.badge(164, 70, 134, 20, "UNIVERSE: 25 HIGH-BETA MOVERS", bg=(22, 36, 62), fg=(16, 215, 150), font_size=7.2)
    c.badge(304, 70, 88, 20, "TIMEFRAME: 15-MIN", bg=(22, 36, 62), fg=(255, 210, 90), font_size=7.2)
    c.badge(398, 70, 161, 20, "SLOTS: 3 CONCENTRATED (33% CAP)", bg=(22, 36, 62), fg=(255, 255, 255), font_size=7.2)

    # =========================================================================
    # SECTION 1: EXECUTIVE SUMMARY & ARCHITECTURE PIPELINE
    # =========================================================================
    c.text(36, 132, "1. EXECUTIVE OVERVIEW & MODULAR SYSTEM ARCHITECTURE", font="F2", size=11.5, color=(11, 18, 32))
    c.line(36, 138, PAGE_W - 36, 138, color=(0, 184, 255), width=1.2)

    c.text(
        36,
        154,
        "Engineered as a short-term momentum compounding machine, the bot scans 25 high-beta US growth equities every 15 minutes,",
        font="F1",
        size=9.1,
        color=(55, 65, 81),
    )
    c.text(
        36,
        167,
        "ranks them 0-100 across four quantitative pillars, and concentrates capital into the top 3 highest-conviction breakouts.",
        font="F1",
        size=9.1,
        color=(55, 65, 81),
    )

    # 5-Stage Pipeline Boxes
    stages = [
        ("1. DataHandler", "OHLCV & L1 Quotes", "EMA 20/50, RSI, ATR", (14, 116, 144)),
        ("2. StockScreener", "25 High-Beta Stocks", "0-100 Quant Score", (37, 99, 235)),
        ("3. Gemini AI Mgr", "News & Slot Rotate", "APPROVE / VETO / 1R", (79, 70, 229)),
        ("4. RiskManager", "3-Slot Compounder", "1.5% Risk & 5% DD Stop", (217, 119, 6)),
        ("5. OrderExecutor", "Trading 212 API v0", "Proxmox LXC & Web GUI", (5, 150, 105)),
    ]
    box_w = 96.0
    gap = 10.5
    start_x = 36.0
    box_y = 180.0
    box_h = 54.0

    for idx, (title, sub1, sub2, col) in enumerate(stages):
        bx = start_x + idx * (box_w + gap)
        c.rect(bx, box_y, box_w, box_h, fill=(255, 255, 255), stroke=(205, 215, 228), line_width=0.9)
        c.rect(bx, box_y, box_w, 16, fill=col)
        c.text(bx + 6, box_y + 11.5, title, font="F2", size=8.0, color=(255, 255, 255))
        c.text(bx + 6, box_y + 30, sub1, font="F2", size=7.8, color=(30, 41, 59))
        c.text(bx + 6, box_y + 43, sub2, font="F1", size=7.3, color=(100, 116, 139))
        if idx < len(stages) - 1:
            ax = bx + box_w + 2
            ay = box_y + box_h / 2
            c.line(ax, ay, ax + gap - 4, ay, color=(100, 116, 139), width=1.4)

    # =========================================================================
    # SECTION 2: HIGH-BETA MOMENTUM UNIVERSE & 0-100 SCORING MODEL
    # =========================================================================
    c.text(36, 256, "2. HIGH-BETA MOMENTUM UNIVERSE & 0-100 QUANT SCORING MODEL", font="F2", size=11.5, color=(11, 18, 32))
    c.line(36, 262, PAGE_W - 36, 262, color=(0, 184, 255), width=1.2)

    c.text(
        36,
        277,
        "Instead of slow defensive stocks or illiquid penny stocks with 2-5% spreads, the screener targets 25 liquid High-Beta",
        font="F1",
        size=8.9,
        color=(55, 65, 81),
    )
    c.text(
        36,
        289,
        "Momentum leaders (3%-12% daily ATR range, <0.05% institutional bid-ask spread):",
        font="F1",
        size=8.9,
        color=(55, 65, 81),
    )
    c.text(
        36,
        301,
        "AI/Semis: PLTR, NVDA, AMD, SMCI, ARM, MU, AVGO, MRVL  |  Crypto Proxies: MSTR, COIN, MARA, RIOT",
        font="F2",
        size=8.0,
        color=(15, 23, 42),
    )
    c.text(
        36,
        312,
        "Space/Quantum: RKLB, IONQ, ASTS  |  Fintech/Cloud/EV: HOOD, SOFI, AFRM, UPST, SHOP, APP, TSLA, RIVN, CRWD, NET",
        font="F2",
        size=8.0,
        color=(15, 23, 42),
    )

    # Scoring Table
    tbl_y = 321.0
    c.rect(36, tbl_y, PAGE_W - 72, 19, fill=(18, 28, 48))
    c.text(44, tbl_y + 13, "QUANTITATIVE FACTOR", font="F2", size=8.1, color=(255, 255, 255))
    c.text(185, tbl_y + 13, "MAX PTS", font="F2", size=8.1, color=(0, 200, 255))
    c.text(245, tbl_y + 13, "SCORING & TECHNICAL CRITERIA", font="F2", size=8.1, color=(255, 255, 255))

    rows = [
        (
            "1. Trend & EMA Crossover",
            "45 pts",
            "45 pts: Fresh 20>50 EMA cross | 34 pts: Strong uptrend (Close > EMA20 > EMA50) | 20 pts: Coiling",
        ),
        (
            "2. RSI (14) Momentum",
            "25 pts",
            "25 pts: Sweet-spot RSI (54 to 67) | 18 pts: Positive RSI (50 to 54) | 0 pts: Overbought (RSI > 72)",
        ),
        (
            "3. Relative Volume (RVOL)",
            "15 pts",
            "15 pts: Volume >= 1.5x 20-bar average | 11 pts: Volume >= 1.1x average | 6 pts: Normal (>= 0.8x)",
        ),
        (
            "4. 10-Bar Rel. Strength",
            "15 pts",
            "15 pts: 10-bar Rate of Change (ROC) >= +1.5% | 11 pts: ROC >= +0.5% | 7 pts: Positive (> 0%)",
        ),
    ]

    for i, (factor, pts, desc) in enumerate(rows):
        ry = tbl_y + 19 + i * 22
        bg = (255, 255, 255) if i % 2 == 0 else (241, 245, 249)
        c.rect(36, ry, PAGE_W - 72, 22, fill=bg, stroke=(226, 232, 240), line_width=0.5)
        c.text(44, ry + 14.5, factor, font="F2", size=8.3, color=(15, 23, 42))
        c.badge(183, ry + 3.5, 46, 15, pts, bg=(224, 242, 254), fg=(3, 105, 161), font_size=7.6)
        c.text(245, ry + 14.5, desc, font="F1", size=7.5, color=(51, 65, 85))

    # Rating Classification Strip
    strip_y = tbl_y + 113
    c.rect(36, strip_y, PAGE_W - 72, 44, fill=(255, 255, 255), stroke=(203, 213, 225), line_width=0.8)
    c.text(46, strip_y + 14, "RECOMMENDATION TIERS & CONCENTRATED 2-SLOT EXECUTION RULES:", font="F2", size=8.3, color=(15, 23, 42))
    c.badge(46, strip_y + 22, 82, 16, "STRONG BUY (>=80)", bg=(209, 250, 229), fg=(6, 95, 70), font_size=7.2)
    c.text(133, strip_y + 33, "Auto-Traded (#1 Priority)", font="F1", size=7.7, color=(51, 65, 85))
    c.badge(238, strip_y + 22, 62, 16, "BUY (70-79)", bg=(224, 242, 254), fg=(3, 105, 161), font_size=7.2)
    c.text(305, strip_y + 33, "Auto-Traded if slot open", font="F1", size=7.7, color=(51, 65, 85))
    c.badge(406, strip_y + 22, 62, 16, "WATCH", bg=(254, 243, 199), fg=(146, 64, 14), font_size=7.2)
    c.text(473, strip_y + 33, "Wait for EMA cross", font="F1", size=7.7, color=(51, 65, 85))

    # =========================================================================
    # SECTION 3: ENTRY, STOP-LOSS, TAKE-PROFIT & 1R TRAILING STOP LOGIC
    # =========================================================================
    c.text(36, 500, "3. TRADE ENTRY, ATR STOP-LOSS, TAKE-PROFIT & 1R TRAILING STOP", font="F2", size=11.5, color=(11, 18, 32))
    c.line(36, 506, PAGE_W - 36, 506, color=(0, 184, 255), width=1.2)

    cards = [
        (
            "A. Entry Conditions (Long-Only ISA/Invest)",
            [
                "- Trigger 1 (Crossover): 20 EMA crosses above 50 EMA on",
                "  a confirmed closed 15m bar AND 14-period RSI > 50.",
                "- Trigger 2 (Top Quant Pick): Stock scores >= 70/100 with",
                "  Close > 20 EMA > 50 EMA, rising 20 EMA, and RSI 50-70.",
                "- Stocks with EMA20 <= EMA50 are held in WATCH status.",
            ],
            (37, 99, 235),
        ),
        (
            "B. Dynamic Volatility Exit Rules (14-Period ATR)",
            [
                "- Initial Stop-Loss: Placed at Entry Price - (1.5 x ATR).",
                "  Adapts automatically to each stock's volatility.",
                "- Profit Target: Placed at Entry Price + (2.0 x ATR),",
                "  providing a positive 1.33:1 reward-to-risk ratio.",
                "- Slot Rotation: Freed cash rotates into next #1 pick.",
            ],
            (5, 150, 105),
        ),
    ]

    for idx, (ctitle, lines, accent) in enumerate(cards):
        cx = 36 + idx * 266
        cy = 518
        cw = 257
        ch = 108
        c.rect(cx, cy, cw, ch, fill=(255, 255, 255), stroke=(203, 213, 225), line_width=0.9)
        c.rect(cx, cy, 4, ch, fill=accent)
        c.text(cx + 12, cy + 17, ctitle, font="F2", size=9.0, color=(15, 23, 42))
        for l_idx, line_str in enumerate(lines):
            c.text(cx + 12, cy + 35 + l_idx * 14, line_str, font="F1", size=8.1, color=(51, 65, 85))

    # 1R Trailing Stop Diagram Box
    ts_y = 640
    c.rect(36, ts_y, PAGE_W - 72, 138, fill=(15, 23, 42), stroke=(30, 41, 59), line_width=1.0)
    c.text(50, ts_y + 20, "HOW THE +1.0R RATCHETING TRAILING STOP WORKS (INTRA-BAR EVERY 15 SECONDS)", font="F2", size=9.2, color=(0, 200, 255))
    c.text(
        50,
        ts_y + 36,
        "1R equals the initial risk distance: 1R = |Entry Price - Initial Stop-Loss| = 1.5 x ATR. Once unrealized profit reaches +1.0R,",
        font="F1",
        size=8.2,
        color=(203, 213, 225),
    )
    c.text(
        50,
        ts_y + 49,
        "the bot activates Trailing Mode and ratchets the Stop-Loss upward at (Highest Price Reached - 1.5 x ATR), locking in gains:",
        font="F1",
        size=8.2,
        color=(203, 213, 225),
    )

    # Visual price scale inside dark box
    bar_y = ts_y + 82
    c.line(60, bar_y, PAGE_W - 60, bar_y, color=(71, 85, 105), width=3.0)

    markers = [
        (80, "Initial Stop-Loss", "Entry - 1.5x ATR (-1.0R)", (239, 68, 68)),
        (210, "Entry Price", "0.0R Baseline", (56, 189, 248)),
        (355, "+1.0R Reached (Trail Activates)", "Stop moves to Breakeven!", (250, 204, 21)),
        (500, "Take-Profit Target", "Entry + 2.0x ATR (+1.33R)", (16, 185, 129)),
    ]
    for mx, mtitle, msub, mcol in markers:
        c.rect(mx - 4, bar_y - 6, 8, 12, fill=mcol)
        c.text(mx - 28, bar_y - 14, mtitle, font="F2", size=7.6, color=mcol)
        c.text(mx - 28, bar_y + 22, msub, font="F1", size=7.2, color=(203, 213, 225))

    # Footer
    c.line(36, PAGE_H - 36, PAGE_W - 36, PAGE_H - 36, color=(203, 213, 225), width=0.7)
    c.text(36, PAGE_H - 22, "Trading 212 Quantitative Trading Bot | Architecture & High-Beta Strategy Specification", font="F1", size=8.0, color=(100, 116, 139))
    c.text(PAGE_W - 90, PAGE_H - 22, "Page 1 of 2", font="F2", size=8.0, color=(100, 116, 139))

    return c


def build_page_2() -> PDFCanvas:
    c = PDFCanvas()

    # Background
    c.rect(0, 0, PAGE_W, PAGE_H, fill=(248, 250, 252))

    # Compact Header
    c.rect(0, 0, PAGE_W, 64, fill=(11, 18, 32))
    c.rect(0, 61, PAGE_W, 3, fill=(0, 184, 255))
    c.text(36, 30, "COMPOUNDING SNOWBALL SIZING, RISK GUARDS & PROXMOX LXC DEPLOYMENT", font="F2", size=13.5, color=(255, 255, 255))
    c.text(36, 47, "3-Slot Concentrated Sizing (£500 Baseline), 24h Circuit Breaker, Live Case Study & 24/7 Server Ops", font="F1", size=9.0, color=(165, 185, 212))

    # =========================================================================
    # SECTION 4: THE 4 CRITICAL RISK & COMPOUNDING RULES
    # =========================================================================
    c.text(36, 90, "4. COMPOUNDING POSITION SIZING & CAPITAL PRESERVATION GUARDS", font="F2", size=11.5, color=(11, 18, 32))
    c.line(36, 96, PAGE_W - 36, 96, color=(0, 184, 255), width=1.2)

    guards = [
        (
            "1. 3-Slot Concentrated Compounding (£500 Base)",
            "Concentrates capital into the top 3 setups (33% cap/slot):",
            "Qty = min(Equity x 1.5% / StopDist, Equity x 33% / Price)",
            "Every winning trade increases Total Equity, automatically",
            "compounding subsequent trade sizes without manual intervention.",
            (37, 99, 235),
        ),
        (
            "2. Hard 5% 24-Hour Drawdown Circuit Breaker",
            "RiskManager tracks a rolling 24-hour equity high-water mark.",
            "Drawdown = (Peak_24h - Current_Equity) / Peak_24h",
            "If drawdown reaches >= 5.0%, the bot immediately flattens all",
            "open positions via Market Sell and halts trading.",
            (220, 38, 38),
        ),
        (
            "3. Slippage & Bid-Ask Spread Guard (0.15%)",
            "Before any order is routed, top-of-book quotes are checked:",
            "Spread % = (Ask - Bid) / Mid_Price <= 0.15%",
            "Off-exchange IEX stub quotes are filtered out, and any",
            "instrument exceeding 0.15% spread is rejected.",
            (217, 119, 6),
        ),
        (
            "4. Off-Hours Order Sync & T212 Rate Throttling",
            "Reconciles both active working orders and open positions:",
            "Sync = /equity/portfolio + /equity/orders",
            "Preserves overnight queued orders until market open and",
            "enforces per-endpoint rate limits (5.2s cash, 50/min orders).",
            (5, 150, 105),
        ),
    ]

    for idx, (gtitle, l1, formula, l2, l3, col) in enumerate(guards):
        col_idx = idx % 2
        row_idx = idx // 2
        gx = 36 + col_idx * 266
        gy = 108 + row_idx * 106
        gw = 257
        gh = 96
        c.rect(gx, gy, gw, gh, fill=(255, 255, 255), stroke=(203, 213, 225), line_width=0.9)
        c.rect(gx, gy, gw, 18, fill=col)
        c.text(gx + 10, gy + 12.5, gtitle, font="F2", size=8.4, color=(255, 255, 255))
        c.text(gx + 10, gy + 32, l1, font="F1", size=7.9, color=(51, 65, 85))
        c.rect(gx + 10, gy + 39, gw - 20, 17, fill=(241, 245, 249))
        c.text(gx + 14, gy + 50.5, formula, font="F3", size=7.2, color=(15, 23, 42))
        c.text(gx + 10, gy + 70, l2, font="F1", size=7.8, color=(71, 85, 105))
        c.text(gx + 10, gy + 82, l3, font="F1", size=7.8, color=(71, 85, 105))

    # =========================================================================
    # SECTION 5: LIVE HIGH-BETA SCREENER & EXECUTION LOG SNAPSHOT
    # =========================================================================
    c.text(36, 338, "5. LIVE HIGH-BETA SCREENER & EXECUTION LIFECYCLE SNAPSHOT", font="F2", size=11.5, color=(11, 18, 32))
    c.line(36, 344, PAGE_W - 36, 344, color=(0, 184, 255), width=1.2)

    c.text(
        36,
        360,
        "Live examples from logs/trading_bot.log demonstrating high-beta selection, WATCH filtering, and stop-loss rotation:",
        font="F1",
        size=8.9,
        color=(55, 65, 81),
    )

    pt_y = 372.0
    c.rect(36, pt_y, PAGE_W - 72, 20, fill=(18, 28, 48))
    c.text(42, pt_y + 13.5, "TICKER", font="F2", size=8.0, color=(255, 255, 255))
    c.text(105, pt_y + 13.5, "RATING", font="F2", size=8.0, color=(0, 200, 255))
    c.text(170, pt_y + 13.5, "SCORE", font="F2", size=8.0, color=(255, 255, 255))
    c.text(208, pt_y + 13.5, "PRICE", font="F2", size=8.0, color=(255, 255, 255))
    c.text(256, pt_y + 13.5, "STOP-LOSS", font="F2", size=8.0, color=(255, 140, 140))
    c.text(312, pt_y + 13.5, "TARGET", font="F2", size=8.0, color=(110, 231, 183))
    c.text(365, pt_y + 13.5, "BOT ACTION & QUANTITATIVE THESIS", font="F2", size=8.0, color=(255, 255, 255))

    live_trades = [
        ("MU_US_EQ", "STRONG BUY", "88.0", "$908.87", "$901.76", "$918.35", "Auto-Bought Slot | Fresh 20/50 EMA cross + RVOL 1.24x"),
        ("TSLA_US_EQ", "STRONG BUY", "81.0", "$368.09", "$365.55", "$371.48", "Auto-Bought #1 Pick | Uptrend + RSI 59.3 + RVOL 2.61x"),
        ("APP_US_EQ", "WATCH", "71.0", "$268.98", "$267.13", "$271.45", "Held in WATCH | High RVOL 3.85x, waiting for EMA cross"),
        ("PLTR_US_EQ", "HOLD", "55.0", "$194.16", "$192.59", "$196.26", "Skipped (<70) | Bullish EMA structure, RSI 51.8 neutral"),
        ("WMT_US_EQ", "SL EXIT", "-1.0R", "$118.67", "$118.67", "$119.63", "Auto-Closed on intra-bar SL -> Rotated slot into MU_US_EQ"),
    ]

    for i, (tkr, rat, scr, prc, sl, tp, ths) in enumerate(live_trades):
        ry = pt_y + 20 + i * 23
        bg = (255, 255, 255) if i % 2 == 0 else (241, 245, 249)
        c.rect(36, ry, PAGE_W - 72, 23, fill=bg, stroke=(226, 232, 240), line_width=0.5)
        c.text(42, ry + 15, tkr, font="F2", size=8.2, color=(15, 23, 42))
        if rat == "STRONG BUY":
            b_bg, b_fg = (209, 250, 229), (6, 95, 70)
        elif rat == "WATCH":
            b_bg, b_fg = (254, 243, 199), (146, 64, 14)
        elif rat == "SL EXIT":
            b_bg, b_fg = (254, 226, 226), (153, 27, 27)
        else:
            b_bg, b_fg = (226, 232, 240), (71, 85, 105)
        c.badge(103, ry + 4, 60, 14, rat, bg=b_bg, fg=b_fg, font_size=6.8)
        c.text(172, ry + 15, scr, font="F2", size=8.0, color=(15, 23, 42))
        c.text(208, ry + 15, prc, font="F3", size=7.7, color=(15, 23, 42))
        c.text(256, ry + 15, sl, font="F3", size=7.7, color=(220, 38, 38))
        c.text(312, ry + 15, tp, font="F3", size=7.7, color=(5, 150, 105))
        c.text(365, ry + 15, ths, font="F1", size=7.2, color=(51, 65, 85))

    # =========================================================================
    # SECTION 6: 24/7 PROXMOX LXC SERVER & LAN WEB COMMAND CENTER
    # =========================================================================
    c.text(36, 535, "6. 24/7 PROXMOX LXC CONTAINER DEPLOYMENT & LAN WEB DASHBOARD", font="F2", size=11.5, color=(11, 18, 32))
    c.line(36, 541, PAGE_W - 36, 541, color=(0, 184, 255), width=1.2)

    c.rect(36, 554, PAGE_W - 72, 195, fill=(255, 255, 255), stroke=(203, 213, 225), line_width=0.9)
    c.text(50, 573, "Always-On Headless Linux LXC Operation + Real-Time Web GUI (Port 8050)", font="F2", size=9.5, color=(15, 23, 42))
    c.text(
        50,
        588,
        "Designed to run 24/7 inside an unprivileged Debian/Ubuntu LXC container on Proxmox VE (~110 MB RAM, 1 vCPU):",
        font="F1",
        size=8.3,
        color=(51, 65, 85),
    )
    bullet_items = [
        "1. Systemd Daemon (t212-bot.service): Auto-starts on Proxmox boot and auto-restarts within 10s if interrupted.",
        "2. LAN-Accessible Web Dashboard (0.0.0.0:8050): View Equity, Open Slots (x/2), 1R Trailing Gauges & 25-Stock Leaderboard.",
        "3. One-Command Mac-to-Proxmox Deploy: push_to_proxmox.sh bundles code + .env and provisions the LXC via pct push/exec.",
        "4. Live Trading FX Optimization: Hold USD in Trading 212 Invest when going live to avoid the 0.15% GBP/USD FX conversion fee.",
    ]
    for b_idx, b_text in enumerate(bullet_items):
        c.text(58, 605 + b_idx * 15, b_text, font="F1", size=8.0, color=(30, 41, 59))

    # CLI Commands Box
    c.rect(50, 672, PAGE_W - 100, 66, fill=(15, 23, 42))
    c.text(62, 687, "./push_to_proxmox.sh root@<PROXMOX_IP> <CT_ID>  # 1-command deploy from Mac to Proxmox LXC container", font="F3", size=7.7, color=(56, 189, 248))
    c.text(62, 701, "systemctl status t212-bot                       # Check 24/7 systemd service inside Proxmox LXC", font="F3", size=7.7, color=(16, 215, 150))
    c.text(62, 715, "python main.py                                  # Run bot + LAN Web Dashboard (http://<IP>:8050)", font="F3", size=7.7, color=(250, 204, 21))
    c.text(62, 729, "python main.py --recommend                      # Print ranked 25-stock High-Beta leaderboard only", font="F3", size=7.7, color=(203, 213, 225))

    # Footer
    c.line(36, PAGE_H - 36, PAGE_W - 36, PAGE_H - 36, color=(203, 213, 225), width=0.7)
    c.text(36, PAGE_H - 22, "Trading 212 Quantitative Trading Bot | Compounding Risk Controls & Proxmox LXC Operations", font="F1", size=8.0, color=(100, 116, 139))
    c.text(PAGE_W - 90, PAGE_H - 22, "Page 2 of 2", font="F2", size=8.0, color=(100, 116, 139))

    return c


def write_pdf(output_path: Path, pages: List[PDFCanvas]) -> None:
    """Assemble a valid multi-page PDF 1.4 binary file."""
    objects: List[bytes] = []

    def add_obj(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    # 1: Catalog, 2: Pages placeholder, 3..5: Standard Type1 Fonts
    add_obj(b"<< /Type /Catalog /Pages 2 0 R >>")
    add_obj(b"")  # Reserved for /Pages
    f1_id = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    f2_id = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    f3_id = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold /Encoding /WinAnsiEncoding >>")

    page_ids: List[int] = []
    for page in pages:
        stream_data = page.get_stream_bytes()
        content_id = add_obj(
            f"<< /Length {len(stream_data)} /Filter /FlateDecode >>\nstream\n".encode("ascii")
            + stream_data
            + b"\nendstream"
        )
        page_dict = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W:.2f} {PAGE_H:.2f}] "
            f"/Resources << /Font << /F1 {f1_id} 0 R /F2 {f2_id} 0 R /F3 {f3_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("ascii")
        page_ids.append(add_obj(page_dict))

    kids_str = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids_str}] /Count {len(page_ids)} >>".encode("ascii")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: List[int] = [0]
    for idx, obj_bytes in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode("ascii"))
        out.extend(obj_bytes)
        out.extend(b"\nendobj\n")

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))

    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    output_path.write_bytes(bytes(out))


def main() -> None:
    target = Path(__file__).resolve().parent / "Trading_212_Quant_Bot_Overview.pdf"
    write_pdf(target, [build_page_1(), build_page_2()])
    print(f"Generated PDF overview: {target} ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
