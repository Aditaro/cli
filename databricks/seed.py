#!/usr/bin/env python3
"""Seed warden.demo_users with ~50 clearly-synthetic rows for the Warden demo.

All data below is fabricated for the demo — emails use the reserved
`.example.invalid` domain and no row corresponds to a real person.

Credentials come from the environment (never hardcode, never commit a .env):
  DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN

Usage:
  seed.py                 # insert rows into warden.demo_users
  seed.py --self-test     # verify the generated rows without a connection
"""

import datetime as dt
import os
import sys

from databricks import sql

ROW_COUNT = 50
VALID_PLANS = ("free", "pro", "enterprise")
# Contract with migrations/001_validate.sql: any plan outside VALID_PLANS
# (or NULL) is an offender that must trip the demo migration's validation.
OFFENDER_USER_ID = 7
OFFENDER_PLAN = "legacy"


def generated_rows():
    """Return (id, email, plan, created_at) tuples; deterministic, synthetic."""
    rows = []
    for i in range(1, ROW_COUNT + 1):
        plan = VALID_PLANS[i % len(VALID_PLANS)]
        if i == OFFENDER_USER_ID:
            plan = OFFENDER_PLAN
        created = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=i)
        rows.append((i, f"user{i:03d}@example.invalid", plan, created))
    return rows


def self_test():
    rows = generated_rows()
    assert len(rows) == ROW_COUNT
    offenders = [r for r in rows if r[2] is None or r[2] not in VALID_PLANS]
    assert offenders, "seed must contain at least one plan offender for the demo"
    assert all("@example.invalid" in r[1] for r in rows)
    assert any(r[2] == "free" for r in rows)
    print(f"self-test OK: {len(rows)} synthetic rows, {len(offenders)} offender(s)")
    print("  offender:", offenders[0][1], repr(offenders[0][2]))
    return 0


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        return self_test()

    endpoint = os.environ.get("DATABRICKS_SERVER_HOSTNAME")
    http_path = os.environ.get("DATABRICKS_HTTP_PATH")
    token = os.environ.get("DATABRICKS_TOKEN")
    missing = [
        name
        for name, val in (
            ("DATABRICKS_SERVER_HOSTNAME", endpoint),
            ("DATABRICKS_HTTP_PATH", http_path),
            ("DATABRICKS_TOKEN", token),
        )
        if not val
    ]
    if missing:
        print("missing env vars: " + ", ".join(missing), file=sys.stderr)
        return 2

    rows = generated_rows()
    with sql.connect(
        server_hostname=endpoint, http_path=http_path, access_token=token
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM warden.demo_users")
            cur.executemany(
                "INSERT INTO warden.demo_users (id, email, plan, created_at) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
    print(f"seeded {len(rows)} synthetic rows into warden.demo_users")


if __name__ == "__main__":
    sys.exit(main())