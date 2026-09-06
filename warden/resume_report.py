#!/usr/bin/env python3
"""Print a safe, read-only readiness report for a Warden checkpoint."""

import argparse
import os
import re
from pathlib import Path

from migrate import LocalOnlyText, classify_completeness, run_entire


def checkpoint_context(checkpoint_id):
    """Return local-only checkpoint text and its safe availability label."""
    output, _ = run_entire(
        ["checkpoint", "explain", checkpoint_id, "--short", "--no-pager"]
    )
    raw_intent = output.strip() if output and output.strip() else None
    return LocalOnlyText(raw_intent), classify_completeness(checkpoint_id, raw_intent)


def migration_target():
    """Best-effort migration/table discovery from the checked-in demo files."""
    for path in sorted(Path("migrations").glob("*.sql")):
        if "validate" in path.name:
            continue
        match = re.search(r"ALTER\s+TABLE\s+([^\s]+)", path.read_text(), re.IGNORECASE)
        return str(path), match.group(1) if match else "unavailable"
    return "unavailable", "unavailable"


def latest_log_status():
    """Return only safe migration-log fields, never the note/error body."""
    required = (
        "DATABRICKS_SERVER_HOSTNAME",
        "DATABRICKS_HTTP_PATH",
        "DATABRICKS_TOKEN",
    )
    if any(not os.environ.get(name) for name in required):
        return None, "unavailable (Databricks credentials not set)"
    try:
        from databricks import sql

        with sql.connect(
            server_hostname=os.environ["DATABRICKS_SERVER_HOSTNAME"],
            http_path=os.environ["DATABRICKS_HTTP_PATH"],
            access_token=os.environ["DATABRICKS_TOKEN"],
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, checkpoint_id, context_completeness, ts "
                    "FROM warden.migration_log ORDER BY ts DESC LIMIT 1"
                )
                row = cur.fetchone()
    except Exception as error:
        return None, f"unavailable ({type(error).__name__})"
    if row is None:
        return None, "no migration attempts recorded"
    return {
        "status": row[0],
        "checkpoint_id": row[1],
        "context_completeness": row[2],
        "timestamp": row[3],
    }, None


def recommendation(completeness, log_row):
    if completeness != "complete":
        return "review locally — context incomplete"
    if log_row and log_row["status"] == "failed":
        return "do not proceed — latest migration failed; review locally"
    if log_row and log_row["status"] == "healed":
        return "review locally — latest migration healed before retrying"
    return "proceed — context complete; run migration with validation"


def render_report(checkpoint_id, intent, completeness, migration, table, log_row, log_message):
    """Render only safe metadata. `intent` is intentionally never revealed."""
    del intent
    lines = [
        "=== Warden safe resume report ===",
        f"Checkpoint: {checkpoint_id}",
        f"Context completeness: {completeness}",
        f"Migration: {migration}",
        f"Affected table: {table}",
    ]
    if log_row:
        lines.append(
            "Latest migration log: "
            f"status={log_row['status']}, "
            f"checkpoint={log_row['checkpoint_id']}, "
            f"context={log_row['context_completeness']}, "
            f"timestamp={log_row['timestamp']}"
        )
    else:
        lines.append(f"Latest migration log: {log_message}")
    lines.append(f"Recommended next action: {recommendation(completeness, log_row)}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Safely assess whether a Warden migration can be resumed"
    )
    parser.add_argument("checkpoint_id")
    args = parser.parse_args()

    intent, completeness = checkpoint_context(args.checkpoint_id)
    migration, table = migration_target()
    log_row, log_message = latest_log_status()
    print(
        render_report(
            args.checkpoint_id,
            intent,
            completeness,
            migration,
            table,
            log_row,
            log_message,
        )
    )


if __name__ == "__main__":
    main()
