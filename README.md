# 📈 Trading 212 Quantitative Trading Bot & Web Dashboard

An institutional-grade, multi-asset quantitative trading bot and real-time glassmorphism web dashboard engineered for **Trading 212** (Invest & Stocks ISA accounts).

Built in Python with zero heavy web framework bloat, this engine pairs a high-precision algorithmic trend-following strategy with an automated stock screener, Gemini AI catalyst analysis, strict risk controls, and an Apple-inspired dark/light responsive workstation.

> 📚 **Complete Documentation & Operations Manual**: For a comprehensive deep-dive into the mathematics, multi-market partition (`3 US + 1 UK`), 71-asset universe, AI slot rotation, Telegram controls, and Proxmox deployment, see the [**Complete Technical Wiki (`WIKI.md`)**](WIKI.md).

---

## 🌟 Key Features

### 1. 🎯 Quantitative Trading Strategy
* **Dual-EMA Trend Following**: Rapid signal identification via configurable exponential moving averages (e.g. EMA 20 / EMA 50) with volume confirmation.
* **RSI Momentum Filtering**: Long entries require dynamic RSI thresholds (e.g. RSI > 50) to prevent buying into exhausted momentum.
* **ATR Volatility Sizing**: Dynamic stop-loss and take-profit targets scaled strictly according to Average True Range (ATR).
* **Trailing Stop Engine**: Ratchets stop prices upward as unrealized profit expands, locking in gains during sustained rallies.
* **Anti-Whipsaw Protection**: Built-in overextension guard (rejects entries if price has drifted too far from the EMA baseline) and post-loss cooldown timers.

### 2. 🔍 Dynamic Stock Screener & Scorer
* **Multi-Ticker Market Scanner**: Continuously monitors a liquid universe of high-beta US equities (NVDA, TSLA, PLTR, AMD, AAPL, etc.).
* **Composite Ranking Score (0–100)**: Evaluates trend slope, Relative Volume (RVOL), RSI position, and ATR expansion.
* **Autonomous Slot Rotation**: Automatically rotates underperforming portfolio slots into higher-scoring screener opportunities.

### 3. 🧠 AI Portfolio Manager & Catalyst Engine
* **Google Gemini Integration**: Evaluates recent corporate headlines and macroeconomic catalysts using Google Gemini (`gemini-2.5-flash`).
* **Deterministic Quant Fallback**: Operates autonomously with a built-in algorithmic keyword scoring engine if no Gemini API key is configured.

### 4. 🖥️ Apple-Inspired Glassmorphism Dashboard
* **Real-Time Workstation**: Native responsive dark & light modes, live ticker tape, KPI performance metrics, portfolio heatmaps, sector diversification donuts, and interactive trade runways.
* **Interactive Candlestick Modal**: Deep-dive charts with toggleable EMA 20/50 bands, volume subplots, and dynamic resolution scaling.
* **1-Click Executive PDF Teardown**: Export boardroom-ready, page-break-safe PDF performance briefings (`Cmd + P` or `P`).
* **Subtle Audio & Haptics**: Synthesized audio feedback for order fills, circuit breakers, and mode toggles.

### 5. 🛡️ Risk Management & Circuit Breakers
* **Safe Order Handling**: Order submissions are never retried blindly; fills are confirmed against the Trading 212 position, and real fill prices and fees come from the broker's order history.
* **Account-Currency Sizing**: Risk, position size and P&L are calculated in your account currency (GBP by default), converting US prices at the live exchange rate.
* **Spread Guard**: Rejects entries when the bid-ask spread exceeds `MAX_SPREAD_PCT`. Estimated spreads (no usable quote) are flagged, and can be refused with `REQUIRE_VERIFIED_SPREAD=true`.
* **Rolling 24h Circuit Breaker**: Flattens and pauses entries if equity falls more than `MAX_DAILY_DRAWDOWN_PCT` (5%) within 24 hours.
* **Leaves Your Own Holdings Alone**: Only positions in the bot's trading list are managed.
* **Optional Broker Backup Stop**: A stop order held at Trading 212 in case the bot goes offline (off by default; test in demo first).
* **Long-Only Safety Gate**: Compliant with Trading 212 Invest and Stocks ISA cash account restrictions (no naked shorting).

### 6. 🔬 Backtesting & Measurement
* **`python backtest.py`**: Replays the same screener, strategy and risk rules over the last ~59 days of 15-minute bars with fees, slippage and portfolio limits.
* **`python analyze.py scans | ai | journal`**: Checks whether higher scores lead to better returns, whether AI vetoes help, and summarises real trades, slippage and fill sources.

---

## 🏗️ Project Architecture

```
├── bot/
│   ├── ai_manager.py       # Gemini LLM & deterministic news catalyst analysis
│   ├── analysis.py         # Reports from scan log, AI decision log and trade journal
│   ├── backtest.py         # Historical replay of the live rules
│   ├── config.py           # Typed environment variable loader & safety validations
│   ├── data_handler.py     # Yahoo Finance bars/quotes and EMA, RSI, ATR indicators
│   ├── disk_monitor.py     # Disk usage alerts
│   ├── fx.py               # Converts USD prices into the account currency
│   ├── market_calendar.py  # US holidays/early closes and US/UK session windows
│   ├── models.py           # Position, TradePlan, OrderResult and other data types
│   ├── order_executor.py   # Order placement, fill confirmation, trade journal
│   ├── risk_manager.py     # Position sizing, slot/score rules, circuit breaker
│   ├── screener.py         # 0-100 scoring and recommendations
│   ├── strategy_engine.py  # Entry/exit signals, trailing stops, market regime
│   ├── t212_client.py      # Trading 212 REST API client (Demo & Live)
│   ├── telegram_notifier.py# Telegram alerts and charts
│   └── utils.py            # Crash-safe file writes, JSONL helpers
├── analyze.py              # CLI: python analyze.py scans | ai | journal | all
├── backtest.py             # CLI: python backtest.py --help
├── dashboard.py            # HTTP server for the web dashboard
├── main.py                 # Bot daemon orchestrator & poll loop
├── web/                    # Dashboard HTML, CSS and JavaScript
├── push_to_proxmox.sh      # 1-command deployment script to Proxmox LXC
├── setup_lxc_service.sh    # Automated Debian/Ubuntu systemd service installer
├── tests/                  # pytest suite (no network access needed)
├── .env.example            # Environment configuration template (NO SECRETS)
├── requirements.txt        # Python dependencies (major versions capped)
└── pytest.ini              # Pytest configuration
```

---

## 🚀 Quickstart Guide

### 1. Clone Repository & Setup Virtual Environment
```bash
git clone https://github.com/<your-username>/<your-repo-name>.git
cd <your-repo-name>

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and insert your credentials:
```bash
cp .env.example .env
```

Open `.env` and configure your settings:
```ini
# Execution Mode ('demo', 'paper', or 'live')
EXECUTION_MODE=demo
LIVE_TRADING_CONFIRMED=false

# Trading 212 API Credentials (from Settings -> API in T212 app)
T212_API_KEY=your_trading_212_api_key_here
T212_API_SECRET=your_trading_212_api_secret_here

# (Optional) Google Gemini API Key for AI Catalyst Engine
GEMINI_API_KEY=your_gemini_api_key_here
```

> ⚠️ **IMPORTANT**: Never commit your `.env` file to source control. The repository's `.gitignore` automatically excludes `.env`.

### 3. Run Unit Tests
Runs offline against a simulated broker and synthetic price data:
```bash
pytest -v
```

### 3b. Backtest Before Changing Strategy Settings
```bash
python backtest.py              # ~30 seconds for the full universe
python backtest.py --help       # options: --symbols, --days, --equity, --min-score, --fx
```

### 4. Launch Locally
Start the trading engine and web dashboard together:
```bash
python main.py
```
Open your browser to:
```
http://localhost:8050
```

---

## 🐧 24/7 Daemon Deployment (Proxmox LXC / Ubuntu / Debian)

This repository includes turnkey automated provisioning for 24/7 headless operation on a Proxmox LXC container or generic Linux VPS.

### Deploy from your local machine:
```bash
# Direct to LXC container IP via SSH:
./push_to_proxmox.sh root@<YOUR_LXC_IP>

# Or via Proxmox Host IP and LXC Container ID:
./push_to_proxmox.sh root@<YOUR_PROXMOX_HOST_IP> <YOUR_CONTAINER_ID>
```

The script automatically:
1. Packages the project bundle.
2. Transfers files to `/opt/trading-bot` on the destination.
3. Provisions a Python 3 virtual environment and installs dependencies.
4. Registers and enables `t212-bot.service` under systemd.
5. Launches the background daemon with auto-restart on failure.

Check service status on the Linux host:
```bash
systemctl status t212-bot
journalctl -u t212-bot -f
```

---

## ⌨️ Dashboard Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| **`T`** | Toggle Light / Dark Apple theme |
| **`M`** | Toggle Sound effects & audio haptics |
| **`R`** | Force instant market & screener refresh |
| **`P`** or **`⌘P`** | Export 1-Click Executive PDF Teardown Briefing |
| **`ESC`** | Close interactive modals / candlestick views |
| **`?`** | Open Keyboard Shortcuts HUD |

---

## 📱 iPhone & Apple Watch Telegram Integration

The bot includes native integration with Telegram to deliver real-time push alerts and remote commands directly to your pocket:

* **Instant Buy / Sell Alerts**: Sends structured trade cards with entry price, risk sizing, stop-loss, take-profit, and volume surge metrics.
* **Embedded Candlestick Charts**: Automatically renders a high-contrast 15-minute candlestick chart with **EMA 20/50**, **Entry**, **SL**, and **TP** overlays directly in the notification thumbnail.
* **Trailing Stop Ratchet Alerts**: Pushes updates whenever a position reaches +1.0R and the trailing stop moves upward to lock in profits.
* **Two-Way Remote Commands**: Text your bot anytime from iOS or Apple Watch:
  * `/status` — View current total equity, cash balance, and session status.
  * `/positions` — Inspect active positions, unrealized PnL, and current R-multiples.
  * `/chart DKNG` — Request an on-demand live 15m candlestick chart for any ticker.
  * `/screener` — View top 5 highest-ranked quantitative candidates.
  * `/help` — List all available commands.

---

## 🔒 Security & Best Practices

* **Zero Hardcoded Secrets**: All keys, passwords, and tokens are read strictly from environment variables at runtime.
* **Practice First**: Always validate new configurations in `EXECUTION_MODE=demo` or `EXECUTION_MODE=paper` before allocating live capital.
* **Live Trading Double-Confirmation**: `EXECUTION_MODE=live` requires setting `LIVE_TRADING_CONFIRMED=true` in `.env` to prevent accidental real-money order submissions.

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.

---

## ⚠️ Disclaimer

*This software is provided for educational, research, and algorithmic trading development purposes only. Financial trading involves substantial risk of loss. The authors assume no liability for financial losses incurred through the use of this software.*
