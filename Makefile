# CoinePro HQ — operator commands. Everything goes through infra/compose/hq.sh,
# which picks the memory profile and loads the env files.
SHELL := /usr/bin/env bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

HQ       := infra/compose/hq.sh
ENV_FILE := infra/compose/.env

.PHONY: help env profile up down ps logs backup restore-test check openbao-init unseal install-systemd

help: ## Show the available commands
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-16s %s\n", $$1, $$2}'

$(ENV_FILE):
	@infra/compose/gen-env.sh

env: $(ENV_FILE) ## Create infra/compose/.env with random secrets (never overwrites)

profile: ## Print the active memory profile (lean/full)
	@$(HQ) --print-profile

up: $(ENV_FILE) ## Start every service of the active profile and wait until healthy
	@echo "profile: $$($(HQ) --print-profile)"
	$(HQ) up -d --remove-orphans
	@infra/openbao/init.sh
	@infra/openbao/unseal.sh
	$(HQ) up -d --wait --wait-timeout 300

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

check: ## Quality gates: gitleaks, compose config, ports, memory budget, shellcheck, yamllint
	@scripts/quality/check.sh

openbao-init: ## One-time OpenBao init (keys -> /home/Hub/.secrets, never printed)
	@infra/openbao/init.sh

unseal: ## Unseal OpenBao with the stored key
	@infra/openbao/unseal.sh

install-systemd: ## Install/refresh the backup and unseal timers (needs sudo)
	@infra/systemd/install.sh
