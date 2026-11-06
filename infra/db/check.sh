#!/usr/bin/env bash
set -Eeuo pipefail
export PGHOST=127.0.0.1 PGPORT=5432 PGCONNECT_TIMEOUT=5
for domain in member catalog support; do
  upper=${domain^^}
  owner_var="${upper}_OWNER_PASSWORD"
  app_var="${upper}_APP_PASSWORD"
  export PGDATABASE="kkulpick_${domain}" PGUSER="kkulpick_${domain}_owner" PGPASSWORD="${!owner_var}"
  # Transaction rollback leaves no test tables and checks migration permissions.
  psql -XqAt -v ON_ERROR_STOP=1 -c 'BEGIN; CREATE TABLE app.__db_bootstrap_check (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY); ROLLBACK;' >/dev/null
  # Check default table/sequence grants in a transaction, leaving no records.
  PGPASSWORD="$POSTGRES_PASSWORD" psql -XqAt -U postgres -v ON_ERROR_STOP=1 \
    -v owner="kkulpick_${domain}_owner" -v app="kkulpick_${domain}_app" <<'SQL' >/dev/null
BEGIN;
SET ROLE :"owner";
CREATE TABLE app.__db_grant_check (id bigserial PRIMARY KEY, value text);
SET ROLE :"app";
INSERT INTO app.__db_grant_check (value) VALUES ('test');
SELECT * FROM app.__db_grant_check;
UPDATE app.__db_grant_check SET value = 'updated';
DELETE FROM app.__db_grant_check;
ROLLBACK;
SQL
  export PGUSER="kkulpick_${domain}_app" PGPASSWORD="${!app_var}"
  actual=$(psql -XqAt -v ON_ERROR_STOP=1 -c 'SELECT current_database();')
  test "$actual" = "$PGDATABASE"
  can_create=$(psql -XqAt -v ON_ERROR_STOP=1 -c "SELECT has_schema_privilege(current_user, 'app', 'CREATE');")
  test "$can_create" = f
  if psql -XqAt -v ON_ERROR_STOP=1 -c 'BEGIN; CREATE TABLE app.__forbidden (id int); ROLLBACK;' >/dev/null 2>&1; then
    echo "FAIL: application user can create tables" >&2; exit 1
  fi
  for other in member catalog support; do
    if [ "$other" != "$domain" ] && psql -XqAt -d "kkulpick_${other}" -c 'SELECT 1' >/dev/null 2>&1; then
      echo "FAIL: cross-database connection allowed" >&2; exit 1
    fi
  done
  if [ "$domain" = catalog ]; then
    distance=$(psql -XqAt -v ON_ERROR_STOP=1 -c "SELECT '[1,2,3]'::vector <-> '[1,2,3]'::vector;")
    test "$distance" = 0
  fi
  echo "PASS: $PGDATABASE login, owner DDL, app CRUD/sequence grants, app DDL denied, cross-DB denied"
done
echo 'PASS: catalog pgvector distance query'
