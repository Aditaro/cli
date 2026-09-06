#!/usr/bin/env bash
set -uo pipefail

# Credentials must already be exported by the caller. Never read or print them.

# --- presentation helpers -------------------------------------------------
# Colour is on unless NO_COLOR is set (https://no-color.org) so a piped
# recording keeps the same shape a live viewer sees.
if [[ -n "${NO_COLOR:-}" ]]; then
  DIM=""; BOLD=""; RED=""; GRN=""; YEL=""; CYN=""; RST=""
else
  DIM=$'\033[2m'; BOLD=$'\033[1m'; RED=$'\033[31m'; GRN=$'\033[32m'
  YEL=$'\033[33m'; CYN=$'\033[36m'; RST=$'\033[0m'
fi

step() {
  printf '\n%s┌─ %s%s %s%s\n' "$CYN" "$BOLD" "$1" "$DIM" "$RST"
  printf '%s│%s  %s\n' "$CYN" "$RST" "$2"
  printf '%s└%s\n' "$CYN" "$RST"
}

banner() { printf '\n%s%s%s\n' "$BOLD" "$1" "$RST"; }

if [[ "${1:-}" == "--self-test" ]]; then
  banner "Warden demo self-test (no warehouse connection)"
  # errexit is deliberately enabled only for this block: without it these
  # checks are non-fatal and the block falls through to an unconditional
  # "self-test OK", so a broken fixture still reported success.
  set -e
  test -s migrations/001_add_plan_column.sql
  test -s migrations/001_validate.sql
  test -s warden/migrate.py
  grep -Fq "ALTER TABLE warden.demo_users" migrations/001_add_plan_column.sql
  grep -Fq "plan NOT IN" migrations/001_validate.sql
  python3 databricks/seed.py --self-test
  set +e
  printf '%s✓ self-test OK%s — migration, validation, and synthetic seed fixtures are present\n' "$GRN" "$RST"
  exit 0
fi

if [[ "$#" -gt 1 ]]; then
  echo "usage: bash warden/demo.sh [--self-test | <checkpoint-id>]" >&2
  exit 2
fi

# Which checkpoint's recorded intent explains this migration. Pinned, because
# the newest checkpoint on the branch is whatever was committed last, which is
# not necessarily the work that authored the migration -- and intent from
# unrelated work is worse than none, since it is confidently wrong. Override
# by argument or environment; set empty to fall back to "most recent".
DEMO_CHECKPOINT="${1:-${WARDEN_DEMO_CHECKPOINT-01M1V6D7VCDZC97DMBF1WGTR52}}"

: "${DATABRICKS_SERVER_HOSTNAME:?DATABRICKS_SERVER_HOSTNAME must be exported}"
: "${DATABRICKS_HTTP_PATH:?DATABRICKS_HTTP_PATH must be exported}"
: "${DATABRICKS_TOKEN:?DATABRICKS_TOKEN must be exported}"

# Prints only the bare version number, so it can be captured and compared.
fetch_version() {
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
        print(row[0])
'
}

run_latest_log() {
  SQL_QUERY='SELECT id, migration_name, status, checkpoint_id, note, context_completeness, ts FROM warden.migration_log ORDER BY ts DESC LIMIT 1' python3 -c '
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
            width = max(len(c) for c in columns)
            for name, value in zip(columns, row):
                print(f"  {name.rjust(width)}  {value}")
'
}

printf '\n%s╔══════════════════════════════════════════════════════════════╗%s\n' "$BOLD" "$RST"
printf '%s║  WARDEN  ·  self-healing migration guard                      ║%s\n' "$BOLD" "$RST"
printf '%s╚══════════════════════════════════════════════════════════════╝%s\n' "$BOLD" "$RST"
printf '%starget: warden.demo_users   ·   migration: 001_add_plan_column.sql%s\n' "$DIM" "$RST"

step "1 · BEFORE" "Reading the current Delta version — this is the rollback target."
pre_version="$(fetch_version)"
printf '   %s%sDelta version %s%s\n' "$BOLD" "$CYN" "$pre_version" "$RST"

step "2 · MIGRATE" "Apply, validate, and heal on failure via Delta time-travel."
migrate_args=(migrations/001_add_plan_column.sql --validate-sql migrations/001_validate.sql)
if [[ -n "$DEMO_CHECKPOINT" ]]; then
  migrate_args+=(--checkpoint "$DEMO_CHECKPOINT")
fi
set +e
python3 warden/migrate.py "${migrate_args[@]}"
migration_status=$?
set -e
if [[ "$migration_status" -gt 1 ]]; then
  printf '\n%s✗ Migration command failed unexpectedly (exit %s).%s\n' "$RED" "$migration_status" "$RST" >&2
  exit "$migration_status"
fi

step "3 · WHAT REACHED DATABRICKS" "Note what is absent: no checkpoint intent, no raw error text."
run_latest_log

step "4 · AFTER" "If the heal worked, this matches the version from step 1."
post_version="$(fetch_version)"
printf '   %s%sDelta version %s%s\n' "$BOLD" "$CYN" "$post_version" "$RST"

# ---- the proof: pre/post comparison ----
printf '\n'
if [[ "$pre_version" == "$post_version" ]]; then
  printf '   %s%s  v%s  ──►  ✗ constraint violated  ──►  v%s  %s\n' \
    "$BOLD" "$GRN" "$pre_version" "$post_version" "$RST"
  printf '   %s%s✓ VERSIONS MATCH%s %s— the table was genuinely restored, not just reported.%s\n' \
    "$BOLD" "$GRN" "$RST" "$DIM" "$RST"
else
  printf '   %s%s⚠ VERSIONS DIFFER%s %s(pre %s → post %s) — inspect before trusting this run.%s\n' \
    "$BOLD" "$YEL" "$RST" "$DIM" "$pre_version" "$post_version" "$RST"
fi

printf '\n'
if [[ "$migration_status" -eq 1 ]]; then
  printf '%s%sDemo complete%s %s— validation failed and Warden healed the table.%s\n' \
    "$BOLD" "$GRN" "$RST" "$DIM" "$RST"
else
  printf '%s%sDemo complete%s %s— migration applied and validation passed.%s\n' \
    "$BOLD" "$GRN" "$RST" "$DIM" "$RST"
fi
