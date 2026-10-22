# shellcheck shell=bash
# shellcheck disable=SC2154  # the values block of the rendered script sets them
# chatwoot (prompt 10 §10): Chatwoot Community Edition for one company's
# website chat, on its OWN small server (2 vCPU / 4 GB), never on the hub.
# The `-ce` image is Chatwoot's Community build (MIT): the enterprise folder
# is not in it and nothing here enables it. Images pinned by tag AND digest.
# Secrets (SECRET_KEY_BASE, the database and Redis passwords) are made HERE,
# on the new server, 0600 root: none is in this template or the user data.
# Nothing starts at build time: the public name is the owner's choice, so the
# owner runs `sudo chatwoot-start <domain>` once DNS points at this server
# (Caddy then gets the certificate over TLS-ALPN on 443; only 443 is open).
CW_DIR=/opt/chatwoot
CW_VERSION=v4.18.0-ce
CW_IMAGE="chatwoot/chatwoot:v4.18.0-ce@sha256:faaa58a911cda8f2ab9d717ddf8ca4332163b07da4c5da10711d896e5d667442"
CW_PG_IMAGE="pgvector/pgvector:0.8.1-pg16@sha256:33198da2828a14c30348d2ccb4750833d5ed9a44c88d840a0e523d7417120337"
CW_REDIS_IMAGE="redis:7.4.5-alpine@sha256:bb186d083732f669da90be8b0f975a37812b15e913465bb14d845db72a4e3e08"
CW_CADDY_IMAGE="caddy:2.11.7-alpine@sha256:24ec7b05bc532c7bb57f727030c5056e257ff7138b4b50460306819ff79362bd"

step_chatwoot() {
  if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    log "chatwoot: docker compose is missing (the docker step runs before this one)"
    return 1
  fi
  install -d -m 0750 "$CW_DIR"
  (
    umask 077
    if [[ ! -s "$CW_DIR/.env" ]]; then
      # Made once; a second run keeps them (the database already uses them).
      {
        printf 'SECRET_KEY_BASE=%s\n' "$(openssl rand -hex 64)"
        printf 'POSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 24)"
        printf 'REDIS_PASSWORD=%s\n' "$(openssl rand -hex 24)"
        printf 'FRONTEND_URL=\n'
      } >"$CW_DIR/.env"
    fi
    chmod 0600 "$CW_DIR/.env"
  )
  cat >"$CW_DIR/chatwoot.env" <<'ENV'
# Chatwoot Community (MIT): no enterprise edition, no public sign-up, no telemetry.
RAILS_ENV=production
NODE_ENV=production
INSTALLATION_ENV=docker
RAILS_LOG_TO_STDOUT=true
LOG_LEVEL=info
DEFAULT_LOCALE=fa
ENABLE_ACCOUNT_SIGNUP=false
DISABLE_TELEMETRY=true
ACTIVE_STORAGE_SERVICE=local
POSTGRES_HOST=postgres
POSTGRES_USERNAME=postgres
POSTGRES_USER=postgres
POSTGRES_DATABASE=chatwoot_production
POSTGRES_DB=chatwoot_production
REDIS_URL=redis://redis:6379
ENV
  cat >"$CW_DIR/docker-compose.yml" <<YAML
# Chatwoot $CW_VERSION (Community, MIT) — written by the CoinePro HQ provisioner.
# Memory limits for a 2 vCPU / 4 GB server: rails 800M, sidekiq 700M,
# postgres 512M, redis 128M, caddy 64M (2.2 GB together).
name: chatwoot
services:
  rails:
    image: $CW_IMAGE
    env_file: [chatwoot.env, .env]
    entrypoint: docker/entrypoints/rails.sh
    command: ["bundle", "exec", "rails", "s", "-p", "3000", "-b", "0.0.0.0"]
    ports: ["127.0.0.1:3000:3000"]
    volumes: ["storage:/app/storage"]
    depends_on: [postgres, redis]
    mem_limit: 800m
    restart: unless-stopped
  sidekiq:
    image: $CW_IMAGE
    env_file: [chatwoot.env, .env]
    command: ["bundle", "exec", "sidekiq", "-C", "config/sidekiq.yml"]
    volumes: ["storage:/app/storage"]
    depends_on: [postgres, redis]
    mem_limit: 700m
    restart: unless-stopped
  postgres:
    image: $CW_PG_IMAGE
    env_file: [chatwoot.env, .env]
    volumes: ["postgres:/var/lib/postgresql/data"]
    mem_limit: 512m
    restart: unless-stopped
  redis:
    image: $CW_REDIS_IMAGE
    env_file: [.env]
    command: ["sh", "-c", "exec redis-server --requirepass \"\$\$REDIS_PASSWORD\" --maxmemory 96mb"]
    volumes: ["redis:/data"]
    mem_limit: 128m
    restart: unless-stopped
  caddy:
    image: $CW_CADDY_IMAGE
    ports: ["443:443"]
    volumes: ["./Caddyfile:/etc/caddy/Caddyfile:ro", "caddy:/data"]
    depends_on: [rails]
    mem_limit: 64m
    restart: unless-stopped
volumes: {storage: {}, postgres: {}, redis: {}, caddy: {}}
YAML
  install -d -m 0755 /usr/local/sbin
  cat >/usr/local/sbin/chatwoot-start <<'START'
#!/bin/bash
# chatwoot-start <domain>: the owner's step once DNS points here. Writes the
# public name, the TLS front (443 only), prepares the database, starts.
set -euo pipefail
domain="${1:-}"
[[ "$domain" =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$ ]] ||
  { echo "usage: chatwoot-start <domain> (e.g. chat.example.com)" >&2; exit 2; }
cd /opt/chatwoot
sed -i "s|^FRONTEND_URL=.*|FRONTEND_URL=https://$domain|" .env
printf '{\n\tauto_https disable_redirects\n}\n%s {\n\tencode gzip\n\treverse_proxy rails:3000\n}\n' \
  "$domain" >Caddyfile
docker compose pull --quiet
docker compose run --rm rails bundle exec rails db:chatwoot_prepare
docker compose up -d
echo "Chatwoot is starting at https://$domain (create the first admin there, then the agent bot)."
START
  chmod 0750 /usr/local/sbin/chatwoot-start
  result chatwoot 1 "$CW_VERSION" "installed, not started: run 'sudo chatwoot-start <domain>' once DNS points here"
}
