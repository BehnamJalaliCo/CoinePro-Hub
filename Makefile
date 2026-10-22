# CoinePro HQ — operator commands. Everything goes through infra/compose/hq.sh,
# which picks the memory profile and loads the env files.
SHELL := /usr/bin/env bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

HQ       := infra/compose/hq.sh
ENV_FILE := infra/compose/.env

.PHONY: help env bootstrap profile up down ps logs backup restore-test check openbao-init unseal \
	install-systemd llm-provision claude-token llm-smoke test-services lock owner-enroll openapi \
	audit-reanchor verify-live bootstrap-month1 prompt-check stt-fetch stt-eval tracing-on tracing-off \
	backup-hourly restore-weekly pitr-test gdrive-auth backup-password openbao-snapshot-token mcp-secret account-secret \
	hetzner-token owner-ssh-key intake-secret telegram-bot-token connection-secret

help: ## Show the available commands
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-16s %s\n", $$1, $$2}'

$(ENV_FILE):
	@infra/compose/gen-env.sh

env: $(ENV_FILE) ## Create infra/compose/.env with random secrets (never overwrites)

bootstrap: $(ENV_FILE) ## Once (needs sudo): anchor dir + the containers' secret files; then make up needs no sudo
	@infra/backup/anchor-dir.sh
	$(HQ) up -d openbao
	@infra/openbao/init.sh
	@infra/openbao/unseal.sh
	@infra/openbao/provision.sh

profile: ## Print the active memory profile (lean/full)
	@$(HQ) --print-profile

up: $(ENV_FILE) ## Start every service of the active profile and wait until healthy
	@infra/compose/gen-env.sh
	@echo "profile: $$($(HQ) --print-profile)"
	$(HQ) up -d openbao
	@infra/openbao/init.sh
	@infra/openbao/unseal.sh
	@infra/openbao/provision.sh
	@infra/backup/anchor-dir.sh --check
	$(HQ) up -d --build --remove-orphans --wait --wait-timeout 300
	@# The hourly backup's image (own profile, nothing depends on it): built and checked here.
	$(HQ) --profile backup-tools build backup-tools
	$(HQ) --profile backup-tools run --rm --no-deps backup-tools >/dev/null

down: ## Stop and remove the containers of every profile (volumes are kept)
	HQ_ALL_PROFILES=1 $(HQ) down

ps: ## Show service status
	$(HQ) ps

logs: ## Follow logs: make logs s=<service>
	$(HQ) logs -f --tail=200 $(s)

backup: ## Dump every database now (pg_dump -Fc) into /home/Hub/backups
	@infra/backup/backup.sh

restore-test: ## Restore the latest backup into a throwaway Postgres and verify it
	@infra/backup/restore-test.sh

backup-hourly: ## Run the hourly encrypted backup now (restic: local, Google Drive when connected)
	@infra/backup/hourly.sh

restore-weekly: ## Run the weekly restore test now (newest snapshot, every check, PITR to a random moment)
	@infra/backup/restore-weekly.sh

pitr-test: ## Point-in-time recovery into a THROWAWAY Postgres: at="2026-10-18 09:41" (UTC)
	@[[ -n "$(at)" ]] || { echo 'usage: make pitr-test at="YYYY-MM-DD HH:MM[:SS] [zone]"' >&2; exit 2; }
	@infra/backup/pitr.sh "$(at)"

gdrive-auth: ## OWNER: connect the hourly backup to Google Drive: a link, then the address (step=link|code; own=1 = your own OAuth client)
	@GDRIVE_OWN_CLIENT=$(own) infra/backup/gdrive-auth.sh $(step)

backup-password: ## OWNER: show the restic password once, in your own terminal, for the paper copy
	@infra/backup/show-password.sh

openbao-snapshot-token: ## OWNER: store your OpenBao snapshot-only token (hidden input -> OpenBao)
	@infra/openbao/snapshot-token.sh

bootstrap-month1: ## Month-1 setup work (seed/bootstrap/month1.yaml) as service "bootstrap"; wakes real runs
	$(HQ) exec -T worker python -m hq_api.bootstrap month1

prompt-check: ## One REAL call with a charter's prompt (role=advisor): schema and answer checked, nothing stored
	@infra/compose/hq.sh exec -T worker python -m hq_api.agents.check_prompt "$(or $(role),advisor)" \
	  <"$${HQ_SECRETS_DIR:-/home/Hub/.secrets}/llm-router-caller-hq-ops.token"

tracing-on: ## Switch traces on: opt-in profile "tracing" (Tempo + otel-collector), refused over the memory budget
	@infra/compose/set-env.sh HQ_TRACING on
	$(HQ) up -d --wait tempo otel-collector prometheus

tracing-off: ## Switch traces off again (the default): Tempo and the collector stop, Prometheus stops scraping them
	@infra/compose/set-env.sh HQ_TRACING off
	HQ_ALL_PROFILES=1 $(HQ) stop tempo otel-collector
	$(HQ) up -d --wait prometheus

stt-fetch: ## Download the pinned speech model into the stt-models volume (sha256-checked; model=large-v3-turbo)
	HQ_STT=off $(HQ) --profile stt build stt-fetch
	HQ_STT=off $(HQ) --profile stt run --rm -e STT_MODEL="$(or $(model),large-v3-turbo)" stt-fetch

stt-eval: ## WER of the speech model on dir=<samples> (<name>.<audio> + <name>.txt), offline; write=1 saves a report
	@[[ -d "$(dir)" ]] || { echo "usage: make stt-eval dir=<samples folder> [model=large-v3-turbo] [write=1]" >&2; exit 2; }
	@out="$$(docker run --rm --network none --read-only --tmpfs /tmp --cap-drop ALL --user 10001:10001 \
	  --memory 2304m -e STT_MODEL="$(or $(model),large-v3-turbo)" -v coinepro-hq_stt-models:/models:ro \
	  -v "$(abspath $(dir)):/samples:ro" coinepro-hq/stt:0.1.0 python -m hq_stt.eval /samples \
	  $(if $(write),--markdown))"; printf '%s\n' "$$out"; \
	if [[ -n "$(write)" ]]; then f="docs/ops/reports/stt-eval-$$(date -u +%Y-%m-%d).md"; \
	  printf '%s\n' "$$out" >"$$f"; echo "stt-eval: wrote $$f"; fi

audit-reanchor: ## After a DB restore: re-anchor the audit chain (typed confirmation + audit row): reason="..."
	@infra/backup/audit-reanchor.sh "$(reason)"

check: ## Quality gates: gitleaks, compose config, ports, memory budget, shellcheck, yamllint
	@scripts/quality/check.sh

verify-live: ## Live checks on the running stack: network isolation, no parameters in the Postgres log
	@scripts/quality/live.sh

openbao-init: ## One-time OpenBao init (keys -> /home/Hub/.secrets, never printed)
	@infra/openbao/init.sh

unseal: ## Unseal OpenBao with the stored key
	@infra/openbao/unseal.sh

install-systemd: ## Install/refresh the backup and unseal timers (needs sudo)
	@infra/systemd/install.sh

llm-provision: ## OpenBao: KV, policies, AppRoles, service tokens (idempotent)
	@infra/openbao/provision.sh

claude-token: ## OWNER: store the token from `claude setup-token` in OpenBao (hidden input)
	@infra/openbao/claude-token.sh

mcp-secret: ## OWNER: the secret of one MCP server, KEY=<server key> [FILE=<json key file>] (-> OpenBao)
	@infra/openbao/mcp-secret.sh "$(KEY)" "$(FILE)"

account-secret: ## OWNER: the secret of one holding service account (KEY=<key>; hidden input)
	@infra/openbao/account-secret.sh "$(KEY)"

connection-secret: ## OWNER: a new LLM connection's API key (KEY=<key>; hidden input -> OpenBao)
	@infra/openbao/connection-secret.sh "$(KEY)"

hetzner-token: ## OWNER: the Hetzner project's API token for new servers (hidden input -> OpenBao)
	@infra/openbao/hetzner-token.sh

owner-ssh-key: ## OWNER: add one of your PUBLIC SSH keys for new servers' work user (-> OpenBao)
	@infra/openbao/owner-ssh-key.sh

intake-secret: ## OWNER: an intake source's HMAC secret, COMPANY=<code> SOURCE=chatwoot|product (hidden)
	@infra/openbao/intake-secret.sh "$(COMPANY)" "$(SOURCE)"

telegram-bot-token: ## OWNER: a support channel's bot token, COMPANY=<code> CHANNEL=telegram_bot|telegram_business
	@infra/openbao/telegram-bot-token.sh "$(COMPANY)" "$(CHANNEL)"

llm-smoke: ## One tiny real call (Haiku, "OK") + ledger row + NATS event
	@services/scripts/llm-smoke.sh

test-services: ## Python services: lint, types, tests (throwaway Postgres/NATS)
	@scripts/quality/services.sh

lock: ## Re-resolve the hash-pinned Python lock files
	@services/scripts/lock.sh

owner-enroll: ## OWNER: one-time passkey enrolment link (printed only in your terminal; also recovery)
	$(HQ) exec api python -m hq_api.enroll

openapi: ## Rewrite apps/api/openapi/hq-api.v1.json from the code (CI checks it matches)
	@scripts/quality/python.sh openapi
