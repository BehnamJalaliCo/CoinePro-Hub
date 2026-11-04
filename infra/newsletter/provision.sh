#!/usr/bin/env bash
# Idempotent role and database for Listmonk (prompt 22 part 3, contract §31.3), run
# as the superuser by the compose job newsletter-provision (opt-in profile
# "newsletter"). Its own role `listmonk` and its own database `listmonk`, reachable
# by nobody else; the password is read with \getenv so it never appears in argv.
set -euo pipefail

: "${LISTMONK_DB_PASSWORD:?run make env}"
export PGUSER="${PGUSER:-postgres}"

psql -v ON_ERROR_STOP=1 --no-psqlrc --quiet --dbname postgres <<'SQL'
SET client_min_messages = warning;
\getenv listmonk_pw LISTMONK_DB_PASSWORD

SELECT 'CREATE ROLE listmonk LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'listmonk')
\gexec

ALTER ROLE listmonk WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  PASSWORD :'listmonk_pw';
ALTER ROLE listmonk SET statement_timeout = '60s';

SELECT 'CREATE DATABASE listmonk OWNER listmonk'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'listmonk')
\gexec

REVOKE ALL ON DATABASE listmonk FROM PUBLIC;
GRANT ALL ON DATABASE listmonk TO listmonk;
SQL

echo "newsletter-provision: role and database listmonk ready"
