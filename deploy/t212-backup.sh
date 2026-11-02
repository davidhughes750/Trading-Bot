#!/usr/bin/env bash
# Daily backup of the bot's irreplaceable data (trade journal, state, equity history, decision logs, .env).
# Archives go to /root/t212-backups (outside /opt/trading-bot so deploys never touch them); 14 days are kept.
set -euo pipefail
BOT_DIR="${BOT_DIR:-/opt/trading-bot}"
DEST="${DEST:-/root/t212-backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"

umask 077
mkdir -p "$DEST"
cd "$BOT_DIR"
stamp="$(date -u +%Y%m%d-%H%M%S)"
out="$DEST/t212-$stamp.tgz"

files=()
for f in .env logs/trade_journal.jsonl logs/t212_state.json logs/risk_state.json logs/equity_history.jsonl \
         logs/scan_log.jsonl logs/ai_entry_decisions.jsonl logs/ai_decisions.json logs/loss_postmortems.json; do
  [ -f "$f" ] && files+=("$f")
done
[ "${#files[@]}" -gt 0 ] || { echo "nothing to back up" >&2; exit 1; }

tar -czf "$out.tmp" "${files[@]}"
mv "$out.tmp" "$out"
# A backup that cannot be read back is worthless: check it before deleting old ones
tar -tzf "$out" >/dev/null
find "$DEST" -name 't212-*.tgz' -mtime +"$KEEP_DAYS" -delete
echo "backup ok: $out ($(du -h "$out" | cut -f1), ${#files[@]} files)"
