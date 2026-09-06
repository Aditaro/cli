# Task Board (Claude Code ↔ opencode/Codex)

Claude Code is the coordinator: writes `## Now` before handing off a slice of work.
Executors (opencode, Codex) update `## Done` / `## Blocked` when finished, then Claude Code reviews the diff and writes the next `## Now`.

## Now
**Assigned: opencode**

Build `databricks/setup.sql` and `databricks/seed.py`:
- `setup.sql`: `CREATE TABLE IF NOT EXISTS warden.demo_users (id BIGINT, email STRING, plan STRING, created_at TIMESTAMP) USING DELTA` — this is the demo migration target. Keep it simple, one table.
- `seed.py`: inserts ~50 rows of clearly-synthetic sample data (label it as synthetic in a comment) via `databricks-sql-connector`, using env vars `DATABRICKS_SERVER_HOSTNAME`, `DATABRICKS_HTTP_PATH`, `DATABRICKS_TOKEN` (never hardcode credentials, never commit a `.env`).

Also stub `databricks/dashboard_queries.sql` with one query: count of migration attempts vs. heals over time, assuming a `warden.migration_log` table with columns `(id, migration_name, status, checkpoint_id, ts)` (Claude Code will create/populate this table from the core CLI).

Do NOT touch anything outside `databricks/`. Update `## Done` or `## Blocked` below when finished.

## Now
**Assigned: Codex**

Build the demo migration scenario in `migrations/`:
- `migrations/001_add_plan_column.sql` — a migration against `warden.demo_users` (id BIGINT, email STRING, plan STRING, created_at TIMESTAMP) that is designed to plausibly fail a validation check (e.g. adds a business-rule constraint like "plan must be one of 'free','pro','enterprise'" applied to existing rows, where the seed data will contain at least one violating row).
- `migrations/001_validate.sql` — a SQL query that returns offending rows if the migration's business rule is violated (0 rows = pass). This is what Warden's core script runs after applying the migration.
- `migrations/README.md` — one paragraph explaining the intended demo narrative: what the migration does, why it's expected to fail on the seeded data, and what "healed" should look like.

Do NOT touch anything outside `migrations/`. Coordinate with opencode's seed data (`databricks/seed.py`) only insofar as: your validation rule should assume at least one seeded row will violate it — note the exact violating condition you assume in `migrations/README.md` so opencode's seed data can be checked against it.

Update `## Done` or `## Blocked` below when finished.

## Context
- **Pivoted** from the original "Handoff" idea (checkpoint-mined onboarding briefing) to **Warden**: a self-healing DB migration guard. Reason: Warden has a higher ceiling on Problem/Innovation and Demo, cleaner Entire Graph fit (impact analysis before a schema change), at the cost of higher technical-implementation risk. See BUILDATHON.md for full rationale.
- Warden's core loop: checkpoint intent → graph impact check → apply migration → validate → on failure, Delta time-travel rollback + explain using the checkpoint's recorded intent → checkpoint the outcome.
- `warden.demo_users` is the one migration target for the demo. Keep scope to ONE table, ONE migration, ONE validation check — this is a narrow vertical slice, not a general migration framework.

## Done
- **opencode:** Added `databricks/setup.sql`, `databricks/seed.py`, and
  `databricks/dashboard_queries.sql`.
  - `setup.sql`: `CREATE TABLE IF NOT EXISTS warden.demo_users (id BIGINT, email
    STRING, plan STRING, created_at TIMESTAMP) USING DELTA` — the single demo
    migration target.
  - `seed.py`: inserts 50 clearly-synthetic rows (emails on reserved
    `example.invalid` domain, marked synthetic in comments) via
    `databricks-sql-connector` using env vars only (`DATABRICKS_SERVER_HOSTNAME`
    / `DATABRICKS_HTTP_PATH` / `DATABRICKS_TOKEN`; fails exit 2 if any missing;
    no hardcoded creds, no `.env`). Deletes existing rows first, then inserts —
    idempotent. Exactly one offender per the Codex contract: user id 7 has
    `plan='legacy'` (user007@example.invalid), so `001_validate.sql` fires.
    `seed.py --self-test` verifies row count, offender presence, and synthetic
    emails without a connection.
  - `dashboard_queries.sql`: one query grouping migration attempts/applied vs
    heals vs failures per day from `warden.migration_log`, which it assumes is
    created/populated by the Warden core CLI with `(id, migration_name, status,
    checkpoint_id, ts)`.
  - Constraint on plans: `free`/`pro`/`enterprise` (matches
    `migrations/001_validate.sql`).
  - **Not run against the live warehouse** — needs real values for the 3 env
    vars; run `python3 setup.sql`-equivalent / `python3 seed.py` once creds are
    in place to validate end to end.
- **Codex:** Added `migrations/001_add_plan_column.sql`, `001_validate.sql`, and
  `README.md`. The validation contract is that any `plan` value outside
  `free`, `pro`, or `enterprise` (including `NULL`) is an offender; the synthetic
  seed should include at least one such row, e.g. `legacy`.

## Blocked / open questions
_(none yet)_
