from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import requests
import pandas as pd

if TYPE_CHECKING:
    from bot.config import Config

logger = logging.getLogger("bot.telegram_notifier")


class TelegramNotifier:
    """Delivers rich push notifications, embedded candlestick charts, and remote commands via Telegram."""

    def __init__(self, config: "Config") -> None:
        self.config = config
        self.enabled = bool(
            config.enable_telegram
            and config.telegram_bot_token
            and config.telegram_chat_id
        )
        self.token = config.telegram_bot_token.strip()
        self.chat_id = str(config.telegram_chat_id).strip()
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        # Money amounts (risk, P&L, fees) are in the account currency; prices in the instrument's.
        self.acct_ccy = {"GBP": "£", "USD": "$", "EUR": "€"}.get(config.account_currency, "")

    @staticmethod
    def _format_sym_and_ccy(symbol: str) -> tuple[str, str]:
        """Return `(display_ticker, currency_symbol)` for US (`$`) vs UK (`£`) symbols."""
        s = str(symbol or "")
        if s.endswith("_UK_EQ"):
            return s.replace("_UK_EQ", ".L"), "£"
        return s.replace("_US_EQ", "").replace("_US", ""), "$"

    def register_bot_commands(self) -> bool:
        """Register the interactive `/` command menu in the Telegram app."""
        if not self.enabled:
            return False
        try:
            commands = [
                {"command": "recommendations", "description": "🔍 Top ranked stock recommendations (US + UK)"},
                {"command": "screener", "description": "🔍 Top ranked screener leaderboard"},
                {"command": "positions", "description": "📦 Active open positions, SL/TP & live PnL"},
                {"command": "status", "description": "📊 Portfolio equity, cash, US & UK market state"},
                {"command": "disk", "description": "💾 Proxmox node disk storage & logs usage"},
                {"command": "uk", "description": "🇬🇧 UK 3x Leveraged ETPs (QQQ3, 3LUS, 3NVD, 3TSL...)"},
                {"command": "chart", "description": "🕯️ 15m Candlestick chart (e.g. /chart QQQ3 or /chart NVDA)"},
                {"command": "summary", "description": "📈 Executive Daily Summary & PnL chart"},
                {"command": "help", "description": "🤖 Show all bot commands"},
            ]
            resp = requests.post(
                f"{self.base_url}/setMyCommands",
                json={"commands": commands},
                timeout=8,
            )
            return resp.status_code == 200
        except Exception as exc:
            logger.debug("Could not register Telegram command menu: %s", exc)
            return False

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send a formatted text alert."""
        if not self.enabled:
            return False
        try:
            resp = requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("Failed to send Telegram message: %s", exc)
            return False

    def send_photo(self, photo_bytes: io.BytesIO, caption: str, parse_mode: str = "HTML") -> bool:
        """Send a photo with a formatted caption (splitting if caption exceeds Telegram's 1024-char limit)."""
        if not self.enabled:
            return False
        try:
            photo_bytes.seek(0)
            is_long_caption = len(caption) > 1000
            photo_caption = (
                "\n".join(caption.splitlines()[:2])
                if is_long_caption
                else caption
            )
            resp = requests.post(
                f"{self.base_url}/sendPhoto",
                data={
                    "chat_id": self.chat_id,
                    "caption": photo_caption,
                    "parse_mode": parse_mode,
                },
                files={"photo": ("chart.png", photo_bytes, "image/png")},
                timeout=15,
            )
            if resp.status_code != 200:
                logger.warning("Telegram sendPhoto returned %d: %s; falling back to text", resp.status_code, resp.text)
                return self.send_message(caption, parse_mode=parse_mode)
            if is_long_caption:
                return self.send_message(caption, parse_mode=parse_mode)
            return True
        except Exception as exc:
            logger.warning("Failed to send Telegram photo: %s; falling back to text", exc)
            return self.send_message(caption, parse_mode=parse_mode)

    def generate_candlestick_chart(
        self,
        symbol: str,
        df: Optional[pd.DataFrame] = None,
        entry_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        exit_price: Optional[float] = None,
        title_suffix: str = "",
        bars_to_show: int = 35,
    ) -> Optional[io.BytesIO]:
        """Generate a high-contrast dark-mode candlestick chart with indicator overlays."""
        if df is None or len(df) < 5:
            return None

        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from matplotlib.lines import Line2D
            from matplotlib.patches import Rectangle
            import numpy as np

            data = df.tail(bars_to_show).copy().reset_index(drop=True)
            n_bars = len(data)
            if n_bars < 5:
                return None

            # Create 2 subplots: Price (top) and Volume (bottom)
            fig, (ax1, ax2) = plt.subplots(
                2, 1, figsize=(9.5, 5.5),
                gridspec_kw={"height_ratios": [3.5, 1.2]},
                facecolor="#0b0f19",
                sharex=True,
            )

            for ax in (ax1, ax2):
                ax.set_facecolor("#111827")
                ax.tick_params(colors="#9ca3af", labelsize=8.5)
                for spine in ax.spines.values():
                    spine.set_color("#374151")
                ax.grid(True, linestyle=":", alpha=0.35, color="#4b5563")

            clean_sym, ccy = self._format_sym_and_ccy(symbol)

            # Draw Candlesticks on ax1
            up_color = "#10b981"    # emerald
            down_color = "#ef4444"  # rose red
            wick_width = 1.2
            candle_width = 0.65

            for i, row in data.iterrows():
                o = float(row["open"])
                h = float(row["high"])
                l = float(row["low"])
                c = float(row["close"])
                is_up = c >= o
                color = up_color if is_up else down_color

                # High/low wick
                ax1.plot([i, i], [l, h], color=color, linewidth=wick_width, zorder=2)

                # Real body
                body_bottom = min(o, c)
                body_height = max(abs(c - o), (h - l) * 0.03 if h > l else 0.01)
                rect = Rectangle(
                    (i - candle_width / 2, body_bottom),
                    candle_width,
                    body_height,
                    facecolor=color,
                    edgecolor=color,
                    linewidth=0.8,
                    zorder=3,
                )
                ax1.add_patch(rect)

                # Draw Volume Bar on ax2
                v = float(row.get("volume", 0))
                ax2.bar(i, v, width=candle_width, color=color, alpha=0.75, zorder=2)

            # Draw EMA Overlays if available
            legend_handles = []
            if "ema_fast" in data.columns and data["ema_fast"].notna().any():
                ax1.plot(data.index, data["ema_fast"], color="#38bdf8", linewidth=1.6, label="EMA 20", zorder=4)
                legend_handles.append(Line2D([0], [0], color="#38bdf8", lw=1.6, label="EMA 20"))
            elif "close" in data.columns:
                ema20 = data["close"].ewm(span=20, adjust=False).mean()
                ax1.plot(data.index, ema20, color="#38bdf8", linewidth=1.6, label="EMA 20", zorder=4)
                legend_handles.append(Line2D([0], [0], color="#38bdf8", lw=1.6, label="EMA 20"))

            if "ema_slow" in data.columns and data["ema_slow"].notna().any():
                ax1.plot(data.index, data["ema_slow"], color="#c084fc", linewidth=1.6, label="EMA 50", zorder=4)
                legend_handles.append(Line2D([0], [0], color="#c084fc", lw=1.6, label="EMA 50"))
            elif "close" in data.columns:
                ema50 = data["close"].ewm(span=50, adjust=False).mean()
                ax1.plot(data.index, ema50, color="#c084fc", linewidth=1.6, label="EMA 50", zorder=4)
                legend_handles.append(Line2D([0], [0], color="#c084fc", lw=1.6, label="EMA 50"))

            # Draw Entry, Stop Loss, and Take Profit levels
            if entry_price is not None:
                ax1.axhline(entry_price, color="#34d399", linestyle="--", linewidth=1.4, alpha=0.9, zorder=5)
                legend_handles.append(Line2D([0], [0], color="#34d399", linestyle="--", lw=1.4, label=f"Entry {ccy}{entry_price:.2f}"))

            if stop_loss is not None:
                ax1.axhline(stop_loss, color="#f87171", linestyle="--", linewidth=1.4, alpha=0.9, zorder=5)
                legend_handles.append(Line2D([0], [0], color="#f87171", linestyle="--", lw=1.4, label=f"SL {ccy}{stop_loss:.2f}"))

            if take_profit is not None:
                ax1.axhline(take_profit, color="#fbbf24", linestyle="--", linewidth=1.4, alpha=0.9, zorder=5)
                legend_handles.append(Line2D([0], [0], color="#fbbf24", linestyle="--", lw=1.4, label=f"TP {ccy}{take_profit:.2f}"))

            if exit_price is not None:
                ax1.axhline(exit_price, color="#a78bfa", linestyle="-.", linewidth=1.5, alpha=0.95, zorder=5)
                legend_handles.append(Line2D([0], [0], color="#a78bfa", linestyle="-.", lw=1.5, label=f"Exit {ccy}{exit_price:.2f}"))

            # Title & Formatting
            title_text = f"{clean_sym} • 15m Trend Following {title_suffix}".strip()
            ax1.set_title(title_text, color="#f3f4f6", fontsize=11, fontweight="bold", pad=8)
            ax1.set_ylabel(f"Price ({ccy})", color="#9ca3af", fontsize=8.5)
            ax2.set_ylabel("Vol", color="#9ca3af", fontsize=8.5)
            ax2.set_xlabel("Recent 15-Minute Bars", color="#9ca3af", fontsize=8.5)

            if legend_handles:
                ax1.legend(
                    handles=legend_handles,
                    loc="upper left",
                    facecolor="#1f2937",
                    edgecolor="#374151",
                    labelcolor="#e5e7eb",
                    fontsize=7.5,
                    framealpha=0.85,
                )

            plt.subplots_adjust(hspace=0.08)

            buf = io.BytesIO()
            plt.savefig(buf, format="png", dpi=130, bbox_inches="tight", facecolor=fig.get_facecolor())
            plt.close(fig)
            buf.seek(0)
            return buf
        except Exception as exc:
            logger.warning("[%s] Failed to generate candlestick chart: %s", symbol, exc)
            return None

    def send_trade_opened_alert(
        self,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        risk_amount: float = 0.0,
        risk_pct: float = 0.0,
        score: float = 0.0,
        rating: str = "STRONG BUY",
        rvol: float = 1.0,
        spread_pct: float = 0.0,
        thesis: str = "",
        df: Optional[pd.DataFrame] = None,
        notional: Optional[float] = None,
    ) -> bool:
        """Send a rich position entry alert with embedded candlestick chart.

        `risk_amount` and `notional` are in account currency.
        """
        if not self.enabled:
            return False

        clean_sym, ccy = self._format_sym_and_ccy(symbol)
        acct = self.acct_ccy
        if notional is None:
            notional = qty * entry_price
        sl_pct = abs(entry_price - stop_loss) / entry_price * 100.0 if entry_price > 0 else 0.0
        tp_pct = abs(take_profit - entry_price) / entry_price * 100.0 if entry_price > 0 else 0.0
        rr = (take_profit - entry_price) / max(entry_price - stop_loss, 0.0001)

        caption = (
            f"🟢 <b>POSITION OPENED: {clean_sym} ({side})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>Entry Price:</b> {ccy}{entry_price:.2f}\n"
            f"📦 <b>Position Size:</b> {qty:.4f} shares ({acct}{notional:.2f})\n"
            f"🛡️ <b>Stop-Loss:</b> {ccy}{stop_loss:.2f} (-{sl_pct:.2f}%)\n"
            f"🎯 <b>Take-Profit:</b> {ccy}{take_profit:.2f} (+{tp_pct:.2f}%)\n"
            f"⚖️ <b>Risk:</b> {acct}{risk_amount:.2f} ({risk_pct:.2f}% eq) • R/R 1:{rr:.1f}\n"
            f"📊 <b>Quant Score:</b> {score:.1f}/100 ({rating})\n"
            f"⚡ <b>RVOL:</b> {rvol:.2f}x avg • <b>Spread:</b> {spread_pct*100:.3f}%\n"
        )
        if thesis:
            clean_thesis = thesis.replace("<", "&lt;").replace(">", "&gt;")
            caption += f"💡 <b>Thesis:</b> {clean_thesis}\n"

        photo = self.generate_candlestick_chart(
            symbol=symbol,
            df=df,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            title_suffix=f"Entry ({ccy}{entry_price:.2f})",
        )
        if photo is not None:
            return self.send_photo(photo, caption)
        return self.send_message(caption)

    def send_trade_closed_alert(
        self,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        exit_price: float,
        net_pnl: float,
        pnl_pct: float,
        r_multiple: float,
        held_minutes: int,
        reason: str,
        df: Optional[pd.DataFrame] = None,
        fee_paid: float = 0.0,
        gross_pnl: Optional[float] = None,
    ) -> bool:
        """Send a rich position exit alert with net PnL and chart (P&L and fees in account currency)."""
        if not self.enabled:
            return False

        clean_sym, ccy = self._format_sym_and_ccy(symbol)
        acct = self.acct_ccy
        is_profit = net_pnl >= 0.0
        header_emoji = "🎯 <b>PROFIT TARGET HIT</b>" if "Take-Profit" in reason else (
            "🛡️ <b>TRAILING STOP HIT</b>" if "Trailing" in reason else (
                "✅ <b>POSITION CLOSED IN PROFIT</b>" if is_profit else "🛑 <b>STOP-LOSS HIT</b>"
            )
        )
        pnl_emoji = "🟢" if is_profit else "🔴"
        pnl_sign = "+" if net_pnl >= 0 else "-"

        hours = held_minutes // 60
        mins = held_minutes % 60
        held_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"

        fee_line = ""
        if fee_paid > 0:
            gross_val = gross_pnl if gross_pnl is not None else (net_pnl + fee_paid)
            gross_sign = "+" if gross_val >= 0 else "-"
            fee_line = f"💸 <b>Fees:</b> -{acct}{fee_paid:.2f} (Gross: {gross_sign}{acct}{abs(gross_val):.2f})\n"
        elif str(symbol).endswith("_UK_EQ"):
            fee_line = "💸 <b>FX / Stamp Duty:</b> £0.00 (0% UK ETP Exemption)\n"

        caption = (
            f"{header_emoji}: <b>{clean_sym}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{pnl_emoji} <b>Net PnL:</b> {pnl_sign}{acct}{abs(net_pnl):.2f} ({pnl_pct:+.2f}%)\n"
            f"{fee_line}"
            f"🎯 <b>R-Multiple:</b> {r_multiple:+.2f}R\n"
            f"🚪 <b>Exit Reason:</b> {reason}\n"
            f"⏱️ <b>Hold Duration:</b> {held_str}\n"
            f"💵 <b>Entry:</b> {ccy}{entry_price:.2f} ➔ <b>Exit:</b> {ccy}{exit_price:.2f}\n"
            f"📦 <b>Quantity:</b> {qty:.4f} shares\n"
        )

        photo = self.generate_candlestick_chart(
            symbol=symbol,
            df=df,
            entry_price=entry_price,
            exit_price=exit_price,
            title_suffix=f"Exit ({pnl_sign}{acct}{abs(net_pnl):.2f})",
        )
        if photo is not None:
            return self.send_photo(photo, caption)
        return self.send_message(caption)

    def send_circuit_breaker_alert(
        self, daily_drawdown_pct: Any, threshold_pct: Optional[float] = None
    ) -> bool:
        """Send critical circuit breaker alert."""
        if not self.enabled:
            return False
        if isinstance(daily_drawdown_pct, str):
            detail = daily_drawdown_pct
        else:
            th = threshold_pct or 0.05
            detail = (
                f"Portfolio rolling 24h drawdown reached <b>{daily_drawdown_pct*100:.2f}%</b> "
                f"(threshold: {th*100:.2f}%)."
            )
        text = (
            f"🚨 <b>HARD CIRCUIT BREAKER TRIGGERED</b> 🚨\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{detail}\n"
            f"Automated trade entries are HALTED to protect equity.\n"
        )
        return self.send_message(text)

    def send_breakeven_alert(
        self,
        symbol: str,
        entry_price: float,
        stop_price: float,
        current_price: float,
    ) -> bool:
        """Send a single high-value milestone alert when a position becomes 100% risk-free."""
        if not self.enabled:
            return False
        clean_sym, ccy = self._format_sym_and_ccy(symbol)
        text = (
            f"🛡️ <b>TRADE NOW RISK-FREE: {clean_sym}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Trailing Stop locked at Entry:</b> {ccy}{stop_price:.2f}\n"
            f"• <b>Current Market Price:</b> {ccy}{current_price:.2f}\n"
            f"• Downside risk is completely eliminated. Remaining upside runs with the trend!"
        )
        return self.send_message(text)

    def send_trailing_ratchet_alert(
        self,
        symbol: str,
        old_stop: float,
        new_stop: float,
        high_price: float,
        r_multiple: float,
    ) -> bool:
        """Deprecated/Silenced to prevent phone spam on 15s micro-ticks."""
        return False

    def generate_daily_summary_chart(
        self,
        date_str: str,
        closed_trades: List[Dict[str, Any]],
        open_positions: List[Dict[str, Any]],
        total_equity: float,
    ) -> Optional[io.BytesIO]:
        """Generate a sleek dark-mode performance chart for the daily summary."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(8.5, 4.2), facecolor="#0b0f19")
            ax.set_facecolor("#111827")
            ax.tick_params(colors="#9ca3af", labelsize=8.5)
            for spine in ax.spines.values():
                spine.set_color("#374151")
            ax.grid(True, linestyle=":", alpha=0.35, color="#4b5563")

            labels = []
            values = []
            colors = []

            for t in closed_trades:
                sym = t.get("symbol", "").replace("_US_EQ", "").replace("_US", "")
                pnl = float(t.get("net_pnl", 0.0))
                labels.append(f"{sym}\n(Closed)")
                values.append(pnl)
                colors.append("#10b981" if pnl >= 0 else "#ef4444")

            for p in open_positions:
                sym = p.get("symbol", "").replace("_US_EQ", "").replace("_US", "")
                pnl = float(p.get("unrealized_pnl", 0.0))
                labels.append(f"{sym}\n(Open)")
                values.append(pnl)
                colors.append("#34d399" if pnl >= 0 else "#f87171")

            if not labels:
                labels = ["Cash\nReserve"]
                values = [0.0]
                colors = ["#38bdf8"]

            bars = ax.bar(labels, values, color=colors, width=0.48, zorder=3)
            ax.axhline(0, color="#6b7280", linewidth=1.0, linestyle="--", alpha=0.7)

            for bar, val in zip(bars, values):
                sign = "+" if val >= 0 else ""
                y_pos = val + (0.1 if val >= 0 else -0.2)
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    y_pos,
                    f"{sign}{self.acct_ccy}{abs(val):.2f}",
                    ha="center",
                    va="bottom" if val >= 0 else "top",
                    color="#f3f4f6",
                    fontsize=9,
                    fontweight="bold",
                )

            ax.set_title(
                f"Daily Trading Performance & PnL • {date_str} (Equity: {self.acct_ccy}{total_equity:,.2f})",
                color="#f3f4f6",
                fontsize=11,
                fontweight="bold",
                pad=10,
            )
            ax.set_ylabel("Net PnL ($)", color="#9ca3af", fontsize=9)

            buf = io.BytesIO()
            plt.savefig(buf, format="png", dpi=130, bbox_inches="tight", facecolor=fig.get_facecolor())
            plt.close(fig)
            buf.seek(0)
            return buf
        except Exception as exc:
            logger.warning("Failed to generate daily summary chart: %s", exc)
            return None

    def send_daily_summary(
        self,
        date_str: str,
        total_equity: float,
        free_cash: float,
        daily_realized_pnl: float,
        unrealized_pnl: float,
        closed_trades_today: List[Dict[str, Any]],
        open_positions: List[Dict[str, Any]],
        market_regime: str,
        top_picks: List[Dict[str, Any]],
    ) -> bool:
        """Send comprehensive end-of-day executive teardown to Telegram."""
        if not self.enabled:
            return False

        comb_pnl = daily_realized_pnl + unrealized_pnl
        comb_pnl_pct = (comb_pnl / max(total_equity - comb_pnl, 1.0)) * 100.0
        pnl_sign = "+" if daily_realized_pnl >= 0 else ""
        unreal_sign = "+" if unrealized_pnl >= 0 else ""
        comb_sign = "+" if comb_pnl >= 0 else ""
        comb_emoji = "🟢" if comb_pnl >= 0 else "🔴"
        mode_str = self.config.execution_mode.upper()

        a = self.acct_ccy  # money amounts are in account currency
        lines = [
            f"📊 <b>EXECUTIVE DAILY TRADING SUMMARY</b>",
            f"🗓️ <b>Session:</b> {date_str} • <b>Mode:</b> {mode_str}",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"💰 <b>FINANCIAL PERFORMANCE</b>",
            f"• <b>Total Equity:</b> {a}{total_equity:,.2f}",
            f"• <b>Free Cash:</b> {a}{free_cash:,.2f} ({(free_cash/max(total_equity,1.0))*100:.1f}%)",
            f"• <b>Realized PnL Today:</b> {pnl_sign}{a}{abs(daily_realized_pnl):.2f}",
            f"• <b>Open Unrealized:</b> {unreal_sign}{a}{abs(unrealized_pnl):.2f}",
            f"• <b>Day Combined PnL:</b> {comb_emoji} <b>{comb_sign}{a}{abs(comb_pnl):.2f}</b> ({comb_pnl_pct:+.2f}%)",
            f"",
        ]

        # Closed Trades Section
        lines.append(f"📈 <b>TRADES CLOSED TODAY ({len(closed_trades_today)})</b>")
        if closed_trades_today:
            for t in closed_trades_today:
                sym, _ = self._format_sym_and_ccy(t.get("symbol", ""))
                p = float(t.get("net_pnl", 0.0))
                p_pct = float(t.get("pnl_pct", 0.0))
                r_m = float(t.get("r_multiple", 0.0))
                em = "🟢" if p >= 0 else "🔴"
                s = "+" if p >= 0 else ""
                lines.append(
                    f"• {em} <b>{sym}</b>: {s}{a}{abs(p):.2f} ({p_pct:+.2f}%, {r_m:+.2f}R)\n"
                    f"  Reason: {t.get('reason', 'N/A')}"
                )
        else:
            lines.append("• <i>No positions closed today.</i>")
        lines.append("")

        # Active Overnight Runway
        lines.append(f"📦 <b>ACTIVE OVERNIGHT POSITIONS ({len(open_positions)}/{self.config.max_open_positions})</b>")
        if open_positions:
            for p in open_positions:
                sym, c = self._format_sym_and_ccy(p.get("symbol", ""))
                cur_p = float(p.get("current_price", 0.0))
                entry_p = float(p.get("entry_price", 0.0))
                unreal = float(p.get("unrealized_pnl", 0.0))
                unreal_pct = float(p.get("pnl_pct", 0.0))
                r_m = float(p.get("r_multiple", 0.0))
                em = "🟢" if unreal >= 0 else "🔴"
                s = "+" if unreal >= 0 else ""
                lines.append(
                    f"• {em} <b>{sym}</b>: {p.get('quantity', 0):.4f} shs @ {c}{entry_p:.2f} (Now {c}{cur_p:.2f})\n"
                    f"  PnL: <b>{s}{a}{abs(unreal):.2f}</b> ({unreal_pct:+.2f}%, {r_m:+.2f}R)\n"
                    f"  SL: {c}{float(p.get('stop_loss', 0.0)):.2f} | TP: {c}{float(p.get('take_profit', 0.0)):.2f}"
                )
        else:
            lines.append("• <i>100% Cash — no open overnight positions.</i>")
        lines.append("")

        # Watchlist Radar
        if top_picks:
            lines.append("🔭 <b>TOP MOMENTUM RADAR FOR TOMORROW</b>")
            for r in top_picks[:3]:
                sym = r.get("symbol", "").replace("_US_EQ", "").replace("_US", "")
                lines.append(f"• <b>{sym}</b>: {r.get('score', 0):.1f}/100 ({r.get('rating')}) | RVOL {r.get('rvol', 1.0):.1f}x")
            lines.append("")

        lines.append(f"🏛️ <b>Market Regime:</b> {market_regime}")
        lines.append(f"🤖 <i>Trading 212 Quantitative Daemon</i>")

        caption = "\n".join(lines)
        photo = self.generate_daily_summary_chart(
            date_str=date_str,
            closed_trades=closed_trades_today,
            open_positions=open_positions,
            total_equity=total_equity,
        )
        if photo is not None:
            return self.send_photo(photo, caption)
        return self.send_message(caption)
