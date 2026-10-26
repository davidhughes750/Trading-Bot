#!/usr/bin/env bash
# ==============================================================================
# Push Trading 212 Bot from MacBook to Proxmox LXC Container (or Proxmox Host)
#
# Usage Option 1 (Direct to LXC IP via SSH):
#   ./push_to_proxmox.sh root@<YOUR_LXC_IP>
#
# Usage Option 2 (Via Proxmox Host IP + LXC Container ID, no SSH needed in LXC):
#   ./push_to_proxmox.sh root@<YOUR_PROXMOX_HOST_IP> 105
# ==============================================================================
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage:"
  echo "  Option 1 (Direct to LXC SSH)     : ./push_to_proxmox.sh root@<LXC_IP>"
  echo "  Option 2 (Via Proxmox Host + CTID): ./push_to_proxmox.sh root@<PROXMOX_HOST_IP> <CT_ID>"
  exit 1
fi

TARGET_SSH="$1"
CT_ID="${2:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

echo "Packaging Trading 212 Bot files (including your .env configuration)..."
TAR_PATH="/tmp/t212_bot_bundle.tar.gz"
COPYFILE_DISABLE=1 tar -czf "${TAR_PATH}" \
  --exclude=".venv" \
  --exclude="__pycache__" \
  --exclude=".pytest_cache" \
  --exclude="logs/*.log" \
  bot/ main.py dashboard.py requirements.txt pytest.ini tests/ setup_lxc_service.sh .env .env.example

if [ -z "${CT_ID}" ]; then
  echo "Deploying directly to LXC container (${TARGET_SSH})..."
  ssh "${TARGET_SSH}" "mkdir -p /opt/trading-bot"
  scp "${TAR_PATH}" "${TARGET_SSH}:/tmp/t212_bot_bundle.tar.gz"
  ssh "${TARGET_SSH}" "tar -xzf /tmp/t212_bot_bundle.tar.gz -C /opt/trading-bot && rm -f /tmp/t212_bot_bundle.tar.gz && bash /opt/trading-bot/setup_lxc_service.sh"
else
  echo "Deploying via Proxmox Host (${TARGET_SSH}) into LXC Container ID ${CT_ID}..."
  scp "${TAR_PATH}" "${TARGET_SSH}:/tmp/t212_bot_bundle.tar.gz"
  ssh "${TARGET_SSH}" "pct exec ${CT_ID} -- mkdir -p /opt/trading-bot && pct push ${CT_ID} /tmp/t212_bot_bundle.tar.gz /tmp/t212_bot_bundle.tar.gz && rm -f /tmp/t212_bot_bundle.tar.gz && pct exec ${CT_ID} -- bash -c 'tar -xzf /tmp/t212_bot_bundle.tar.gz -C /opt/trading-bot && rm -f /tmp/t212_bot_bundle.tar.gz && bash /opt/trading-bot/setup_lxc_service.sh'"
fi

rm -f "${TAR_PATH}"
