#!/usr/bin/env bash
set -uo pipefail

# Credentials must already be exported by the caller. Never read or print them.
: "${DATABRICKS_SERVER_HOSTNAME:?DATABRICKS_SERVER_HOSTNAME must be exported}"
: "${DATABRICKS_HTTP_PATH:?DATABRICKS_HTTP_PATH must be exported}"
: "${DATABRICKS_TOKEN:?DATABRICKS_TOKEN must be exported}"

run_history_version() {
  SQL_QUERY='DESCRIBE HISTORY warden.demo_users LIMIT 1' python3 -c '
import os
from databricks import sql

with sql.connect(
    server_hostname=os.environ["DATABRICKS_SERVER_HOSTNAME"],
    http_path=os.environ["DATABRICKS_HTTP_PATH"],
    access_token=os.environ["DATABRICKS_TOKEN"],
) as conn:
    with conn.cursor() as cur:
        cur.execute(os.environ["SQL_QUERY"])
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("DESCRIBE HISTORY returned no rows")
        print(f"Delta version: {row[0]}")
'
}

run_latest_log() {
  SQL_QUERY='SELECT id, migration_name, status, checkpoint_id, note, ts FROM warden.migration_log ORDER BY ts DESC LIMIT 1' python3 -c '
import os
from databricks import sql

with sql.connect(
    server_hostname=os.environ["DATABRICKS_SERVER_HOSTNAME"],
    http_path=os.environ["DATABRICKS_HTTP_PATH"],
    access_token=os.environ["DATABRICKS_TOKEN"],
) as conn:
    with conn.cursor() as cur:
        cur.execute(os.environ["SQL_QUERY"])
        columns = [column[0] for column in cur.description]
        row = cur.fetchone()
        if row is None:
            print("(no migration attempts recorded)")
        else:
            print(" | ".join(columns))
            print(" | ".join(str(value) for value in row))
'
}

echo "=== Pre-migration Delta version ==="
run_history_version

echo "=== Apply migration and validate (healing on failure) ==="
set +e
python3 warden/migrate.py migrations/001_add_plan_column.sql \
  --validate-sql migrations/001_validate.sql
migration_status=$?
set -e
if [[ "$migration_status" -gt 1 ]]; then
  echo "Migration command failed unexpectedly (exit $migration_status)." >&2
  exit "$migration_status"
fi

echo "=== Most recent migration log row ==="
run_latest_log

echo "=== Post-migration Delta version ==="
run_history_version

if [[ "$migration_status" -eq 1 ]]; then
  echo "Demo completed: validation failed and Warden healed the table."
else
  echo "Demo completed: migration applied and validation passed."
fi
