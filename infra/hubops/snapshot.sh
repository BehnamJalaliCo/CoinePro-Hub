#!/usr/bin/env bash
# The hub's memory and services as one JSON object (contract §38.3; hub.ops `stats`): the hub-ops
# dispatcher posts it to the api at most every 60 s and after each job, and the owner's «سرویس‌ها»
# page shows it. Read only: nothing on the host changes.
#   memory    total_mb (MemTotal), budget_mb (HQ_BUDGET_PERCENT, else 80%, of the profile's reference RAM, or of this
#             server's when larger: hq.sh's budget_ref), caps_mb (the active set's memory limits),
#             free_mb (budget - caps: what may still be switched on), available_mb (MemAvailable)
#   services  every compose service of every profile: its profiles, memory cap, one-shot or not,
#             state and health (hq.sh ps), memory used and CPU (docker stats)
#   switches  each optional service's switch in infra/compose/.env (on/off only; nothing else of
#             the file is read)
# Usage: snapshot.sh   (tests set HQ_SH, HQ_ENV_FILE, HQ_MEMINFO, HQ_DOCKER)
set -euo pipefail
umask 077

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_DIR="$REPO_DIR/infra/compose"
HQ="${HQ_SH:-$COMPOSE_DIR/hq.sh}"
ENV_FILE="${HQ_ENV_FILE:-$COMPOSE_DIR/.env}"
MEMINFO="${HQ_MEMINFO:-/proc/meminfo}"
DOCKER="${HQ_DOCKER:-docker}"

env_switch() { # env_switch NAME: on|off, from the environment or .env (only this one key)
  local v="${!1:-}"
  if [[ -z "$v" && -r "$ENV_FILE" ]]; then v="$(sed -n "s/^$1=//p" "$ENV_FILE" | tail -n1)"; fi
  if [[ "$v" == on ]]; then printf on; else printf off; fi
}

profile="$("$HQ" --print-profile 2>/dev/null || echo full)"
[[ "$profile" =~ ^(lean|full)$ ]] || profile=full
ref="$(sed -n 's/^HQ_BUDGET_REF_RAM_MB=//p' "$COMPOSE_DIR/profiles/$profile.env" 2>/dev/null | tail -n1)"
total="$(awk '/^MemTotal:/ {print int($2 / 1024)}' "$MEMINFO" 2>/dev/null || echo 0)"
avail="$(awk '/^MemAvailable:/ {print int($2 / 1024)}' "$MEMINFO" 2>/dev/null || echo 0)"
[[ "$ref" =~ ^[0-9]+$ ]] || ref=0
[[ "$total" =~ ^[0-9]+$ ]] || total=0
[[ "$avail" =~ ^[0-9]+$ ]] || avail=0
if ((total > ref)); then ref="$total"; fi
# The share of it, as hq.sh's budget_pct: the profile's HQ_BUDGET_PERCENT (50..90), else 80.
pct="$(sed -n 's/^HQ_BUDGET_PERCENT=//p' "$COMPOSE_DIR/profiles/$profile.env" 2>/dev/null | tail -n1)"
[[ "$pct" =~ ^[0-9]+$ ]] && ((pct >= 50 && pct <= 90)) || pct=80
budget=$((ref * pct / 100))

# Files, not arguments: a compose config is larger than one argument may be (128 KiB).
T="$(mktemp -d "${RUNTIME_DIRECTORY:-${TMPDIR:-/tmp}}/snapshot.XXXXXX")"
trap 'rm -rf "$T"' EXIT
HQ_ALL_PROFILES=1 "$HQ" config --format json >"$T/all" 2>/dev/null || echo '{}' >"$T/all"
"$HQ" config --format json >"$T/active" 2>/dev/null || echo '{}' >"$T/active"
{ "$HQ" ps --all --format json 2>/dev/null || true; } >"$T/ps.raw"
jq -cs 'if length == 1 and (.[0] | type) == "array" then .[0] else . end' "$T/ps.raw" >"$T/ps" 2>/dev/null ||
  echo '[]' >"$T/ps"
{ "$DOCKER" stats --no-stream --format '{{json .}}' 2>/dev/null || true; } >"$T/stats.raw"
jq -cs '.' "$T/stats.raw" >"$T/stats" 2>/dev/null || echo '[]' >"$T/stats"
for f in all active; do jq -e 'type == "object"' "$T/$f" >/dev/null 2>&1 || echo '{}' >"$T/$f"; done
switches="$(jq -cn \
  --arg media "$(env_switch HQ_MEDIA)" --arg tts "$(env_switch HQ_TTS)" --arg stt "$(env_switch HQ_STT)" \
  --arg ocr "$(env_switch HQ_OCR)" --arg newsletter "$(env_switch HQ_NEWSLETTER)" \
  --arg automations "$(env_switch HQ_AUTOMATIONS)" --arg mcp "$(env_switch HQ_MCP)" \
  --arg tracing "$(env_switch HQ_TRACING)" --arg substitutes "$(env_switch HQ_SUBSTITUTES)" \
  --arg substitutes_web "$(env_switch HQ_SUBSTITUTES_WEB)" \
  '{media: $media, tts: $tts, stt: $stt, ocr: $ocr, newsletter: $newsletter, automations: $automations,
    mcp: $mcp, tracing: $tracing, substitutes: $substitutes, substitutes_web: $substitutes_web}')"

jq -cn --slurpfile all_ "$T/all" --slurpfile active_ "$T/active" --slurpfile ps_ "$T/ps" \
  --slurpfile stats_ "$T/stats" --argjson switches "$switches" --arg profile "$profile" \
  --argjson total "$total" --argjson budget "$budget" --argjson avail "$avail" '
  ($all_[0]) as $all | ($active_[0]) as $active | ($ps_[0]) as $ps | ($stats_[0]) as $stats
  | def mib: (try (tonumber / 1048576 | floor) catch 0);
  def used_mib: try (
      (split(" / ")[0] | capture("^(?<n>[0-9.]+)\\s*(?<u>[A-Za-z]+)$")) as $m
      | ($m.n | tonumber) * ({"B": (1 / 1048576), "kB": (1 / 1024), "KiB": (1 / 1024), "MB": 1,
                              "MiB": 1, "GB": 1024, "GiB": 1024}[$m.u] // 0)
      | . * 10 | floor / 10) catch null;
  ($ps | map(select(type == "object")) | map({key: (.Name // ""), value: .}) | from_entries) as $byname
  | ($ps | map(select(type == "object")) | map({key: (.Service // ""), value: .}) | from_entries) as $st
  | ($stats | map(select(type == "object")) | map(. as $s | ($byname[$s.Name // ""].Service // null) as $svc
      | select($svc != null)
      | {key: $svc, value: {mem: ($s.MemUsage // "" | used_mib),
                             cpu: (try ($s.CPUPerc // "" | rtrimstr("%") | tonumber) catch null)}})
      | from_entries) as $use
  | ([($active.services // {})[] | (.deploy.resources.limits.memory // 0 | mib)] | add // 0) as $caps
  | {profile: $profile,
     memory: {total_mb: $total, budget_mb: $budget, caps_mb: $caps,
              free_mb: ([$budget - $caps, 0] | max), available_mb: $avail},
     switches: $switches,
     services: [($all.services // {}) | to_entries[]
       | {service: .key, profiles: (.value.profiles // []),
          cap_mb: (.value.deploy.resources.limits.memory // 0 | mib),
          one_shot: ((.value.restart // "no") == "no"),
          state: ($st[.key].State // "absent"), health: (($st[.key].Health // "") | if . == "" then null else . end),
          mem_used_mb: ($use[.key].mem // null), cpu_percent: ($use[.key].cpu // null)}]}'
