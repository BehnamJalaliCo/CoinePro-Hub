#!/usr/bin/env bash
# Idempotent role provisioning, run as the superuser on every `make up`
# (compose job db-provision). initdb/ only runs on an empty volume; roles
# added by later prompts live here.
#
#   hq_llm_writer  NOLOGIN  insert/update in llm.* (rows of permitted companies only)
#   hq_llm_reader  NOLOGIN  read-only in llm.* (permitted companies only)
#   llm_router     LOGIN    the llm-router service; member of hq_llm_writer
#
# Table privileges are granted by the owner (role hq) in the Alembic migrations.
set -euo pipefail

: "${LLM_ROUTER_DB_PASSWORD:?}"
export PGUSER="${PGUSER:-postgres}"

psql -v ON_ERROR_STOP=1 --no-psqlrc --quiet --dbname postgres <<'SQL'
SET client_min_messages = warning;
\getenv router_pw LLM_ROUTER_DB_PASSWORD

SELECT format('CREATE ROLE %I NOLOGIN', r)
FROM unnest(ARRAY['hq_llm_writer', 'hq_llm_reader']) AS r
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)
\gexec

SELECT 'CREATE ROLE llm_router LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'llm_router')
\gexec

ALTER ROLE llm_router WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  PASSWORD :'router_pw';
ALTER ROLE llm_router SET statement_timeout = '15s';
GRANT hq_llm_writer TO llm_router;
GRANT CONNECT ON DATABASE hq TO llm_router;
SQL

echo "db-provision: roles hq_llm_writer, hq_llm_reader, llm_router ready"
