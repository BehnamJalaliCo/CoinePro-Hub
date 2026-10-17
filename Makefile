# CoinePro HQ — operator commands. Everything goes through infra/compose/hq.sh,
# which picks the memory profile and loads the env files.
SHELL := /usr/bin/env bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

HQ       := infra/compose/hq.sh
ENV_FILE := infra/compose/.env

.PHONY: help env bootstrap profile up down ps logs backup restore-test check openbao-init unseal \
	install-systemd llm-provision claude-token llm-smoke test-services lock owner-enroll openapi \
	audit-reanchor verify-live bootstrap-month1

help: ## Show the available commands
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-16s %s\n", $$1, $$2}'

$(ENV_FILE):
	@infra/compose/gen-env.sh

env: $(ENV_FILE) ## Create infra/compose/.env with random secrets (never overwrites)

bootstrap: $(ENV_FILE) ## Once (needs sudo): anchor dir + the containers' secret files; then make up needs no sudo
	@infra/backup/anchor-dir.sh
	$(HQ) up -d --wait openbao
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

bootstrap-month1: ## Month-1 setup work (seed/bootstrap/month1.yaml) as service "bootstrap"; wakes real runs
	$(HQ) exec -T worker python -m hq_api.bootstrap month1

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
