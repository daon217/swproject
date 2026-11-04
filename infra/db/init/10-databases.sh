#!/usr/bin/env bash
set -Eeuo pipefail
# Values enter SQL through psql quoting, never shell interpolation into SQL.
for domain in member catalog support; do
  upper=${domain^^}
  owner_var="${upper}_OWNER_PASSWORD"
  app_var="${upper}_APP_PASSWORD"
  psql --username "$POSTGRES_USER" --dbname postgres --no-psqlrc --set ON_ERROR_STOP=1 \
    --set db="kkulpick_${domain}" --set owner="kkulpick_${domain}_owner" \
    --set app="kkulpick_${domain}_app" \
    --set owner_password="${!owner_var}" --set app_password="${!app_var}" <<'SQL'
CREATE ROLE :"owner" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'owner_password';
CREATE ROLE :"app" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'app_password';
CREATE DATABASE :"db" OWNER :"owner" ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO :"owner", :"app";
SQL
  psql --username "$POSTGRES_USER" --dbname "kkulpick_${domain}" --no-psqlrc --set ON_ERROR_STOP=1 \
    --set owner="kkulpick_${domain}_owner" --set app="kkulpick_${domain}_app" <<'SQL'
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"owner", :"app";
CREATE SCHEMA app AUTHORIZATION :"owner";
GRANT USAGE ON SCHEMA app TO :"app";
ALTER ROLE :"owner" SET search_path = app, public;
ALTER ROLE :"app" SET search_path = app, public;
ALTER ROLE :"app" SET statement_timeout = '15s';
ALTER ROLE :"app" SET idle_in_transaction_session_timeout = '30s';
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA app
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA app
  GRANT USAGE, SELECT ON SEQUENCES TO :"app";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA app
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
SQL
 done
psql --username "$POSTGRES_USER" --dbname kkulpick_catalog --no-psqlrc --set ON_ERROR_STOP=1 \
  --command 'CREATE EXTENSION vector WITH SCHEMA public;'
# Prevent application users from connecting to the bootstrap/maintenance DBs.
psql --username "$POSTGRES_USER" --dbname postgres --no-psqlrc --set ON_ERROR_STOP=1 <<'SQL'
REVOKE CONNECT, TEMPORARY ON DATABASE postgres FROM PUBLIC;
REVOKE CONNECT, TEMPORARY ON DATABASE template1 FROM PUBLIC;
SQL
