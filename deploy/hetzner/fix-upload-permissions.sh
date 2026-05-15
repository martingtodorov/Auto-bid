#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# Quick fix for "Image storage is not writable at '/opt/autobids/uploads'
# (Permission denied)" on production. Run as root on the Hetzner box.
#
# Root cause: Ansible's `chown` on upload_dir had `recurse: no`, so any
# subdirectories pre-existing from a previous deploy (or created by root
# during a manual interaction) stayed root-owned and the systemd-managed
# `www-data` backend user can't write content-addressed sha256 files
# into them.
#
# This script is idempotent and safe to re-run.
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

UPLOAD_DIR="${UPLOAD_DIR:-/opt/autobids/uploads}"
SERVICE_USER="${SERVICE_USER:-www-data}"
SERVICE_GROUP="${SERVICE_GROUP:-www-data}"

if [[ "$EUID" -ne 0 ]]; then
  echo "ERROR: must run as root (sudo $0)" >&2
  exit 1
fi

echo "→ Ensuring $UPLOAD_DIR exists"
mkdir -p "$UPLOAD_DIR"

echo "→ Recursively chowning $UPLOAD_DIR → $SERVICE_USER:$SERVICE_GROUP"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$UPLOAD_DIR"

echo "→ Ensuring 0755 on directories, 0644 on files"
find "$UPLOAD_DIR" -type d -exec chmod 0755 {} +
find "$UPLOAD_DIR" -type f -exec chmod 0644 {} +

echo "→ Running write probe as $SERVICE_USER"
PROBE="$UPLOAD_DIR/.write-probe-$$"
if sudo -u "$SERVICE_USER" touch "$PROBE" 2>/dev/null; then
  rm -f "$PROBE"
  echo "✓ $SERVICE_USER can write to $UPLOAD_DIR"
else
  echo "✗ $SERVICE_USER STILL cannot write — inspect ACLs or parent dir perms" >&2
  ls -la "$(dirname "$UPLOAD_DIR")"
  exit 2
fi

echo "→ Restarting backend"
systemctl restart autobids-backend

echo "→ Waiting 3s for boot, then checking storage probe in logs"
sleep 3
journalctl -u autobids-backend -n 60 --no-pager | grep -i "Storage probe" | tail -3 || true

echo ""
echo "DONE. Storage probe should now show: 'Storage probe OK: backend=disk root=$UPLOAD_DIR → ...'"
