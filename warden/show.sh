#!/usr/bin/env bash
# Read-only inspection helpers for demoing Warden. Every query here is a
# SELECT or DESCRIBE: this script never migrates, restores, or writes.
set -uo pipefail

if [[ -n "${NO_COLOR:-}" ]]; then
  DIM=""; BOLD=""; GRN=""; CYN=""; RST=""
else
  DIM=$'\033[2m'; BOLD=$'\033[1m'; GRN=$'\033[32m'; CYN=$'\033[36m'; RST=$'\033[0m'
fi

usage() {
  cat <<'USAGE'
usage: bash warden/show.sh <command>

  offenders   the rows that will break the migration, before it runs
  log         recent migration attempts recorded in Databricks
  history     Delta version history for the demo table
  audit       migration attempts joined to the Delta versions they targeted

All commands are read-only.
USAGE
}

[[ $# -eq 1 ]] || { usage; exit 2; }

: "${DATABRICKS_SERVER_HOSTNAME:?DATABRICKS_SERVER_HOSTNAME must be exported}"
: "${DATABRICKS_HTTP_PATH:?DATABRICKS_HTTP_PATH must be exported}"
: "${DATABRICKS_TOKEN:?DATABRICKS_TOKEN must be exported}"

header() {
  printf '\n%s┌─ %s%s%s\n' "$CYN" "$BOLD" "$1" "$RST"
  printf '%s│%s  %s%s%s\n' "$CYN" "$RST" "$DIM" "$2" "$RST"
  printf '%s└%s\n' "$CYN" "$RST"
}

# Runs $SQL_QUERY and prints an aligned table. Read-only by construction:
# the query is supplied by this script, never by the caller.
run_query() {
  python3 -c '
import os
from databricks import sql

with sql.connect(
    server_hostname=os.environ["DATABRICKS_SERVER_HOSTNAME"],
    http_path=os.environ["DATABRICKS_HTTP_PATH"],
    access_token=os.environ["DATABRICKS_TOKEN"],
) as conn:
    with conn.cursor() as cur:
        cur.execute(os.environ["SQL_QUERY"])
        cols = [c[0] for c in cur.description]
        rows = [["" if v is None else str(v) for v in r] for r in cur.fetchall()]
        if not rows:
            print("  (no rows)")
        else:
            w = [max(len(cols[i]), *(len(r[i]) for r in rows)) for i in range(len(cols))]
            w = [min(x, 58) for x in w]
            def line(vals):
                return "  " + "  ".join(v[:58].ljust(w[i]) for i, v in enumerate(vals))
            print(line(cols))
            print("  " + "  ".join("-" * x for x in w))
            for r in rows:
                print(line(r))
            print(f"\n  {len(rows)} row(s)")
'
}

case "$1" in
  offenders)
    header "Rows that violate the rule this migration enforces" \
           "Run BEFORE migrating — this is why it is going to fail."
    SQL_QUERY="$(cat migrations/001_validate.sql)" run_query
    ;;
  log)
    header "Recent migration attempts (warden.migration_log)" \
           "The audit trail. Note: no checkpoint intent, no row values."
    SQL_QUERY='SELECT status, context_completeness, checkpoint_id, ts
               FROM warden.migration_log ORDER BY ts DESC LIMIT 8' run_query
    ;;
  history)
    header "Delta version history for warden.demo_users" \
           "Every version is a restore target. This is what makes healing possible."
    SQL_QUERY='SELECT version, operation, timestamp
               FROM (DESCRIBE HISTORY warden.demo_users) LIMIT 8' run_query
    ;;
  audit)
    header "Migration attempts joined to Delta table history" \
           "Two systems? No — one. The audit trail lives beside the data it describes."
    # One row per attempt: the table version that was current when it ran.
    # ROW_NUMBER picks the newest version at or before the attempt, rather
    # than every version that preceded it.
    SQL_QUERY="WITH hist AS (
                 SELECT version, timestamp FROM (DESCRIBE HISTORY warden.demo_users)
               ),
               paired AS (
                 SELECT l.status, l.context_completeness, l.ts, h.version,
                        ROW_NUMBER() OVER (PARTITION BY l.ts ORDER BY h.version DESC) AS rn
                 FROM warden.migration_log l
                 LEFT JOIN hist h ON h.timestamp <= l.ts
               )
               SELECT status, context_completeness,
                      version AS table_version_at_attempt, ts
               FROM paired WHERE rn = 1 ORDER BY ts DESC LIMIT 6" run_query
    ;;
  *)
    usage; exit 2
    ;;
esac
