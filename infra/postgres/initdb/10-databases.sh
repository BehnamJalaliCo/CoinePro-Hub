#!/usr/bin/env bash
# First-start initialisation (runs once, only on an empty data volume).
# One database per consumer, each owned by its own least-privilege role:
#   hq                  -> role hq                   (+ vector, pg_stat_statements)
#   temporal            -> role temporal
#   temporal_visibility -> role temporal_visibility  (+ btree_gin)
# Passwords are read with \getenv so they never appear in a process argv.
set -euo pipefail

: "${HQ_DB_PASSWORD:?}" "${TEMPORAL_DB_PASSWORD:?}" "${TEMPORAL_VISIBILITY_DB_PASSWORD:?}"

psql -v ON_ERROR_STOP=1 --no-psqlrc --username "$POSTGRES_USER" --dbname postgres <<'SQL'
\getenv hq_pw HQ_DB_PASSWORD
\getenv temporal_pw TEMPORAL_DB_PASSWORD
\getenv visibility_pw TEMPORAL_VISIBILITY_DB_PASSWORD

-- Nobody but the superuser may connect to the maintenance database.
REVOKE ALL ON DATABASE postgres FROM PUBLIC;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

CREATE ROLE hq LOGIN PASSWORD :'hq_pw'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE temporal LOGIN PASSWORD :'temporal_pw'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE temporal_visibility LOGIN PASSWORD :'visibility_pw'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

CREATE DATABASE hq OWNER hq;
CREATE DATABASE temporal OWNER temporal;
CREATE DATABASE temporal_visibility OWNER temporal_visibility;

-- Each database is reachable only by its owner (and the superuser).
REVOKE ALL ON DATABASE hq FROM PUBLIC;
REVOKE ALL ON DATABASE temporal FROM PUBLIC;
REVOKE ALL ON DATABASE temporal_visibility FROM PUBLIC;

\connect hq
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

\connect temporal
REVOKE ALL ON SCHEMA public FROM PUBLIC;

\connect temporal_visibility
-- Needed by Temporal's visibility schema; created here so the role needs no extra rights.
CREATE EXTENSION IF NOT EXISTS btree_gin;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
SQL

echo "initdb: databases hq, temporal, temporal_visibility and their roles are ready"
