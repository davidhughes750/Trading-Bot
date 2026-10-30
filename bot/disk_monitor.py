"""Disk space monitoring and alerting utility for Trading 212 Quantitative Bot.

Monitors local and remote Proxmox container storage, tracks log and trade journal sizes,
and dispatches high-priority Telegram and SMTP email warnings when disk usage exceeds
the designated threshold (e.g. 80%).
"""

from __future__ import annotations

import logging
import shutil
import smtplib
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class DiskMonitor:
    """Monitors filesystem usage and manages rate-limited Telegram + Email alerts."""

    def __init__(
        self,
        target_path: str = "/",
        alert_threshold_pct: float = 80.0,
        critical_threshold_pct: float = 90.0,
        cooldown_hours: float = 6.0,
    ) -> None:
        self.target_path = target_path
        self.alert_threshold_pct = alert_threshold_pct
        self.critical_threshold_pct = critical_threshold_pct
        self.cooldown_hours = cooldown_hours
        self._last_alert_time: Optional[datetime] = None
        self._last_alerted_level: Optional[str] = None

    def get_disk_telemetry(self) -> Dict[str, Any]:
        """Query filesystem disk usage and top project directory footprints."""
        usage = shutil.disk_usage(self.target_path)
        total_gb = usage.total / (1024 ** 3)
        used_gb = usage.used / (1024 ** 3)
        free_gb = usage.free / (1024 ** 3)
        used_pct = (usage.used / usage.total) * 100.0 if usage.total > 0 else 0.0

        # Query log directory sizes
        logs_dir = Path("logs")
        journal_size_kb = 0.0
        logs_total_mb = 0.0
        if logs_dir.exists():
            journal_path = logs_dir / "trade_journal.jsonl"
            if journal_path.exists():
                journal_size_kb = journal_path.stat().st_size / 1024.0

            for f in logs_dir.glob("*"):
                if f.is_file():
                    logs_total_mb += f.stat().st_size / (1024 * 1024.0)

        status_badge = "CRITICAL 🔴" if used_pct >= self.critical_threshold_pct else (
            "WARNING 🟡" if used_pct >= self.alert_threshold_pct else "HEALTHY 🟢"
        )

        return {
            "target_path": self.target_path,
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
            "free_gb": round(free_gb, 2),
            "used_pct": round(used_pct, 1),
            "status_badge": status_badge,
            "trade_journal_kb": round(journal_size_kb, 1),
            "logs_total_mb": round(logs_total_mb, 1),
            "is_above_warning": used_pct >= self.alert_threshold_pct,
            "is_above_critical": used_pct >= self.critical_threshold_pct,
        }

    def should_alert(self, telemetry: Dict[str, Any]) -> Tuple[bool, str]:
        """Determine if an alert should be sent based on thresholds and rate-limiting."""
        used_pct = telemetry.get("used_pct", 0.0)
        if used_pct < self.alert_threshold_pct:
            return False, "HEALTHY"

        level = "CRITICAL" if used_pct >= self.critical_threshold_pct else "WARNING"
        now = datetime.now(timezone.utc)

        if self._last_alert_time is None:
            return True, level

        # If escalation from WARNING -> CRITICAL, alert immediately
        if level == "CRITICAL" and self._last_alerted_level != "CRITICAL":
            return True, level

        # Otherwise enforce cooldown
        cooldown = timedelta(hours=self.cooldown_hours if level == "WARNING" else 1.0)
        if now - self._last_alert_time >= cooldown:
            return True, level

        return False, level

    def record_alert_dispatched(self, level: str) -> None:
        """Mark the timestamp of the last dispatched alert."""
        self._last_alert_time = datetime.now(timezone.utc)
        self._last_alerted_level = level

    def format_telegram_alert(self, telemetry: Dict[str, Any]) -> str:
        """Format an actionable Telegram warning message."""
        is_crit = telemetry.get("is_above_critical", False)
        icon = "🚨" if is_crit else "⚠️"
        title = "CRITICAL DISK SPACE EXHAUSTION" if is_crit else "DISK SPACE WARNING"

        return (
            f"{icon} <b>{title}: {telemetry['used_pct']}% Used</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💾 <b>Filesystem:</b> <code>{telemetry['target_path']}</code>\n"
            f"📊 <b>Usage:</b> {telemetry['used_gb']} GB / {telemetry['total_gb']} GB (<b>{telemetry['used_pct']}%</b>)\n"
            f"🟢 <b>Available Space:</b> {telemetry['free_gb']} GB remaining\n"
            f"📁 <b>Logs Directory:</b> {telemetry['logs_total_mb']} MB (Trade Journal: {telemetry['trade_journal_kb']} KB)\n\n"
            f"💡 <i>Recommended Action: Run <code>logrotate -f /etc/logrotate.d/t212-bot</code> or expand LXC disk in Proxmox.</i>"
        )

    def format_status_message(self, telemetry: Dict[str, Any]) -> str:
        """Format routine /disk inquiry message for Telegram."""
        return (
            f"💾 <b>Proxmox Node Storage Status</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Status:</b> {telemetry['status_badge']}\n"
            f"• <b>Used:</b> <b>{telemetry['used_gb']} GB</b> of {telemetry['total_gb']} GB (<b>{telemetry['used_pct']}%</b>)\n"
            f"• <b>Available Free:</b> <b>{telemetry['free_gb']} GB</b>\n"
            f"• <b>Trade Journal:</b> {telemetry['trade_journal_kb']} KB (permanent append-only)\n"
            f"• <b>Log Footprint:</b> {telemetry['logs_total_mb']} MB\n"
            f"• <b>Threshold Alert:</b> Fires at <b>{self.alert_threshold_pct:.0f}%</b>"
        )

    def send_email_alert(
        self,
        telemetry: Dict[str, Any],
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        recipient: str,
        sender: Optional[str] = None,
        use_tls: bool = True,
    ) -> bool:
        """Dispatch a warning email via SMTP if configured."""
        if not smtp_host or not recipient or not smtp_user:
            return False

        try:
            msg = EmailMessage()
            is_crit = telemetry.get("is_above_critical", False)
            subject = f"{'🚨 [CRITICAL]' if is_crit else '⚠️ [WARNING]'} Trading Bot Disk Alert: {telemetry['used_pct']}% Used on Proxmox"
            msg["Subject"] = subject
            msg["From"] = sender or smtp_user
            msg["To"] = recipient

            text_content = (
                f"Trading 212 Quant Bot Disk Alert\n\n"
                f"Mount: {telemetry['target_path']}\n"
                f"Usage: {telemetry['used_gb']} GB / {telemetry['total_gb']} GB ({telemetry['used_pct']}%)\n"
                f"Free: {telemetry['free_gb']} GB\n"
                f"Logs Footprint: {telemetry['logs_total_mb']} MB\n\n"
                f"Please review log files or expand container disk space in Proxmox."
            )
            msg.set_content(text_content)

            html_content = f"""
            <html>
              <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1c1c1e; padding: 20px;">
                <h2 style="color: {'#ff3b30' if is_crit else '#ff9500'};">{subject}</h2>
                <div style="background: #f2f2f7; border-radius: 8px; padding: 16px; margin: 16px 0;">
                  <p><strong>Filesystem:</strong> {telemetry['target_path']}</p>
                  <p><strong>Used Space:</strong> {telemetry['used_gb']} GB / {telemetry['total_gb']} GB (<strong>{telemetry['used_pct']}%</strong>)</p>
                  <p><strong>Free Space:</strong> <span style="color: #34c759; font-weight: bold;">{telemetry['free_gb']} GB remaining</span></p>
                  <p><strong>Total Logs Size:</strong> {telemetry['logs_total_mb']} MB (Trade Journal: {telemetry['trade_journal_kb']} KB)</p>
                </div>
                <p style="font-size: 13px; color: #8e8e93;">Generated automatically by Trading 212 Quantitative Bot on Proxmox LXC.</p>
              </body>
            </html>
            """
            msg.add_alternative(html_content, subtype="html")

            if use_tls:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as server:
                    server.login(smtp_user, smtp_password)
                    server.send_message(msg)

            logger.info("Disk warning email successfully dispatched to %s", recipient)
            return True
        except Exception as exc:
            logger.error("Failed to send disk warning email to %s: %s", recipient, exc)
            return False
