#!/usr/bin/env bash
# ==============================================================================
# Deploy the Trading 212 bot from this Mac to the Proxmox LXC container.
#
#   ./push_to_proxmox.sh root@<LXC_IP> [options]
#
# What it does (direct SSH mode):
#   1. Packages a git revision (default HEAD, so what runs on the server is what is in git) and runs
#      the test suite on exactly that code. Your local .env is added to the bundle.
#   2. Refuses to deploy while the bot holds open positions, or if the server's .env has settings
#      your local .env lacks (use --force to override). Shows which settings will change.
#   3. Backs up the live code, swaps in the new code, restarts, and waits for a healthy cycle
#      (service active, a fresh equity line in the log, dashboard answering).
#   4. If the health check fails it rolls back to the backup automatically and exits non-zero.
#
# Options:
#   --rev <git-rev>   deploy this commit instead of HEAD
#   --dirty           deploy the working tree (uncommitted changes included)
#   --force           deploy even with open positions / dropped .env settings
#   --skip-tests      do not run the tests first
#   --dry-run         run every check, change nothing on the server
#
# Test hook:  T212_DEPLOY_FAULT=smoke ./push_to_proxmox.sh ...   makes the first health check fail,
#             to prove the rollback path works.
#
# Legacy mode (no safety checks):  ./push_to_proxmox.sh root@<PROXMOX_HOST> <CT_ID>
# ==============================================================================
set -euo pipefail

usage() { sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }
[ $# -ge 1 ] || usage

TARGET_SSH="$1"; shift
CT_ID=""
if [ $# -ge 1 ] && [[ "$1" =~ ^[0-9]+$ ]]; then CT_ID="$1"; shift; fi

REV="HEAD"; DIRTY=0; FORCE=0; SKIP_TESTS=0; DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --rev) REV="$2"; shift 2 ;;
    --dirty) DIRTY=1; shift ;;
    --force) FORCE=1; shift ;;
    --skip-tests) SKIP_TESTS=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1" >&2; usage ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"
FAULT="${T212_DEPLOY_FAULT:-none}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)
MANAGED=(bot web tests deploy main.py dashboard.py backtest.py analyze.py requirements.txt pytest.ini setup_lxc_service.sh .env.example DEPLOYED_REV)

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# ------------------------------------------------------------------------------
# Legacy mode: through the Proxmox host with `pct` (kept for completeness, no safety checks)
# ------------------------------------------------------------------------------
if [ -n "${CT_ID}" ]; then
  echo "WARNING: legacy pct mode has no tests, backup or rollback."
  umask 077
  TAR_PATH="$(mktemp -t t212_bundle).tar.gz"
  trap 'rm -f "${TAR_PATH}"' EXIT
  COPYFILE_DISABLE=1 tar -czf "${TAR_PATH}" --exclude=".venv" --exclude="__pycache__" --exclude=".pytest_cache" --exclude="logs/*.log" \
    bot/ main.py dashboard.py backtest.py analyze.py web/ requirements.txt pytest.ini tests/ setup_lxc_service.sh .env .env.example
  scp "${TAR_PATH}" "${TARGET_SSH}:/tmp/t212_bot_bundle.tar.gz"
  ssh "${TARGET_SSH}" "pct exec ${CT_ID} -- mkdir -p /opt/trading-bot && pct push ${CT_ID} /tmp/t212_bot_bundle.tar.gz /tmp/t212_bot_bundle.tar.gz && rm -f /tmp/t212_bot_bundle.tar.gz && pct exec ${CT_ID} -- bash -c 'tar -xzf /tmp/t212_bot_bundle.tar.gz -C /opt/trading-bot && rm -f /tmp/t212_bot_bundle.tar.gz && chmod 600 /opt/trading-bot/.env && bash /opt/trading-bot/setup_lxc_service.sh'"
  exit 0
fi

# ------------------------------------------------------------------------------
# 1. Stage the code to deploy (private temp dir, removed on exit)
# ------------------------------------------------------------------------------
WORK="$(mktemp -d -t t212_deploy.XXXXXX)"   # mktemp creates it private (0700); files inside keep normal modes
trap 'rm -rf "${WORK}"' EXIT
STAGE="${WORK}/stage"; mkdir -p "${STAGE}"
PYTHON="${SCRIPT_DIR}/.venv/bin/python"; [ -x "${PYTHON}" ] || PYTHON="python3"

if [ "${DIRTY}" -eq 1 ]; then
  say "Staging the working tree (including uncommitted changes)"
  git ls-files -co --exclude-standard -z | xargs -0 tar -cf - 2>/dev/null | tar -xf - -C "${STAGE}"
  REV_LABEL="$(git rev-parse --short HEAD)+dirty"
else
  if ! git diff --quiet HEAD -- 2>/dev/null; then
    echo "Note: you have uncommitted changes. Deploying commit $(git rev-parse --short "${REV}") as committed (use --dirty to include them)."
  fi
  say "Staging git revision ${REV} ($(git rev-parse --short "${REV}"))"
  git archive "${REV}" | tar -xf - -C "${STAGE}"
  REV_LABEL="$(git rev-parse --short "${REV}")"
fi
echo "${REV_LABEL} $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${STAGE}/DEPLOYED_REV"
[ -f "${SCRIPT_DIR}/.env" ] || die "No .env next to this script"

# ------------------------------------------------------------------------------
# 2. Tests on the staged code
# ------------------------------------------------------------------------------
if [ "${SKIP_TESTS}" -eq 1 ]; then
  echo "Skipping tests (--skip-tests)"
else
  say "Running the test suite on the staged code"
  # Run inside the staging dir (not the repo) and before .env is copied in, so the tests never see real secrets
  if ! ( cd "${STAGE}" && EXECUTION_MODE=paper "${PYTHON}" -m pytest -q -p no:cacheprovider ) > "${WORK}/tests.log" 2>&1; then
    tail -25 "${WORK}/tests.log"
    die "Tests failed; nothing was deployed"
  fi
  tail -2 "${WORK}/tests.log"
fi
cp "${SCRIPT_DIR}/.env" "${STAGE}/.env"

# ------------------------------------------------------------------------------
# 3. Pre-flight checks on the server (read-only)
# ------------------------------------------------------------------------------
say "Checking the server (${TARGET_SSH})"
ssh "${SSH_OPTS[@]}" "${TARGET_SSH}" 'test -d /opt/trading-bot' || die "/opt/trading-bot not found on the server (first install? use legacy mode)"

POSITIONS="$(ssh "${SSH_OPTS[@]}" "${TARGET_SSH}" "python3 -c \"import json;print(' '.join(json.load(open('/opt/trading-bot/logs/t212_state.json')).get('positions',{})))\" 2>/dev/null || echo UNKNOWN")"
if [ -n "${POSITIONS}" ]; then
  echo "Open positions on the server: ${POSITIONS}"
  if [ "${FORCE}" -ne 1 ]; then die "Refusing to restart the bot while it holds positions (use --force to override)"; fi
else
  echo "No open positions."
fi

# Compare settings. Secrets are compared by hash and never printed.
ssh "${SSH_OPTS[@]}" "${TARGET_SSH}" 'python3 - <<"PY"
import hashlib, json, re
out = {}
for line in open("/opt/trading-bot/.env", encoding="utf-8", errors="replace"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    out[k.strip()] = v.strip()
secret = re.compile(r"KEY|SECRET|TOKEN|PASSWORD|CHAT_ID|URL", re.I)
print(json.dumps({k: ["", hashlib.sha256(v.encode()).hexdigest()] if secret.search(k) else [v, hashlib.sha256(v.encode()).hexdigest()] for k, v in out.items()}))
PY' > "${WORK}/server_env.json" 2>/dev/null || echo '{}' > "${WORK}/server_env.json"

ENV_REPORT="$("${PYTHON}" - "${SCRIPT_DIR}/.env" "${WORK}/server_env.json" <<'PY'
import hashlib, json, re, sys
local = {}
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); local[k.strip()] = v.strip()
server = json.load(open(sys.argv[2]))
secret = re.compile(r"KEY|SECRET|TOKEN|PASSWORD|CHAT_ID|URL", re.I)
only_server = sorted(set(server) - set(local))
changed = [k for k in local if k in server and hashlib.sha256(local[k].encode()).hexdigest() != server[k][1]]
added = sorted(set(local) - set(server))
for k in changed:
    print(f"CHANGED {k}" + ("" if secret.search(k) else f": {server[k][0]} -> {local[k]}"))
for k in added:
    print(f"ADDED {k}" + ("" if secret.search(k) else f"={local[k]}"))
for k in only_server:
    print(f"DROPPED {k}")
PY
)"
if [ -z "${ENV_REPORT}" ]; then echo ".env: identical to the server's."; else echo ".env differences (local -> server):"; echo "${ENV_REPORT}" | sed 's/^/  /'; fi
if echo "${ENV_REPORT}" | grep -q '^DROPPED' && [ "${FORCE}" -ne 1 ]; then
  die "The server's .env has settings your local .env lacks (listed as DROPPED). Add them locally or use --force"
fi

if [ "${DRY_RUN}" -eq 1 ]; then
  say "Dry run complete: checks passed, nothing was changed on the server (would deploy ${REV_LABEL})."
  exit 0
fi

# ------------------------------------------------------------------------------
# 4. Bundle, upload, install, health-check, roll back on failure
# ------------------------------------------------------------------------------
say "Uploading ${REV_LABEL}"
BUNDLE="${WORK}/bundle.tgz"
ITEMS=(); for m in "${MANAGED[@]}"; do [ -e "${STAGE}/${m}" ] && ITEMS+=("${m}"); done   # older revisions lack some folders
( cd "${STAGE}" && COPYFILE_DISABLE=1 tar -czf "${BUNDLE}" --exclude='__pycache__' --exclude='.DS_Store' "${ITEMS[@]}" .env )
REMOTE_BUNDLE="/tmp/t212_bundle_$$.tgz"
ssh "${SSH_OPTS[@]}" "${TARGET_SSH}" "umask 077; cat > ${REMOTE_BUNDLE}" < "${BUNDLE}"

say "Installing on the server"
set +e
ssh "${SSH_OPTS[@]}" "${TARGET_SSH}" bash -s -- "${REMOTE_BUNDLE}" "${FAULT}" "${REV_LABEL}" <<'REMOTE'
set -uo pipefail
BUNDLE="$1"; FAULT="$2"; REV="$3"
# Kept inside the script rather than passed as an argument: an older setup script ran `pkill -f dashboard.py`,
# which would also kill this shell if that file name appeared in its command line.
MANAGED=(bot web tests deploy main.py dashboard.py backtest.py analyze.py requirements.txt pytest.ini setup_lxc_service.sh .env.example DEPLOYED_REV)
BOT=/opt/trading-bot; REL=/root/t212-releases; STAMP="$(date -u +%Y%m%d-%H%M%S)"; PRE="$REL/pre-$STAMP.tgz"
exec 9>/tmp/t212-deploy.lock; flock -n 9 || { echo "Another deploy is running"; exit 2; }
umask 077; mkdir -p "$REL"; cd "$BOT"

echo "-- backing up the live code to $PRE"
existing=(); for m in "${MANAGED[@]}" .env; do [ -e "$m" ] && existing+=("$m"); done
tar -czf "$PRE" "${existing[@]}" && tar -tzf "$PRE" >/dev/null || { echo "backup failed; aborting before any change"; rm -f "$BUNDLE"; exit 2; }
umask 022   # the backup is private (made under umask 077); the installed code gets normal permissions

echo "-- checking the new code before touching the live folder"
STAGE="$(mktemp -d /tmp/t212-stage.XXXXXX)"; trap 'rm -rf "$STAGE" "$BUNDLE"' EXIT
tar -xzf "$BUNDLE" -C "$STAGE" 2>/dev/null
( cd "$STAGE" && "$BOT/.venv/bin/python" -m compileall -q bot main.py dashboard.py backtest.py analyze.py >/dev/null ) || { echo "new code does not compile; aborting"; exit 2; }
if ! cmp -s "$STAGE/requirements.txt" "$BOT/requirements.txt"; then
  echo "-- requirements changed: installing dependencies"
  "$BOT/.venv/bin/pip" install -q -r "$STAGE/requirements.txt" || { echo "pip install failed; aborting"; exit 2; }
fi
( cd "$STAGE" && EXECUTION_MODE=paper "$BOT/.venv/bin/python" -c "import main, dashboard" ) || { echo "new code does not import; aborting"; exit 2; }

health() {  # $1 = epoch seconds taken before the restart, $2 = fault to inject
  local since="$1" fault="$2" i
  [ "$fault" = "smoke" ] && { echo "   (fault injected: pretending the health check failed)"; return 1; }
  for i in $(seq 1 30); do
    sleep 5
    systemctl is-active --quiet t212-bot || continue
    if python3 - "$since" <<'PY'
import datetime, json, re, sys, urllib.request
since = float(sys.argv[1])
line = ""
for l in open("/opt/trading-bot/logs/trading_bot.log", errors="replace").readlines()[-400:]:
    if "Total Equity=" in l:
        line = l
m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
assert m, "no equity line in the log yet"
assert datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp() > since, "no cycle since the restart"
d = json.load(urllib.request.urlopen("http://127.0.0.1:8050/api/mobile", timeout=10))
assert d.get("portfolio"), "dashboard feed has no portfolio"
PY
    then return 0; fi
  done
  return 1
}

install_tree() {  # $1 = tarball
  local m
  for m in bot web tests deploy; do rm -rf "$BOT/$m"; done   # remove files that no longer exist upstream
  tar -xzf "$1" -C "$BOT" 2>/dev/null
  chown -R root:root "$BOT"/bot "$BOT"/web "$BOT"/tests "$BOT"/deploy "$BOT"/*.py "$BOT"/.env 2>/dev/null
  chmod 600 "$BOT/.env"
}

echo "-- installing $REV"
install_tree "$BUNDLE"
bash "$BOT/setup_lxc_service.sh" >/tmp/t212-setup.log 2>&1 || { echo "setup script failed (see /tmp/t212-setup.log)"; tail -5 /tmp/t212-setup.log; }
SINCE="$(date +%s)"   # taken after the restart, so only the new process can satisfy the health check
echo "-- waiting for a healthy cycle (up to 150 s)"
if health "$SINCE" "$FAULT"; then
  echo "HEALTHY: $(cat $BOT/DEPLOYED_REV)"
  ls -1t "$REL"/pre-*.tgz 2>/dev/null | tail -n +6 | xargs -r rm -f   # keep the 5 most recent backups
  exit 0
fi

echo "!! health check FAILED; rolling back to $PRE"
journalctl -u t212-bot -n 15 --no-pager -o cat 2>/dev/null | tail -8 | sed 's/^/   log: /'
install_tree "$PRE"
bash "$BOT/setup_lxc_service.sh" >/tmp/t212-setup.log 2>&1
SINCE="$(date +%s)"
if health "$SINCE" none; then echo "ROLLED BACK and healthy again: $(cat $BOT/DEPLOYED_REV 2>/dev/null || echo previous version)"; exit 3; fi
echo "!! ROLLBACK ALSO FAILED: manual attention needed (backup at $PRE)"; exit 4
REMOTE
STATUS=$?
set -e
ssh "${SSH_OPTS[@]}" "${TARGET_SSH}" "rm -f ${REMOTE_BUNDLE}" || true

case "${STATUS}" in
  0) say "Deployed ${REV_LABEL}. Dashboard: http://${TARGET_SSH#*@}:8050   Phone: http://${TARGET_SSH#*@}:8050/m" ;;
  3) die "Deploy of ${REV_LABEL} FAILED its health check and was rolled back; the previous version is running again." ;;
  *) die "Deploy of ${REV_LABEL} failed (exit ${STATUS}). Check the server: systemctl status t212-bot" ;;
esac
