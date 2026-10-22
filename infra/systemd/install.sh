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
  coinepro-hq-tts.service coinepro-hq-tts.timer)

# node-exporter's textfile directory (container metrics without a Docker socket).
sudo install -d -o Hub -g Hub -m 0755 /var/lib/coinepro-hq /var/lib/coinepro-hq/textfile
# /run/hq: the lock the one-shots share (the hourly backup, the TTS pass; prompt 12 §4).
sudo install -m 0644 "$UNIT_DIR/coinepro-hq-oneshot.conf" /etc/tmpfiles.d/coinepro-hq-oneshot.conf
sudo systemd-tmpfiles --create /etc/tmpfiles.d/coinepro-hq-oneshot.conf
for unit in "${UNITS[@]}"; do
  sudo install -m 0644 "$UNIT_DIR/$unit" "/etc/systemd/system/$unit"
done
sudo systemd-analyze verify "${UNITS[@]/#//etc/systemd/system/}"
sudo systemctl daemon-reload
sudo systemctl enable --now coinepro-hq-backup.timer coinepro-hq-openbao-unseal.timer \
  coinepro-hq-container-metrics.timer coinepro-hq-backup-hourly.timer coinepro-hq-restore-weekly.timer
# coinepro-hq-tts.timer is installed, not enabled: `make tts-on` enables it (opt-in).
systemctl list-timers 'coinepro-hq-*' --no-pager
