#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 -v graph_password="$GRAPH_WRITER_PASSWORD" \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE ROLE graph_writer LOGIN PASSWORD :'graph_password';
CREATE SCHEMA graph AUTHORIZATION graph_writer;
ALTER ROLE graph_writer SET search_path = graph;
SQL
