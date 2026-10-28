# 📖 Trading 212 Quantitative Trading Bot — Comprehensive Wiki & Technical Manual

Welcome to the official technical wiki for the **Trading 212 Quantitative Trading Bot & Web Dashboard**. This manual documents the bot's system architecture, multi-market partitioning, quantitative mathematical models, risk engine, AI decision gatekeepers, interactive dashboard, Telegram bot suite, and deployment operations.

---

## 📑 Table of Contents
1. [System Architecture Overview](#1-system-architecture-overview)
2. [Multi-Market Partition Architecture (3 US + 1 UK)](#2-multi-market-partition-architecture-3-us--1-uk)
3. [Asset Universe & Ticker Classification (55 Assets)](#3-asset-universe--ticker-classification-55-assets)
4. [Quantitative Screener & Recommendation Engine](#4-quantitative-screener--recommendation-engine)
5. [Market Regime Filter & Inverse ETP Hedging](#5-market-regime-filter--inverse-etp-hedging)
6. [AI Portfolio Manager & Niche Duplication Guard](#6-ai-portfolio-manager--niche-duplication-guard)
7. [Trade Execution, Fee Accounting & Risk Management](#7-trade-execution-fee-accounting--risk-management)
8. [Web Dashboard & Interactive Telemetry Visualizers](#8-web-dashboard--interactive-telemetry-visualizers)
9. [Telegram Interactive Remote Control & Alerts](#9-telegram-interactive-remote-control--alerts)
10. [Proxmox LXC Deployment & DevOps Operations](#10-proxmox-lxc-deployment--devops-operations)
11. [Troubleshooting & Frequently Asked Questions](#11-troubleshooting--frequently-asked-questions)

---

## 1. System Architecture Overview

The system is engineered as an autonomous, high-availability quantitative trading daemon built in Python with zero third-party web framework overhead (no Flask, Django, or FastAPI bloat).

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           TRADING 212 BOT RUNTIME                               │
├─────────────────────────┬─────────────────────────────┬─────────────────────────┤
│    DATA INGESTION       │     QUANT STRATEGY CORE     │     EXECUTION ENGINE    │
│ • Trading 212 API v0    │ • Dual-EMA (20 / 50)        │ • OrderExecutor         │
│ • Yahoo Finance (OHLCV) │ • 14-period RSI & ATR       │ • RiskManager           │
│ • Google News RSS       │ • Relative Volume (RVOL)    │ • Dynamic Lot Sizing    │
│ • LSE / US Market Cal   │ • 0–100 Screener Matrix     │ • Fractional Precision  │
├─────────────────────────┼─────────────────────────────┼─────────────────────────┤
│    AI INTELLIGENCE      │    TELEMETRY & CONTROL      │    HOSTING & OPS        │
│ • Google Gemini Flash   │ • Glassmorphism Dashboard   │ • Proxmox VE (Debian)   │
│ • News Sentiment Gate   │ • Trade Journey Trajectory  │ • systemd 24/7 daemon   │
│ • Niche Duplication     │ • Telegram Interactive Bot  │ • Push-to-Proxmox bash  │
│ • Atomic Slot Rotation  │ • Executive PDF Tear-Sheets │ • 18-spec pytest suite  │
└─────────────────────────┴─────────────────────────────┴─────────────────────────┘
```

### Key Components
* **`main.py`**: Daemon entrypoint orchestrating the 15-second intra-bar management loop, 15-minute candle scanner, regime monitor, and async Telegram listener.
* **`bot/strategy.py`**: Pure quantitative logic for entry signals, candle-close protection, and ATR dynamic trailing stops.
* **`bot/risk_manager.py`**: Volatility sizing, notional caps, 24-hour drawdown circuit breakers, and fee-adjusted risk calculations.
* **`bot/screener.py`**: Multi-threaded scanner evaluating all 55 assets on closed 15m candles with vectorized pandas indicators.
* **`bot/ai_manager.py`**: Gemini 2.5 Flash agent evaluating headlines, binary catalyst risk, sector duplication, and slot rotation.
* **`bot/t212_client.py`**: Robust REST client for Trading 212 API v0 with token auth, rate-limit backoff, and broker ticker translation.
* **`dashboard.py`**: High-performance HTTP server rendering an Apple-grade dark/light glassmorphism analytics workstation.

---

## 2. Multi-Market Partition Architecture (3 US + 1 UK)

To maximize trading opportunities across timezones without capital competition, the portfolio enforces a strict **Dedicated Sleeve Partition**:

```text
MAX_OPEN_POSITIONS = 4  (MAX_US_POSITIONS = 3,  MAX_UK_POSITIONS = 1)
```

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       PORTFOLIO SLOTS (4 CONCURRENT MAX)                        │
├──────────────────────────────────────┬──────────────────────────────────────────┤
│         3 US EQUITY SLOTS            │             1 UK ETP SLOT                │
│    (NYSE / NASDAQ: 14:30–21:00 UK)   │     (London Stock Exchange: 08:00–16:30) │
│                                      │                                          │
│ • Slot 1: High-Beta US Stock         │ • Slot 4: UK 3x Leveraged Bull or Short  │
│ • Slot 2: High-Beta US Stock         │   ETP (0% FX fee, 0% Stamp Duty, GBP)    │
│ • Slot 3: High-Beta US Stock         │   Active during the London morning!      │
└──────────────────────────────────────┴──────────────────────────────────────────┘
```

### Why the Partition Matters
1. **Morning Market Independence**: In the morning (08:00–14:30 UK), the US market is closed. Holding 3 US stocks overnight will **never block** the UK ETP slot from entering a London breakout.
2. **Exchange-Aware AI Slot Rotation**: If the US sleeve is full (3/3), a new US `STRONG BUY` will only evaluate rotating out of a US position. It will never sell the UK ETP to buy a US stock (or vice versa).
3. **Session Awareness**: The bot verifies whether the relevant market is open before placing entry orders (`_is_market_open_for_symbol`) and applies a 15-minute opening-bell whipsaw guard to both London and New York opens.

---

## 3. Asset Universe & Ticker Classification (55 Assets)

The bot screens **55 institutional and high-momentum assets** every 15 minutes:

### 🇺🇸 50 High-Beta US Equities
* **AI & Semis**: `NVDA`, `AMD`, `AVGO`, `TSM`, `ARM`, `SMCI`, `MU`, `MRVL`, `ASML`
* **Mega-Cap Tech**: `AAPL`, `MSFT`, `GOOGL`, `AMZN`, `META`, `TSLA`
* **Cybersecurity & Cloud**: `CRWD`, `PANW`, `PLTR`, `SNOW`, `NET`, `DDOG`, `MDB`, `PATH`
* **Fintech & Crypto Proxies**: `COIN`, `MSTR`, `MARA`, `RIOT`, `CLSK`, `HOOD`, `AFRM`, `SOFI`, `PYPL`, `XYZ`
* **Deep Tech & Frontier**: `IONQ`, `RGTI`, `QBTS`, `RKLB`, `ASTS`, `LUNR`, `OKLO`, `SMR`, `RIVN`, `CVNA`, `DKNG`, `DUOL`, `HIMS`, `VKTX`, `BABA`, `PDD`

### 🇬🇧 5 UK 3x Leveraged ETPs (London Stock Exchange in GBP)
All UK ETPs are WisdomTree GBP-denominated share classes traded in pence (`GBX`), automatically normalized by `/ 100.0` to Pounds Sterling (`GBP` / `£`):

| Direction | Bot Symbol | T212 Broker Ticker | Yahoo Finance | Currency | FX Fee | Stamp Duty | Benchmark |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **3x Bull** | `QQQ3_UK_EQ` | `LQQ3l_EQ` | `LQQ3.L` | GBP (`£`) | **0.00%** | **0.00%** | +3x NASDAQ 100 |
| **3x Bull** | `3LUS_UK_EQ` | `3LUS1l_EQ` | `3LUS.L` | GBP (`£`) | **0.00%** | **0.00%** | +3x S&P 500 |
| **3x Bull** | `3LSE_UK_EQ` | `3SMCl_EQ` | `3SMC.L` | GBP (`£`) | **0.00%** | **0.00%** | +3x Semiconductors |
| **3x Short** | `QQQS_UK_EQ` | `LQQSl_EQ` | `LQQS.L` | GBP (`£`) | **0.00%** | **0.00%** | **-3x NASDAQ 100 (Bear Hedge)** |
| **3x Short** | `3USS_UK_EQ` | `3ULSl_EQ` | `3ULS.L` | GBP (`£`) | **0.00%** | **0.00%** | **-3x S&P 500 (Bear Hedge)** |

---

## 4. Quantitative Screener & Recommendation Engine

Every 15-minute candle close, the screener executes a multi-factor ranking across all 55 symbols using 6 parallel worker threads.

### The 0–100 Scoring Formula
The composite score (0 to 100 points) combines four independent quantitative factors:

```text
Composite Score = Score(Trend) + Score(RSI) + Score(RVOL) + Score(ROC)
```

1. **Trend Structure (0 to 40 points)**:
   * `Close > EMA20 > EMA50`: **+40 points** (Bullish alignment)
   * `Close > EMA20` and `EMA20 <= EMA50` with gap <= 0.5%: **+30 points** (Coiling for golden cross)
   * `Close > EMA50`: **+15 points**
   * `Close < EMA50`: **0 points** (Downtrend)
2. **Momentum Sweet-Spot (0 to 25 points)**:
   * `RSI between 52.0 and 65.0`: **+25 points** (Ideal expansion phase)
   * `RSI in [50.0, 52.0) or (65.0, 68.0]`: **+18 points**
   * `RSI > 68.0`: **+5 points** (Penalized for overbought exhaustion)
   * `RSI < 50.0`: **0 points** (Bearish momentum)
3. **Volume Participation (0 to 20 points)**:
   * `RVOL >= 1.75x`: **+20 points** (Institutional accumulation)
   * `RVOL >= 1.25x`: **+15 points**
   * `RVOL >= 1.00x`: **+10 points**
   * `RVOL < 1.00x`: **+2 points**
4. **Relative Strength / Rate of Change (0 to 15 points)**:
   * `10-Bar ROC >= +2.0%`: **+15 points**
   * `10-Bar ROC >= +0.5%`: **+10 points**
   * `10-Bar ROC >= 0.0%`: **+5 points**
   * `10-Bar ROC < 0.0%`: **0 points**

### Recommendation Tiers
* **`STRONG BUY`**: Score >= 80.0, RVOL >= 1.20x, not overextended.
* **`BUY`**: Score >= 76.0, RVOL >= 1.00x, not overextended.
* **`WATCH`**: Score >= 65.0 or high-scoring stock blocked by overextension or low volume.
* **`HOLD`**: Score between 50.0 and 64.9.
* **`AVOID`**: Score < 50.0 or `Close < EMA50`.

---

## 5. Market Regime Filter & Inverse ETP Hedging

The bot evaluates broad market health using the Nasdaq-100 benchmark (`QQQ`):

```text
                     ┌────────────────────────┐
                     │ QQQ Benchmark Analysis │
                     └───────────┬────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
    [BULLISH]               [CAUTIOUS]               [BEARISH]
Close > EMA20 > EMA50      Close between EMAs        Close < EMA20 < EMA50
   RSI >= 50.0              or RSI 46–50             or RSI < 46.0
         │                       │                       │
Long Min Score: 76.0    Long Min Score: 80.0    Long Min Score: 86.0
Inverse Short:  80.0    Inverse Short:  76.0    Inverse Short:  76.0
```

### Inverted Logic for Short ETPs (`QQQS.L` & `3USS.L`)
* When the US stock market crashes, **`QQQS.L` and `3USS.L` go UP** (+3% for every -1% drop in the index).
* Their charts form strong bullish breakouts (`Close > EMA20 > EMA50`, surging volume).
* `TradingBot._required_min_score_for_symbol()` automatically lowers the hurdle for inverse ETPs during `BEARISH` / `CAUTIOUS` markets to **`76.0`**, turning the UK sleeve into a portfolio hedge that profits on market downturns.

---

## 6. AI Portfolio Manager & Niche Duplication Guard

Powered by **Google Gemini (`gemini-2.5-flash`)** with fallback to deterministic keyword analysis, the AI manager vets every entry and slot rotation.

### 1. Pre-Entry Vetting
Before capital is committed, Gemini reviews:
1. **Recent News Headlines**: Detects negative binary catalysts (offerings, dilution, SEC inquiries, analyst downgrades).
2. **Technical Quality**: Checks whether price is overextended (> 1.6x ATR above EMA20).
3. **Sizing Multiplier**: Returns `size_multiplier` between 0.65x and 1.0x based on conviction.

### 2. High-Beta Niche Duplication Guard
To prevent correlated blow-ups, the bot groups volatile assets into specialized clusters:
* **Crypto & Bitcoin Miners**: `MSTR`, `COIN`, `MARA`, `RIOT`, `CLSK`, `HOOD`
* **Quantum Computing**: `IONQ`, `RGTI`, `QBTS`
* **Space & Satellite**: `RKLB`, `ASTS`, `LUNR`
* **Next-Gen Nuclear**: `SMR`, `OKLO`

> **Key Rule**: The bot will **never** hold more than 1 asset from the same niche cluster simultaneously.

### 3. Atomic Slot Rotation Guard (Anti-Churn Fix)
Before rotating out of a stagnant stock (Score < 50.0) for a new `STRONG BUY` (Score >= 80.0):
* The manager checks the candidate against all **retained** portfolio positions.
* If the replacement shares a niche with a retained position, rotation returns `HOLD` immediately.
* When approved, the replacement is marked `PRE-APPROVED`, preventing the bot from selling a position and then vetoing the entry.

---

## 7. Trade Execution, Fee Accounting & Risk Management

### Position Sizing Model
Every order size is calculated dynamically by `RiskManager.validate_and_build_trade_plan()`:

```text
Quantity = min( (Risk Amount USD) / (Entry Price - Stop Loss),
                (Account Equity * MAX_NOTIONAL_PCT) / (Entry Price) )
```

* **Stop-Loss Distance**: 1.5x ATR(14) below entry fill.
* **Take-Profit Distance**: 3.5x ATR(14) above entry fill (2.33x reward-to-risk ratio).
* **Capital Cap**: No single position can exceed 30% of total equity.

### Trading 212 FX Fee Accounting
Trading 212 charges a **0.15% FX conversion fee per leg** (0.30% round-trip) when trading USD equities from a GBP account:
* Entry Fee: Notional * 0.0015
* Exit Fee: Notional * 0.0015
* Net P&L: Gross P&L - (Entry Fee + Exit Fee)
* **Exemption**: All `_UK_EQ` symbols have a fee rate of **`0.0000` (0% FX fee, 0% Stamp Duty)**.

### 1R Trailing Stop-Loss Engine
To guarantee that profitable breakouts never turn into losses:
1. When unrealized profit reaches **+1.0R** (1.0x initial risk):
   ```text
   Stop Loss = Entry Price + (0.15 * Initial Risk)       [100% Risk-Free Breakeven]
   ```
2. As price continues upward, the stop ratchets to:
   ```text
   Stop Loss = max(Stop Loss, Highest Price - (0.5 * ATR)) [Trailing Ratchet]
   ```
3. **Anti-Whipsaw Buffer**: Trailing updates require at least a 0.05x ATR price advancement to avoid commission churn.

### Safety Circuit Breakers
* **Rolling 24-Hour Drawdown Limit**: Automatically halts entries and flattens positions if portfolio drawdown exceeds **5%**.
* **Post-Loss Cooldown**: Any stock closed at a loss is placed on a **120-minute trading lockout**.
* **Fractional Precision Retry**: Automatically rounds down share decimals if Trading 212 rejects an order with `LOT_SIZE_PRECISION_EXCEEDED`.

---

## 8. Web Dashboard & Interactive Telemetry Visualizers

Accessible on port `8050` (e.g. `http://<PROXMOX_IP>:8050`), the dashboard offers live real-time monitoring:

### 1. Portfolio Equity Trajectory Chart
* **1-Minute Downsampled Canvas**: Displays intraday portfolio equity compared to the opening session baseline.
* **Dynamic Color Fill**: Emerald green glow during profitable sessions, coral red during pullbacks.
* **Interactive Hover Scrubber**: Dragging across the curve reveals exact timestamp, equity, and session return.

### 2. Per-Position "Trade Journey Trajectory"
* Embedded directly inside each card in **Open Positions**.
* Traces the asset's exact path from **`BUY` Entry Anchor → Intraday Bars → `NOW` Live Mark**.
* Shows dashed **Entry Fill Line**, **Active Stop-Loss Line**, and **▲ Peak High** marker.
* Interactive crosshair displays historical price and unrealized P&L at any moment during the hold.

### 3. Apple-Grade Trade Runway
* Visual progress bar displaying the current mark between downside stop-loss and upside take-profit target.

### 4. Closed Trades Journey Replay
* The closed trades table preserves the complete Buy → Sell price curve for every completed trade.

---

## 9. Telegram Interactive Remote Control & Alerts

The bot features a two-way asynchronous Telegram listener and automated alert dispatcher:

### Slash Command Suite
* **`/status`**: Live portfolio equity, cash, slot allocation, US/UK session states, and active market regime.
* **`/positions`**: Detailed open position report with quantity, entry fill, current mark, net P&L, stop-loss, and take-profit.
* **`/uk` (or `/etp`)**: Dedicated telemetry matrix for all 5 UK 3x Leveraged Bull & Inverse Short ETPs in GBP (`£`).
* **`/chart [TICKER]`**: Generates and sends a 15-minute candlestick chart with EMA 20/50 bands and RSI subplot (e.g. `/chart QQQ3` or `/chart NVDA`).
* **`/summary`**: Dispatches the Executive Daily Performance Briefing on demand.
* **`/help`**: Lists all available commands.

### Automated Notifications
* **Trade Opened Alert**: Dispatched on entry fill with chart snapshot, technical thesis, and risk parameters.
* **Risk-Free Breakeven Alert**: Dispatched when a position hits +1.0R and the stop is moved into guaranteed profit.
* **Trade Closed Alert**: Dispatched on exit with fill price, net P&L, R-multiple, and exit trigger reason.
* **Daily Close Summary**: Dispatched automatically after US market close (21:00 UK).

---

## 10. Proxmox LXC Deployment & DevOps Operations

The bot is designed to run 24/7 on a Debian/Ubuntu LXC container under `systemd`.

### Quick Deployment via Bash Script
From your local development machine:
```bash
./push_to_proxmox.sh root@<PROXMOX_IP>
```
This script automatically packages the workspace, securely transfers it via SCP, extracts it into `/opt/trading-bot`, updates the virtual environment, configures the `systemd` daemon, and restarts the service.

### Essential Service Commands
```bash
# Check service status
ssh root@<PROXMOX_IP> "systemctl status t212-bot"

# Stream live bot execution logs
ssh root@<PROXMOX_IP> "journalctl -u t212-bot -f"
# or
ssh root@<PROXMOX_IP> "tail -f /opt/trading-bot/logs/trading_bot.log"

# Restart or stop the bot
ssh root@<PROXMOX_IP> "systemctl restart t212-bot"
ssh root@<PROXMOX_IP> "systemctl stop t212-bot"
```

### Running Test Suite Locally
```bash
source .venv/bin/activate
pytest -v
```
All 18 unit tests cover indicator calculations, risk sizing, Trading 212 API translation, UK ETP fee exemptions, atomic slot rotation, and trade journey trajectory serialization.

---

## 11. Troubleshooting & Frequently Asked Questions

#### Q: Why didn't the bot purchase a UK ETP during the London morning?
* Check if all 4 slots were full (holding 3 US + 1 UK). Under the partition, 1 slot is reserved exclusively for UK ETPs.
* If the slot is empty, check `/uk` on Telegram. The bot will only enter if a UK ETP meets the minimum score threshold (>= 76.0) with valid volume and trend alignment.

#### Q: How does the bot handle Trading 212 fractional order errors?
* If an order fails with `LOT_SIZE_PRECISION_EXCEEDED`, the bot automatically decrements decimal precision (e.g. from 4 to 3 to 2 decimals) and retries the fill.

#### Q: How do I know if Gemini AI is active or if it's using the fallback?
* In `/status` or on the web dashboard, look at the **AI Manager** pill:
  * `Google Gemini (gemini-2.5-flash)`: Active LLM catalyst analysis.
  * `Quant News & Catalyst Engine`: Built-in deterministic heuristic fallback.

---
*Created and maintained for the Trading 212 Quantitative Trading Bot Project.*
