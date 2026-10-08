#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -v runtime_pass="$RUNTIME_DB_PASSWORD" -v migrator_pass="$MIGRATOR_DB_PASSWORD" <<'SQL'
CREATE ROLE greenops LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD :'runtime_pass';
CREATE ROLE greenops_migrator LOGIN NOSUPERUSER BYPASSRLS PASSWORD :'migrator_pass';
GRANT CONNECT ON DATABASE greenops TO greenops, greenops_migrator;
GRANT CREATE ON SCHEMA public TO greenops_migrator;
SQL
