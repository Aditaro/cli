#!/usr/bin/env python3
"""Check that Entire and Databricks are ready for a Warden run.

This is intentionally an operator preflight, not another migration command.
By default it makes no warehouse request. ``--live`` performs only ``SELECT
1`` so a developer can verify the configured warehouse before starting the
live fail/heal demo. Output never includes credentials, checkpoint intent, or
raw database error text.
"""

import argparse
import json
import os

from migrate import run_entire


REQUIRED_CREDENTIALS = (
    "DATABRICKS_SERVER_HOSTNAME",
    "DATABRICKS_HTTP_PATH",
    "DATABRICKS_TOKEN",
)


def entire_readiness():
    """Verify checkpoint access without exposing checkpoint content."""
    output, _ = run_entire(["checkpoint", "list", "--json"])
    if output is None:
        return {"state": "unavailable"}
    try:
        json.loads(output)
    except json.JSONDecodeError:
        return {"state": "unavailable"}
    return {"state": "ready"}


def databricks_readiness(live=False, environment=os.environ):
    """Check configuration, optionally with a harmless warehouse round-trip."""
    missing = [name for name in REQUIRED_CREDENTIALS if not environment.get(name)]
    if missing:
        return {"state": "unavailable", "missing": missing}
    if not live:
        return {"state": "configured"}
    try:
        from databricks import sql

        with sql.connect(
            server_hostname=environment["DATABRICKS_SERVER_HOSTNAME"],
            http_path=environment["DATABRICKS_HTTP_PATH"],
            access_token=environment["DATABRICKS_TOKEN"],
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
    except Exception as error:
        return {"state": "unavailable", "error_type": type(error).__name__}
    return {"state": "ready"}


def report(live=False, environment=os.environ):
    """Return machine-readable, non-sensitive combined readiness state."""
    entire = entire_readiness()
    databricks = databricks_readiness(live, environment)
    ready = entire["state"] == "ready" and databricks["state"] == (
        "ready" if live else "configured"
    )
    return {
        "entire": entire,
        "databricks": databricks,
        "warehouse_checked": live,
        "ready": ready,
    }


def render_human(result):
    lines = ["=== Warden preflight ==="]
    lines.append("Entire checkpoints: " + result["entire"]["state"])
    databricks = result["databricks"]
    lines.append("Databricks: " + databricks["state"])
    if databricks.get("missing"):
        lines.append("Missing variables: " + ", ".join(databricks["missing"]))
    if databricks.get("error_type"):
        lines.append("Warehouse check: unavailable (" + databricks["error_type"] + ")")
    lines.append(
        "Result: " + ("ready to run Warden" if result["ready"] else "resolve the items above")
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Check Entire and Databricks readiness for a Warden migration"
    )
    parser.add_argument(
        "--live", action="store_true", help="also issue a read-only SELECT 1 to Databricks"
    )
    parser.add_argument("--json", action="store_true", help="emit structured JSON")
    args = parser.parse_args()
    result = report(args.live)
    print(json.dumps(result, indent=2) if args.json else render_human(result))
    raise SystemExit(0 if result["ready"] else 1)


if __name__ == "__main__":
    main()
