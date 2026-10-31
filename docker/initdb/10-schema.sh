#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 -v writer_password="$AUDIT_WRITER_PASSWORD" \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/schema.sql.in
