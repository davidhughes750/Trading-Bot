# 📖 Trading 212 Quantitative Trading Bot — Comprehensive Wiki & Technical Manual

Welcome to the official technical wiki for the **Trading 212 Quantitative Trading Bot & Web Dashboard**. This manual documents the bot's system architecture, multi-market partitioning, quantitative mathematical models, risk engine, AI decision gatekeepers, interactive dashboard, Telegram bot suite, and deployment operations.

---

## 📑 Table of Contents
1. [System Architecture Overview](#1-system-architecture-overview)
2. [Multi-Market Partition Architecture (3 US + 1 UK)](#2-multi-market-partition-architecture-3-us--1-uk)
3. [Asset Universe & Ticker Classification (71 Assets)](#3-asset-universe--ticker-classification-71-assets)
4. [Quantitative Screener & Recommendation Engine](#4-quantitative-screener--recommendation-engine)
5. [Market Regime Filter & Inverse ETP Hedging](#5-market-regime-filter--inverse-etp-hedging)
6. [AI Portfolio Manager & Niche Duplication Guard](#6-ai-portfolio-manager--niche-duplication-guard)
7. [Trade Execution, Fee Accounting & Risk Management](#7-trade-execution-fee-accounting--risk-management)
7b. [Backtesting & Measuring the Strategy](#7b-backtesting--measuring-the-strategy)
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
│ • Yahoo Finance news    │ • Relative Volume (RVOL)    │ • Dynamic Lot Sizing    │
│ • LSE / US Market Cal   │ • 0–100 Screener Matrix     │ • Fractional Precision  │
├─────────────────────────┼─────────────────────────────┼─────────────────────────┤
│    AI INTELLIGENCE      │    TELEMETRY & CONTROL      │    HOSTING & OPS        │
│ • Google Gemini Flash   │ • Glassmorphism Dashboard   │ • Proxmox VE (Debian)   │
│ • News Sentiment Gate   │ • Trade Journey Trajectory  │ • systemd 24/7 daemon   │
│ • Niche Duplication     │ • Telegram Interactive Bot  │ • Push-to-Proxmox bash  │
│ • Atomic Slot Rotation  │ • Executive PDF Tear-Sheets │ • pytest suite          │
└─────────────────────────┴─────────────────────────────┴─────────────────────────┘
```

### Key Components
* **`main.py`**: Entry point. `TradingBot.run_cycle()` runs each poll as named steps: sync with Trading 212, equity and circuit breaker, end-of-day flat, intra-bar position management, candle scan, candle-close exits, entry selection, slot rotation and entries. Also hosts the Telegram command listener.
* **`bot/strategy_engine.py`**: Pure logic for entry signals, stops/targets, trailing stops and the market regime classifier.
* **`bot/screener.py`**: Scores every symbol 0–100 on each closed candle.
* **`bot/risk_manager.py`**: Position sizing in account currency, slot and score rules, spread guard, 24-hour drawdown circuit breaker.
* **`bot/order_executor.py`**: Places orders and confirms fills against the Trading 212 position, journals trades, optional broker backup stops, paper simulator.
* **`bot/t212_client.py`**: Trading 212 REST client (rate limits, ticker translation, GBX→GBP). Order submissions are never retried.
* **`bot/fx.py`**: Converts USD prices into the account currency.
* **`bot/market_calendar.py`**: US holidays/early closes and US/UK session windows (shared by the bot and the backtester).
* **`bot/ai_manager.py`**: Gemini (or keyword fallback) entry vetting, slot rotation and loss postmortems.
* **`bot/backtest.py` / `backtest.py`**: Historical replay of the same rules.
* **`bot/analysis.py` / `analyze.py`**: Reports from the scan log, AI decision log and trade journal.
* **`dashboard.py`**: HTTP server for the web dashboard (`web/`).

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

## 3. Asset Universe & Ticker Classification (71 Assets)

The bot screens **71 assets** every 15 minutes (lists live in `bot/screener.py`):

### 🇺🇸 63 High-Beta US Equities
* **Mega-Cap "Magnificent 7+" Institutional Core**: `GOOGL`, `META`, `AMZN`, `MSFT`, `AAPL`, `NFLX`, `ORCL`, `UBER`
* **High-Beta AI, Semiconductors & Compute**: `PLTR`, `NVDA`, `AMD`, `SMCI`, `ARM`, `MU`, `AVGO`, `MRVL`, `TSM`, `ANET`, `VRT`
* **Crypto-Linked High-Beta Equities**: `MSTR`, `COIN`, `MARA`, `RIOT`, `CLSK`
* **AI Power, Grid, Nuclear, Uranium & Gold/Resources**: `VST`, `CEG`, `GEV`, `OKLO`, `CCJ`, `ENPH`, `NEM`, `FCX`
* **Space, Quantum, Defense & Frontier Tech**: `RKLB`, `IONQ`, `ASTS`, `LUNR`, `AXON`, `KTOS`, `RGTI`
* **High-Beta Fintech & Digital Brokerage**: `HOOD`, `SOFI`, `AFRM`, `UPST`, `NU`, `FUTU`
* **Hyper-Growth Cloud, Cyber & AI Software**: `SHOP`, `APP`, `CRWD`, `NET`, `SNOW`, `PANW`, `DDOG`, `IOT`
* **Explosive Consumer, Social, Gaming & EV Breakouts**: `TSLA`, `RIVN`, `RDDT`, `CVNA`, `DKNG`, `DUOL`
* **High-Beta Biotech, Healthcare & Global ADR Movers**: `HIMS`, `VKTX`, `BABA`, `PDD`

### 🇬🇧 8 UK 3x Leveraged & Inverse ETPs (London Stock Exchange in GBP)

The UK sleeve trades **WisdomTree 3x Leveraged & Inverse Short ETPs** natively in British Pounds (`GBP` / `£`).

#### Key Advantages
* **0.00% FX Conversion Fee**: Trades directly in GBP, avoiding Trading 212's 0.30% round-trip foreign exchange fee.
* **0.00% UK Stamp Duty**: Fully exempt from the standard 0.50% UK Stamp Duty Reserve Tax (SDRT).
* **Automatic Pence-to-Pound Conversion**: London prices quoted in pence (`GBX`) are automatically normalized to Pounds (`GBP` / `£`) by dividing by `100.0`.
* **Dedicated Trading Hours**: London Stock Exchange session runs `08:00 – 16:30 UK` (active 6.5 hours before US market open).

#### ETP Sleeve Matrix

| Direction | Display | T212 API Ticker | Yahoo Symbol | Target Benchmark | Sleeve Role |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **3x Bull** | `QQQ3.L` | `LQQ3l_EQ` | `LQQ3.L` | +3x NASDAQ 100 | Tech momentum breakout |
| **3x Bull** | `3LUS.L` | `3LUS1l_EQ` | `3LUS.L` | +3x S&P 500 | Large-cap market rally |
| **3x Bull** | `3LSE.L` | `3SMCl_EQ` | `3SMC.L` | +3x Semiconductors | Semiconductor sector surge |
| **3x Short** | `QQQS.L` | `LQQSl_EQ` | `LQQS.L` | -3x NASDAQ 100 | Tech sell-off hedge & downside profit |
| **3x Short** | `3USS.L` | `3ULSl_EQ` | `3ULS.L` | -3x S&P 500 | Broad market bear hedge |

> 💡 **Share Class Note**: On the London Stock Exchange, WisdomTree lists both USD and GBP share classes for leveraged ETPs. The bot specifically maps to the **GBP-denominated tickers** (`LQQSl_EQ` and `3ULSl_EQ` on Trading 212, `LQQS.L` and `3ULS.L` on Yahoo Finance) so your account never pays currency exchange fees.

---

## 4. Quantitative Screener & Recommendation Engine

Every 15-minute candle close, the screener executes a multi-factor ranking across all 71 symbols using 6 parallel worker threads.

### The 0–100 Scoring Formula
Implemented in `StockScreener.evaluate_dataframe()` (`bot/screener.py`):

```text
Score = Trend + RSI + RVOL + ROC - penalties      (clamped to 0..100)
```

1. **Trend (0 to 45 points)**:
   * Fresh EMA20/EMA50 bullish crossover on this bar: **45**
   * `Close > EMA20 > EMA50` with EMA20 rising: **34**
   * `EMA20 > EMA50`: **22**
   * Coiling: EMA gap between -0.25% and 0%, EMA20 rising, close above EMA20: **20**
   * Otherwise: `max(0, 10 + 5 x EMA gap %)`
2. **RSI momentum (0 to 25 points)**:
   * 54 to 67: **25** · 50 to 54: **18** · 67 to 72: **14** · above 72: **0**
   * below 50: `max(0, (RSI - 35) x 0.5)`
3. **Relative volume vs the 20-bar average (0 to 15 points)**:
   * `>= 1.5x`: **15** · `>= 1.1x`: **11** · `>= 0.8x`: **6** · lower: **2**
4. **10-bar rate of change (0 to 15 points)**:
   * `>= +1.5%`: **15** · `>= +0.5%`: **11** · `> 0%`: **7** · otherwise **0**
5. **Penalties**: **-15** if the close is more than `MAX_EMA_EXTENSION_ATR` (1.6) ATRs above EMA20;
   **-10** for an upper-wick rejection candle.

**FX fee hurdle**: a US share is only tradeable if its take-profit is at least
`MIN_TARGET_MOVE_PCT_FX` (1.5%) away, so the 0.30% round-trip FX fee stays small relative to the
expected gain. UK ETPs are exempt.

### Recommendation Tiers
* **`STRONG BUY` (crossover)**: fresh bullish crossover with RSI > 50, not overextended, no wick
  rejection, FX hurdle passed, RVOL >= 0.85 x `MIN_RVOL_FOR_ENTRY`.
* **`STRONG BUY` / `BUY` (trend)**: `Close > EMA20 > EMA50`, EMA20 rising, RSI 50 to 68,
  RVOL >= `MIN_RVOL_FOR_ENTRY`, not overextended, no wick rejection, FX hurdle passed, and score >=
  `MIN_RECOMMENDATION_SCORE` (76). Rated STRONG BUY at 80+.
* **`WATCH`**: trend aligned but overextended or failing the FX hurdle, or coiling with RSI >= 50.
* **`HOLD`**: EMA20 > EMA50 and RSI >= 48. **`AVOID`**: everything else.

Only BUY / STRONG BUY ratings are actionable, and the market regime can raise the score needed
(section 5).

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
* `required_min_score()` (`bot/risk_manager.py`) automatically lowers the hurdle for inverse ETPs during `BEARISH` / `CAUTIOUS` markets to **`76.0`**, turning the UK sleeve into a portfolio hedge that profits on market downturns.

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
Every order is sized by `RiskManager.calculate_position_size()`. Equity, cash and risk are in
the account currency (`ACCOUNT_CURRENCY`, default GBP); US prices are converted with the live
GBP/USD rate before sizing.

```text
fx          = account currency per 1 unit of the price currency (1.0 for GBP-priced UK ETPs)
risk budget = equity * RISK_PER_TRADE_PCT                       (default 1.5%)
quantity    = min( risk budget / (stop distance * fx),
                   min(equity * MAX_POSITION_EXPOSURE_PCT,      (default 33%)
                       free cash / open slots left,
                       free cash less a fee buffer) / (entry price * fx) )
```

* **Stop-loss**: `STOP_LOSS_ATR_MULT` (1.5) x ATR(14) below the fill.
* **Take-profit**: `TAKE_PROFIT_ATR_MULT` (2.0) x ATR(14) above the fill. Can be extended up to
  `TP_EXTENSION_MAX` times while the trend stays strong.
* If no exchange rate is available, US entries are skipped rather than sized in the wrong currency.

### Order Placement & Fill Confirmation
* Order submissions are **never retried automatically**. If a request times out, the bot checks
  the account to see whether it went through instead of sending it again.
* A fill only counts once the Trading 212 position quantity actually changes. An order that is
  accepted but still queued (e.g. market closed) leaves the position open, and no second order is
  sent while one is working.
* An unfilled limit order is only replaced by a market order after the cancel is confirmed.
* Fill prices and fees come from `GET /equity/history/orders`. If that is unavailable the bot
  falls back to the position's average price (entries) or the quote (exits) and records which
  source it used (`entry_price_source` / `exit_price_source` in the journal), along with slippage.

### Trading 212 FX Fee Accounting
Trading 212 charges a **0.15% FX conversion fee per leg** (0.30% round-trip) on USD shares bought
from a GBP account. Net P&L is recorded in the account currency and includes exchange-rate moves
between entry and exit:

```text
gross = quantity * (exit price * fx at exit - entry price * fx at entry)
net   = gross - entry fee - exit fee
```

All `_UK_EQ` symbols use a fee rate of **0%** (GBP-priced, no FX conversion or stamp duty).

### Trailing Stop Engine
1. At **+1.0R** (`TRAILING_STOP_ACTIVATE_R`) the stop moves to a fee-adjusted breakeven:
   entry x (1 + 2 x FX fee + 0.05%) for US shares, entry for UK ETPs.
2. From **+1.5R** (`TRAILING_STOP_START_R`) it trails `TRAILING_STOP_ATR_MULT` (1.5) x ATR below
   the highest price, never below the breakeven floor.
3. Intra-bar checks (every poll) give the *initial* stop a 0.35 x ATR buffer against brief wicks;
   active trailing stops and candle-close checks use the exact stop.

### Safety Circuit Breakers
* **Rolling 24-hour drawdown limit** (`MAX_DAILY_DRAWDOWN_PCT`, 5%): flattens positions and pauses
  entries for `CIRCUIT_BREAKER_COOLDOWN_HOURS`. It only looks back 24 hours, so a slow multi-day
  decline is not capped by it.
* **Post-loss cooldown**: a symbol closed at a loss is locked out for 120 minutes.
* **Personal holdings are left alone**: the bot only adopts broker positions in its own trading
  list unless `ADOPT_UNMANAGED_POSITIONS=true`.
* **Optional broker backup stop** (`BROKER_BACKUP_STOP_ENABLED`, off by default): a good-till-
  cancelled stop at Trading 212, `BROKER_BACKUP_STOP_ATR_MULT` ATRs below the bot's stop, so a
  position stays protected if the bot is offline. The bot cancels it before its own exits. Test
  it in demo first: Trading 212 does not document whether stop orders accept fractional shares.
* **Spread guard**: rejects entries when bid-ask spread > `MAX_SPREAD_PCT`. Yahoo often gives no
  usable bid/ask; the spread is then estimated and marked unverified. Set
  `REQUIRE_VERIFIED_SPREAD=true` to refuse those entries.
* **Price cross-check**: open positions are managed on Trading 212's own price. If it differs
  from Yahoo by more than `MAX_BROKER_PRICE_DIVERGENCE_PCT` (3%), Yahoo is used and a warning logged.
* **Heartbeat monitoring** (`HEARTBEAT_URL`, optional): the bot pings a monitoring URL (e.g.
  healthchecks.io) after every healthy cycle and reports crashes to `<url>/fail`, so you are
  alerted if the bot or server stops.
* **Crash-safe state**: state files are written to a temporary file and swapped in, so a crash
  mid-write cannot corrupt them.

---

## 7b. Backtesting & Measuring the Strategy

```bash
python backtest.py                     # last 59 days of 15m bars across the full universe
python backtest.py --symbols NVDA_US_EQ,TSLA_US_EQ --days 30 --equity 500
python analyze.py journal              # real trade results, slippage, fill-price sources
python analyze.py scans                # do higher scores lead to better forward returns?
python analyze.py ai                   # did AI-vetoed setups do worse than approved ones?
```

* The backtester replays the same screener, strategy, risk and session code the live bot uses,
  with fills at the next bar's open plus slippage and FX fees in the account currency.
* It does not simulate the AI layer, uses one fixed FX rate, and assumes stops are hit before
  targets when both fall inside one bar.
* Yahoo only provides about 60 days of 15-minute history, so one run is one market period. Treat
  results with fewer than ~30 trades as noise.
* `--set KEY=VALUE` changes any setting for one run; `--from` / `--until` limit trading to a date
  range so a change can be tuned on one period and checked on another.
* `python research.py` tests daily strategies (trend filter, momentum rotation, dip buying) on
  ~10 years of pound-priced London ETFs. Settings are picked on 2017–2021 and judged on 2022 onwards,
  against simply holding the index. Report: `logs/research_report.md`. Code: `bot/research/`.
* The bot logs every scored candidate to `logs/scan_log.jsonl` and every AI entry decision to
  `logs/ai_entry_decisions.jsonl`; `analyze.py` turns these into the reports above.

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

### Long-Term Performance
Reads the full trade journal (not just the last 25 trades) and `logs/equity_history.jsonl`
(one equity reading every 5 minutes, seeded from old log files on first start): all-time net P&L,
average R, win rate and profit factor, drawdown from the all-time high, equity and cumulative P&L
charts, weekly results, and execution quality (slippage, fill-price sources, fees).

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
The tests cover indicators, risk sizing and currency conversion, order confirmation against a simulated broker (no duplicate orders, unconfirmed cancels, queued exits, backup stops), Trading 212 ticker translation, UK ETP fee exemptions, slot rotation, the backtester and the analysis reports.

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
