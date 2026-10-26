#!/usr/bin/env bash
# ==============================================================================
# Trading 212 Bot — Proxmox LXC Automated Provisioning & Systemd Setup Script
# Run inside your Debian/Ubuntu Proxmox LXC container as root:
#   bash /opt/trading-bot/setup_lxc_service.sh
# ==============================================================================
set -euo pipefail

BOT_DIR="/opt/trading-bot"
SERVICE_NAME="t212-bot"

if [ ! -x "${BOT_DIR}/.venv/bin/python" ]; then
  echo "============================================================"
  echo "  1. Installing system packages (Python 3, venv, pip)..."
  echo "============================================================"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y python3 python3-venv python3-pip ca-certificates tzdata iproute2

  # Ensure UK timezone for accurate log timestamps
  timedatectl set-timezone Europe/London 2>/dev/null || ln -sf /usr/share/zoneinfo/Europe/London /etc/localtime

  echo "============================================================"
  echo "  2. Building Python virtual environment in ${BOT_DIR}..."
  echo "============================================================"
  cd "${BOT_DIR}"
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
else
  echo "============================================================"
  echo "  Existing .venv detected in ${BOT_DIR} — applying fast update"
  echo "============================================================"
fi

mkdir -p "${BOT_DIR}/logs"

echo "============================================================"
echo "  3. Creating systemd daemon (${SERVICE_NAME}.service)..."
echo "============================================================"
cat <<EOF > /etc/systemd/system/${SERVICE_NAME}.service
[Unit]
Description=Trading 212 Quantitative Trading Bot & Web Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=${BOT_DIR}
Environment="PYTHONUNBUFFERED=1"
ExecStart=${BOT_DIR}/.venv/bin/python ${BOT_DIR}/main.py
Restart=always
RestartSec=10
StandardOutput=append:${BOT_DIR}/logs/systemd.log
StandardError=append:${BOT_DIR}/logs/systemd.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
pkill -f "dashboard.py" 2>/dev/null || true
systemctl restart ${SERVICE_NAME}

LXC_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "============================================================"
echo "  SUCCESS! Trading 212 Bot is running 24/7 on Proxmox LXC"
echo "============================================================"
echo "  Service Status : systemctl status ${SERVICE_NAME}"
echo "  Live Bot Logs  : tail -f ${BOT_DIR}/logs/trading_bot.log"
echo "  Web Dashboard  : http://${LXC_IP}:8050"
echo "============================================================"
