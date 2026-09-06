#!/usr/bin/env python3
"""Integration tests against the real Databricks warehouse (Warden demo data).

Requires DATABRICKS_SERVER_HOSTNAME / DATABRICKS_HTTP_PATH / DATABRICKS_TOKEN
in the environment (exported from the gitignored `.env` by the invoking shell;
this file never reads or prints `.env`). Tests skip cleanly when the env vars
are absent or the connector isn't installed, so the file is safe to run in
environments without live credentials.

Synthetic demo data only -- asserts on warden.demo_users / warden.migration_log,
both owned by the Warden demo.
"""

import os
from pathlib import Path

import pytest

REQUIRED_ENV = ("DATABRICKS_SERVER_HOSTNAME", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN")
REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATE_SQL = REPO_ROOT / "migrations" / "001_validate.sql"

MIGRATION_LOG_DDL = """
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


@pytest.fixture(scope="module")
def cur():
    missing = [v for v in REQUIRED_ENV if v not in os.environ]
    if missing:
        pytest.skip(f"missing Databricks env vars: {', '.join(missing)}")
    try:
        from databricks import sql
    except ImportError as e:
        pytest.skip(f"databricks-sql-connector not installed: {e}")

    conn = sql.connect(
        server_hostname=os.environ["DATABRICKS_SERVER_HOSTNAME"],
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ["DATABRICKS_TOKEN"],
    )
    cursor = conn.cursor()
    yield cursor
    cursor.close()
    conn.close()


def test_demo_users_has_exactly_50_rows(cur):
    cur.execute("SELECT COUNT(*) FROM warden.demo_users")
    assert cur.fetchone()[0] == 50


def test_validate_finds_exactly_one_offender(cur):
    cur.execute(VALIDATE_SQL.read_text())
    rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0][2] == "legacy"


def test_migration_log_queryable(cur):
    cur.execute(MIGRATION_LOG_DDL)
    cur.execute("SELECT COUNT(*) FROM warden.migration_log")
    cur.fetchone()