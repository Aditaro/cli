#!/usr/bin/env python3
"""Warden: self-healing database migration guard for Databricks Delta tables.

Core loop: read the migration's intent from the most recent Entire checkpoint,
run an Entire Graph impact check, apply the migration, validate it, and on
failure roll back via Delta time-travel while explaining the failure using the
checkpoint's recorded intent -- not just a blind revert.

Synthetic/demo data only. Requires env vars:
  DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN
"""
import argparse
import json
import os
import subprocess
import sys


def run_entire(args, timeout=30):
    """Run an `entire` subcommand, returning stdout. Never raises -- degrades
    gracefully with a note, per the Buildathon guide's own warning that graph
    (and checkpoint) output is evidence, not fact, and must not be presented
    as certain when it can't be obtained."""
    try:
        result = subprocess.run(
            ["entire"] + args, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            return None, result.stderr.strip()
        return result.stdout, None
    except Exception as e:
        return None, str(e)


def get_latest_checkpoint():
    """Returns (checkpoint_id, intent_text) for the most recent checkpoint on
    this branch, or (None, None) if unavailable."""
    out, err = run_entire(["checkpoint", "list", "--json"])
    if out is None:
        print(f"[warden] WARNING: could not list checkpoints ({err}); proceeding without recorded intent")
        return None, None
    try:
        checkpoints = json.loads(out)
    except json.JSONDecodeError:
        print("[warden] WARNING: checkpoint list did not parse as JSON; proceeding without recorded intent")
        return None, None
    # Skip live/pending shadow-branch entries (no `agent`/`is_logs_only` field,
    # commit-SHA-shaped id) -- only trust checkpoints that are actually
    # committed, since an in-progress checkpoint's recorded intent can still
    # change and shouldn't be treated as settled evidence.
    committed = [c for c in checkpoints if c.get("is_logs_only") or c.get("agent")]
    if not committed:
        return None, None
    cp_id = committed[0]["checkpoint_id"]
    explain, err = run_entire(["checkpoint", "explain", cp_id, "--short", "--no-pager"])
    if explain is None:
        print(f"[warden] WARNING: could not explain checkpoint {cp_id} ({err})")
        return cp_id, None
    return cp_id, explain.strip()


def graph_impact(symbol):
    """Best-effort Entire Graph impact analysis. Evidence, not fact -- shown
    to the operator, never asserted as ground truth."""
    out, err = run_entire(
        ["graph", "impact", "--repo", ".", "--symbol", symbol, "--head", "--profile", "fast"],
        timeout=45,
    )
    if out is None:
        return f"(graph impact unavailable: {err})"
    return out.strip()


def connect():
    from databricks import sql
    missing = [v for v in ("DATABRICKS_SERVER_HOSTNAME", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN") if v not in os.environ]
    if missing:
        print(f"[warden] ERROR: missing required env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)
    return sql.connect(
        server_hostname=os.environ["DATABRICKS_SERVER_HOSTNAME"],
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ["DATABRICKS_TOKEN"],
    )


def current_delta_version(cur, table):
    cur.execute(f"DESCRIBE HISTORY {table} LIMIT 1")
    row = cur.fetchone()
    return row[0]


def ensure_log_table(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS warden.migration_log (
            id STRING,
            migration_name STRING,
            status STRING,
            checkpoint_id STRING,
            note STRING,
            ts TIMESTAMP
        ) USING DELTA
        """
    )


def log_attempt(cur, migration_name, status, checkpoint_id, note):
    import uuid as uuid_module

    ensure_log_table(cur)
    # uuid() can't be evaluated server-side inside a parameterized VALUES
    # clause on Databricks (INVALID_INLINE_TABLE.CANNOT_EVALUATE_EXPRESSION_IN_INLINE_TABLE)
    # -- generate the id client-side instead.
    row_id = str(uuid_module.uuid4())
    cur.execute(
        """
        INSERT INTO warden.migration_log (id, migration_name, status, checkpoint_id, note, ts)
        VALUES (?, ?, ?, ?, ?, current_timestamp())
        """,
        (row_id, migration_name, status, checkpoint_id or "", (note or "")[:4000]),
    )


def apply_migration(migration_path, table, validate_sql_path):
    with open(migration_path) as f:
        migration_sql = f.read()

    validate_sql = None
    if validate_sql_path:
        with open(validate_sql_path) as f:
            validate_sql = f.read().strip()

    cp_id, intent = get_latest_checkpoint()
    print(f"[warden] intent from checkpoint {cp_id or '(none)'}:\n{intent or '(unavailable)'}\n")

    symbol = table.split(".")[-1]
    impact = graph_impact(symbol)
    print(f"[warden] Entire Graph impact on '{symbol}' (evidence, not fact -- verify before trusting):\n{impact}\n")

    conn = connect()
    cur = conn.cursor()
    try:
        pre_version = current_delta_version(cur, table)
        print(f"[warden] '{table}' currently at Delta version {pre_version}")

        for stmt in migration_sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)
        print(f"[warden] migration '{migration_path}' applied.")

        offending_rows = 0
        if validate_sql:
            cur.execute(validate_sql)
            offending_rows = len(cur.fetchall())
            print(f"[warden] validation {'passed' if offending_rows == 0 else 'FAILED'} ({offending_rows} offending row(s))")

        if offending_rows == 0:
            log_attempt(cur, migration_path, "applied", cp_id, "applied cleanly, validation passed")
            print("[warden] SUCCESS.")
            return 0

        raise RuntimeError(f"validation failed: {offending_rows} row(s) violated the check in {validate_sql_path}")

    except Exception as e:
        print(f"[warden] FAILURE: {e}")
        print(f"[warden] healing: restoring '{table}' to Delta version {pre_version} via time-travel...")
        try:
            cur.execute(f"RESTORE TABLE {table} TO VERSION AS OF {pre_version}")
        except Exception as heal_error:
            # The heal itself failed -- this is the genuinely unrecoverable case.
            # Log it as such rather than silently losing the failure.
            log_attempt(cur, migration_path, "failed", cp_id, f"migration failed ({e}) AND rollback failed ({heal_error})")
            raise
        explanation = (
            f"Migration '{migration_path}' failed: {e}\n\n"
            f"Recorded intent (checkpoint {cp_id or 'unavailable'}):\n{intent or '(no intent recorded)'}\n\n"
            f"Action taken: rolled back {table} to Delta version {pre_version}. "
            f"The intent above is what this migration was trying to achieve -- "
            f"use it to write a corrected migration rather than re-attempting blindly."
        )
        print(f"\n[warden] {explanation}")
        log_attempt(cur, migration_path, "healed", cp_id, explanation)
        return 1
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Warden: self-healing DB migration guard")
    parser.add_argument("migration", help="path to the migration .sql file")
    parser.add_argument("--table", default="warden.demo_users", help="target Delta table")
    parser.add_argument("--validate-sql", help="path to a SQL file returning offending rows (0 rows = pass)")
    args = parser.parse_args()

    sys.exit(apply_migration(args.migration, args.table, args.validate_sql))


if __name__ == "__main__":
    main()
