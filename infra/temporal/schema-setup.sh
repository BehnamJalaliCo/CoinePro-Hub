#!/bin/sh
# Temporal schema via the official production tool (temporal-sql-tool).
# setup-schema -v 0.0 is a no-op once a database is versioned, and
# update-schema applies only newer versions, so this is safe on every start
# and doubles as the upgrade step after a Temporal version bump.
# Connection settings come from SQL_PLUGIN / SQL_HOST / SQL_PORT.
set -eu

SCHEMA_DIR=/etc/temporal/schema/postgresql/v12

migrate() {
  db="$1" user="$2" password="$3" dir="$4"
  echo "temporal-schema: $db"
  (
    export SQL_DATABASE="$db" SQL_USER="$user" SQL_PASSWORD="$password"
    temporal-sql-tool setup-schema -v 0.0
    temporal-sql-tool update-schema -d "$dir"
  )
}

migrate temporal temporal "$TEMPORAL_DB_PASSWORD" "$SCHEMA_DIR/temporal/versioned"
migrate temporal_visibility temporal_visibility "$TEMPORAL_VISIBILITY_DB_PASSWORD" "$SCHEMA_DIR/visibility/versioned"
echo "temporal-schema: done"
