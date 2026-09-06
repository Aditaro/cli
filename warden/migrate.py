#!/usr/bin/env python3
"""Warden: self-healing database migration guard for Databricks Delta tables.

Core loop: read the migration's intent from the most recent Entire checkpoint,
run an Entire Graph impact check, apply the migration, validate it, and on
failure roll back via Delta time-travel while explaining the failure using the
checkpoint's recorded intent locally -- not just a blind revert.

Synthetic/demo data only. Requires env vars:
  DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN
"""
import argparse
import json
import os
import re
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


class LocalOnlyText:
    """Wraps checkpoint intent text so leaking it is a type error, not a
    discipline problem. str()/repr()/an f-string all return a redaction
    placeholder -- never the real text. The only way back to the real text
    is the explicit .reveal() call, which exists at exactly the two
    console-print sites that are genuinely local-only (apply_migration's
    initial print, and describe_failure's console_text). A future call site
    that forgets the external-service boundary and just interpolates this
    object into a string headed for Databricks gets the placeholder, not a
    leak -- the failure mode changes from "silent data exposure" to "an
    obviously wrong string in a log row", which is what makes this a
    structural guarantee rather than a convention enforced by review."""

    _PLACEHOLDER = "<local-only text, use .reveal() explicitly>"

    def __init__(self, value):
        self._value = value

    def reveal(self):
        """The one sanctioned way to get the real text back."""
        return self._value

    def __bool__(self):
        return bool(self._value)

    def __str__(self):
        return self._PLACEHOLDER

    __repr__ = __str__


REDACTED_MARKER_RE = re.compile(r"\bREDACTED\b|\[REDACTED_[A-Z_]+\]")


def classify_completeness(cp_id, intent):
    """Classify how much of the checkpoint's recorded intent is actually
    available, so nothing downstream (console reader, DB row, human) can
    mistake partial context for complete: 'complete', 'redacted', or
    'unavailable'. Entire's own redaction marks removed text as bare
    "REDACTED" or "[REDACTED_<LABEL>]" (see redact.RedactedPlaceholder) --
    that marker surviving into --short output is the signal a field was
    stripped, not missing outright."""
    if cp_id is None or intent is None:
        return "unavailable"
    if REDACTED_MARKER_RE.search(intent):
        return "redacted"
    return "complete"


def explain_checkpoint(cp_id):
    """Fetch one checkpoint's recorded intent by id, wrapped local-only.

    Shared by the pinned and latest paths so both classify completeness
    and wrap intent identically -- a pinned checkpoint gets no weaker
    treatment than a discovered one."""
    explain, err = run_entire(["checkpoint", "explain", cp_id, "--short", "--no-pager"])
    if explain is None:
        print(f"[warden] WARNING: could not explain checkpoint {cp_id} ({err})")
        return cp_id, LocalOnlyText(None), classify_completeness(cp_id, None)
    intent = explain.strip()
    if not intent:
        return cp_id, LocalOnlyText(None), classify_completeness(cp_id, None)
    return cp_id, LocalOnlyText(intent), classify_completeness(cp_id, intent)


def get_latest_checkpoint(checkpoint_id=None):
    """Returns (checkpoint_id, LocalOnlyText(intent_text), completeness).

    With `checkpoint_id`, reads that checkpoint. Pinning matters because a
    migration's reasoning lives in the checkpoint that *authored* it, which
    is not necessarily the newest one on the branch -- any unrelated work
    committed afterwards would otherwise supply the intent explaining a
    failure, which is worse than having none: it is confidently wrong.

    Without it, falls back to the most recent committed checkpoint.
    completeness is 'unavailable' when no checkpoint/intent could be
    obtained at all. Intent is always wrapped, including the None cases, so
    every caller gets the same type back and the fail-safe default applies
    uniformly."""
    if checkpoint_id:
        return explain_checkpoint(checkpoint_id)
    out, err = run_entire(["checkpoint", "list", "--json"])
    if out is None:
        print(f"[warden] WARNING: could not list checkpoints ({err}); proceeding without recorded intent")
        return None, LocalOnlyText(None), classify_completeness(None, None)
    try:
        checkpoints = json.loads(out)
    except json.JSONDecodeError:
        print("[warden] WARNING: checkpoint list did not parse as JSON; proceeding without recorded intent")
        return None, LocalOnlyText(None), classify_completeness(None, None)
    # Skip live/pending shadow-branch entries (no `agent`/`is_logs_only` field,
    # commit-SHA-shaped id) -- only trust checkpoints that are actually
    # committed, since an in-progress checkpoint's recorded intent can still
    # change and shouldn't be treated as settled evidence.
    committed = [c for c in checkpoints if c.get("is_logs_only") or c.get("agent")]
    if not committed:
        return None, LocalOnlyText(None), classify_completeness(None, None)
    return explain_checkpoint(committed[0]["checkpoint_id"])


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
            context_completeness STRING,
            ts TIMESTAMP
        ) USING DELTA
        """
    )
    # The table may already exist from before this column was added -- backfill
    # it rather than failing every insert against an older live table.
    try:
        cur.execute("ALTER TABLE warden.migration_log ADD COLUMNS (context_completeness STRING)")
    except Exception as error:
        # Databricks does not expose a portable duplicate-column exception in
        # the DB-API layer. Match its specific duplicate-column diagnostic,
        # but propagate permission, connectivity, and other ALTER failures.
        error_text = str(error).upper()
        duplicate_column = (
            "COLUMN_ALREADY_EXISTS" in error_text
            or "CONTEXT_COMPLETENESS" in error_text and "ALREADY EXISTS" in error_text
        )
        if not duplicate_column:
            raise


def log_attempt(cur, migration_name, status, checkpoint_id, note, context_completeness):
    import uuid as uuid_module

    ensure_log_table(cur)
    # uuid() can't be evaluated server-side inside a parameterized VALUES
    # clause on Databricks (INVALID_INLINE_TABLE.CANNOT_EVALUATE_EXPRESSION_IN_INLINE_TABLE)
    # -- generate the id client-side instead.
    row_id = str(uuid_module.uuid4())
    cur.execute(
        """
        INSERT INTO warden.migration_log (id, migration_name, status, checkpoint_id, note, context_completeness, ts)
        VALUES (?, ?, ?, ?, ?, ?, current_timestamp())
        """,
        (row_id, migration_name, status, checkpoint_id or "", (note or "")[:4000], context_completeness),
    )


def error_summary(error):
    """Reduce an exception to its type name only, for anything that reaches
    an external service. A DB engine's own error text is not safe to forward
    verbatim: some of Delta's own constraint-violation messages
    (DELTA_VIOLATE_CONSTRAINT_WITH_VALUES, raised on an INSERT/UPDATE against
    an existing constraint) embed the offending row's actual column values,
    so `str(error)` can carry table data through the exact same door the
    checkpoint-intent boundary closes for intent text. (This demo's own
    failure mode -- ADD CONSTRAINT validating pre-existing data -- raises
    DELTA_NEW_CHECK_CONSTRAINT_VIOLATION instead, which reports only a row
    count; this guard covers the value-embedding case generally, not just
    what this specific migration happens to trigger.) The
    full message is still available locally via console_text/print -- this
    function only governs what crosses the external-service boundary."""
    return type(error).__name__


def describe_failure(migration_path, error, table, pre_version, cp_id, intent, completeness):
    """Build (console_text, db_note) for a failed-and-healed migration.

    `intent` is a LocalOnlyText -- .reveal() is called here exactly once,
    for console_text, which is printed locally only and may carry the full
    recorded intent and the full exception text. db_note is what reaches
    Databricks -- an external service outside Entire's own boundary -- and
    must never carry the raw checkpoint intent text (redacted or not) or the
    raw exception text: both are reduced to safe labels (completeness /
    error_summary), with the checkpoint id and console as the pointer to
    full detail. db_note never touches `intent` at all, so even if that
    changed, the LocalOnlyText wrapper still fails safe by default."""
    intent_for_console = (
        intent.reveal() if (completeness == "complete" and intent)
        else "(intent is not complete; verify the checkpoint locally)"
    )
    console_text = (
        f"Migration '{migration_path}' failed: {error}\n\n"
        f"Recorded intent (checkpoint {cp_id or 'unavailable'}, context: {completeness}):\n"
        f"{intent_for_console}\n\n"
        f"Action taken: rolled back {table} to Delta version {pre_version}. "
        f"The intent above is what this migration was trying to achieve -- "
        f"use it to write a corrected migration rather than re-attempting blindly."
    )
    db_note = (
        f"migration failed ({error_summary(error)}); rolled back {table} to Delta version {pre_version}. "
        f"Checkpoint intent and full error detail kept local-only (context: {completeness}); "
        f"see operator console for detail."
    )
    return console_text, db_note


def apply_migration(migration_path, table, validate_sql_path, checkpoint_id=None):
    with open(migration_path) as f:
        migration_sql = f.read()

    validate_sql = None
    if validate_sql_path:
        with open(validate_sql_path) as f:
            validate_sql = f.read().strip()

    cp_id, intent, completeness = get_latest_checkpoint(checkpoint_id)
    # .reveal() here is deliberate: this print is local console output, one
    # of the two sanctioned local-only sites for LocalOnlyText (the other is
    # describe_failure's console_text).
    print(f"[warden] intent from checkpoint {cp_id or '(none)'} [context: {completeness}]:\n{intent.reveal() if intent else '(unavailable)'}\n")
    if completeness != "complete":
        print(f"[warden] NOTE: recorded intent is {completeness} -- treat as partial evidence, not settled fact.\n")

    symbol = table.split(".")[-1]
    impact = graph_impact(symbol)
    print(f"[warden] Entire Graph impact on '{symbol}' (evidence, not fact -- verify before trusting):\n{impact}\n")

    conn = connect()
    cur = conn.cursor()
    pre_version = None
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
            log_attempt(cur, migration_path, "applied", cp_id, "applied cleanly, validation passed", completeness)
            print("[warden] SUCCESS.")
            return 0

        raise RuntimeError(f"validation failed: {offending_rows} row(s) violated the check in {validate_sql_path}")

    except Exception as e:
        print(f"[warden] FAILURE: {e}")
        if pre_version is None:
            print(
                "[warden] HEAL SKIPPED: pre-migration Delta version is unavailable; "
                "cannot safely restore the table."
            )
            try:
                log_attempt(
                    cur, migration_path, "failed", cp_id,
                    f"migration failed ({error_summary(e)}); rollback skipped because "
                    "the pre-migration Delta version was unavailable; see operator console for detail",
                    completeness,
                )
            except Exception as log_error:
                print(f"[warden] LOG FAILED: {log_error}")
            return 1
        print(f"[warden] healing: restoring '{table}' to Delta version {pre_version} via time-travel...")
        try:
            cur.execute(f"RESTORE TABLE {table} TO VERSION AS OF {pre_version}")
        except Exception as heal_error:
            # The heal itself failed -- this is the genuinely unrecoverable case.
            # Log it as such rather than silently losing the failure. Same
            # error_summary reduction as describe_failure -- raw exception
            # text can carry table data (see error_summary's docstring), so
            # neither exception's message crosses the external-service
            # boundary here either.
            print(f"[warden] HEAL FAILED: {heal_error}")
            log_attempt(
                cur, migration_path, "failed", cp_id,
                f"migration failed ({error_summary(e)}) AND rollback failed ({error_summary(heal_error)}); "
                f"see operator console for detail",
                completeness,
            )
            raise
        console_text, db_note = describe_failure(migration_path, e, table, pre_version, cp_id, intent, completeness)
        print(f"\n[warden] {console_text}")
        log_attempt(cur, migration_path, "healed", cp_id, db_note, completeness)
        return 1
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Warden: self-healing DB migration guard")
    parser.add_argument("migration", help="path to the migration .sql file")
    parser.add_argument("--table", default="warden.demo_users", help="target Delta table")
    parser.add_argument("--validate-sql", help="path to a SQL file returning offending rows (0 rows = pass)")
    parser.add_argument(
        "--checkpoint",
        help="checkpoint id whose recorded intent explains THIS migration. "
             "Defaults to the most recent committed checkpoint, which is only "
             "the right one when nothing unrelated was committed after the "
             "migration was written.",
    )
    args = parser.parse_args()

    sys.exit(apply_migration(args.migration, args.table, args.validate_sql, args.checkpoint))


if __name__ == "__main__":
    main()
