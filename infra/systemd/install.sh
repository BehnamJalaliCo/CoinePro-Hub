#!/usr/bin/env bash
# Installs (or refreshes) the CoinePro HQ systemd units and enables the timers.
# Units run as user Hub; they call scripts inside /home/Hub/CoinePro-Hub.
set -euo pipefail

UNIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNITS=(coinepro-hq-backup.service coinepro-hq-backup.timer
  coinepro-hq-openbao-unseal.service coinepro-hq-openbao-unseal.timer
  coinepro-hq-container-metrics.service coinepro-hq-container-metrics.timer
  coinepro-hq-backup-hourly.service coinepro-hq-backup-hourly.timer
  coinepro-hq-restore-weekly.service coinepro-hq-restore-weekly.timer
  coinepro-hq-mcp-index.service coinepro-hq-mcp-index.timer coinepro-hq-mcp-index.path)

# node-exporter's textfile directory (container metrics without a Docker socket).
sudo install -d -o Hub -g Hub -m 0755 /var/lib/coinepro-hq /var/lib/coinepro-hq/textfile
for unit in "${UNITS[@]}"; do
  sudo install -m 0644 "$UNIT_DIR/$unit" "/etc/systemd/system/$unit"
done
sudo systemd-analyze verify "${UNITS[@]/#//etc/systemd/system/}"
sudo systemctl daemon-reload
sudo systemctl enable --now coinepro-hq-backup.timer coinepro-hq-openbao-unseal.timer \
  coinepro-hq-container-metrics.timer coinepro-hq-backup-hourly.timer coinepro-hq-restore-weekly.timer
# Prompt 12 §14.6: CodeCortex's index (does nothing while HQ_MCP is off).
sudo systemctl enable --now coinepro-hq-mcp-index.timer coinepro-hq-mcp-index.path
systemctl list-timers 'coinepro-hq-*' --no-pager
