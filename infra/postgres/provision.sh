#!/usr/bin/env bash
# Idempotent role provisioning, run as the superuser on every `make up`
# (compose job db-provision). initdb/ only runs on an empty volume; roles
# added by later prompts live here.
#
#   hq_llm_writer  NOLOGIN  insert/update in llm.* (rows of permitted companies only)
#   hq_llm_reader  NOLOGIN  read-only in llm.* (permitted companies only)
#   llm_router     LOGIN    the llm-router service; member of hq_llm_writer
#   hq_api         LOGIN    apps/api (public + internal API), least privilege (prompt 04)
#   hq_worker      LOGIN    apps/api worker (Temporal activities), least privilege
# Also creates pg_trgm in database hq (Persian-safe trigram search).
#
# Table privileges are granted by the owner (role hq) in the Alembic migrations.
set -euo pipefail

: "${LLM_ROUTER_DB_PASSWORD:?}" "${HQ_API_DB_PASSWORD:?}" "${HQ_WORKER_DB_PASSWORD:?}"
export PGUSER="${PGUSER:-postgres}"

psql -v ON_ERROR_STOP=1 --no-psqlrc --quiet --dbname postgres <<'SQL'
SET client_min_messages = warning;
\getenv router_pw LLM_ROUTER_DB_PASSWORD
\getenv api_pw HQ_API_DB_PASSWORD
\getenv worker_pw HQ_WORKER_DB_PASSWORD

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

SELECT format('CREATE ROLE %I LOGIN', r)
FROM unnest(ARRAY['hq_api', 'hq_worker']) AS r
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)
\gexec

ALTER ROLE hq_api WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  PASSWORD :'api_pw';
ALTER ROLE hq_api SET statement_timeout = '15s';
ALTER ROLE hq_worker WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  PASSWORD :'worker_pw';
ALTER ROLE hq_worker SET statement_timeout = '60s';
GRANT CONNECT ON DATABASE hq TO hq_api, hq_worker;

\connect hq
CREATE EXTENSION IF NOT EXISTS pg_trgm;
SQL

echo "db-provision: roles hq_llm_writer, hq_llm_reader, llm_router, hq_api, hq_worker ready"
