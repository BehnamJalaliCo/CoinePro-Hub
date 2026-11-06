#!/usr/bin/env bash
# Masks secrets in a command's output before it leaves the hub host (contract §38.1; the
# hub masks it again with hq_common.redact). A filter: stdin -> stdout, nothing else.
#   by name   KEY=value, KEY: value and "key": "value" whose key names a secret (PASSWORD,
#             SECRET, TOKEN, API_KEY, PRIVATE_KEY, CREDENTIALS, PASSPHRASE), Authorization
#             headers, Bearer/Basic credentials, a password inside a URL
#   by shape  PEM private keys (whole blocks), Anthropic/OpenAI, GitHub, GitLab, Slack, AWS,
#             Google, Stripe, OpenBao/Vault, npm, Telegram bot tokens, JWTs, hq agent tokens
# Usage: some-command | mask.sh
set -euo pipefail
LC_ALL=C
export LC_ALL

M='[redacted]'
KEYS='[A-Za-z0-9_.-]*(PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|APIKEY|PRIVATE_?KEY|CREDENTIALS?|PASSPHRASE)[A-Za-z0-9_.-]*'
B='(^|[^A-Za-z0-9_])' # what may stand before a token shape
SHAPES='sk-ant-[A-Za-z0-9_-]{16,}|sk-(proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}'
SHAPES+='|glpat-[A-Za-z0-9_-]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|(AKIA|ASIA)[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}'
SHAPES+='|(sk|rk|pk)_(live|test)_[A-Za-z0-9]{16,}|hv[sbr]\.[A-Za-z0-9_-]{20,}|npm_[A-Za-z0-9]{36}'
SHAPES+='|hq[ar]1[_.-][A-Za-z0-9_.-]{16,}|eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'
SHAPES+='|[0-9]{8,10}:AA[A-Za-z0-9_-]{30,}'

awk -v m="$M" '
  /-----BEGIN [A-Z0-9 ]*PRIVATE KEY( BLOCK)?-----/ { print m " (private key)"; skip = 1; next }
  skip && /-----END [A-Z0-9 ]*PRIVATE KEY( BLOCK)?-----/ { skip = 0; next }
  skip { next }
  { print }
' | sed -E \
  -e "s/((proxy-)?authorization[[:space:]]*[:=][[:space:]]*[\"']?)((bearer|basic|token|digest)[[:space:]]+)?[^[:space:]\"',;]+/\1\3$M/Ig" \
  -e "s/(^|[^A-Za-z0-9_])(bearer|basic)([[:space:]]+)[A-Za-z0-9._~+\/=-]{8,}/\1\2\3$M/Ig" \
  -e "s#([A-Za-z][A-Za-z0-9+.-]{1,20}://[^/[:space:]:@]{1,256}:)[^@[:space:]/]{1,256}@#\1$M@#g" \
  -e "s/(\"$KEYS\"[[:space:]]*:[[:space:]]*)\"[^\"]*\"/\1\"$M\"/Ig" \
  -e "s/(^|[^A-Za-z0-9_.-])(${KEYS}[[:space:]]*(=|:[[:space:]])[[:space:]]*)(\"[^\"]*\"|'[^']*'|[^[:space:],;&|\"']+)/\1\2$M/Ig" \
  -e "s/(--?(password|passwd|pass|token|secret|api-key|apikey|access-key|secret-key|auth-token|client-secret)(=|[[:space:]]+))(\"[^\"]*\"|'[^']*'|[^[:space:]]+)/\1$M/Ig" \
  -e "s/$B($SHAPES)/\1$M/g"
