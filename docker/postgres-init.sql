-- Runs once, as the Postgres superuser, on first container init.
--
-- The application connects as erpgram_app, which is deliberately NOT a superuser
-- and does NOT have BYPASSRLS — otherwise the row-level-security policies would
-- be silently ignored. It DOES get CREATEDB so the test runner can build the
-- throwaway test database (owned by this same role, which is what makes the
-- FORCE ROW LEVEL SECURITY behaviour exercised by the tests meaningful).

CREATE ROLE erpgram_app WITH LOGIN PASSWORD 'erpgram_app_pw'
    NOSUPERUSER CREATEDB NOBYPASSRLS NOCREATEROLE;

CREATE DATABASE erpgram OWNER erpgram_app;

GRANT ALL PRIVILEGES ON DATABASE erpgram TO erpgram_app;
