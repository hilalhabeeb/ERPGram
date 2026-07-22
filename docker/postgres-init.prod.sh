#!/usr/bin/env bash
# Runs once, as the Postgres superuser, on first init of the production db
# volume. Mirrors docker/postgres-init.sql but takes the app-role password from
# the environment instead of hard-coding it, so no secret lives in the image.
#
# The application role is deliberately NOT a superuser and does NOT have
# BYPASSRLS — otherwise the row-level-security policies that isolate tenants are
# silently ignored. It also drops CREATEDB (production never builds a test db),
# keeping it to the least privilege that still lets it own its schema.
set -euo pipefail

: "${APP_DB_PASSWORD:?APP_DB_PASSWORD must be set for the production database}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
    CREATE ROLE erpgram_app WITH LOGIN PASSWORD '${APP_DB_PASSWORD}'
        NOSUPERUSER NOCREATEDB NOBYPASSRLS NOCREATEROLE;
    CREATE DATABASE erpgram OWNER erpgram_app;
    GRANT ALL PRIVILEGES ON DATABASE erpgram TO erpgram_app;
SQL
