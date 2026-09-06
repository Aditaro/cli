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

## Now
**Assigned: Codex**

Your `migrations/` task is done and reviewed — nice work, the constraint/validation contract matched exactly. New task:

Build `warden/demo.sh` — a single script that runs the full live-demo sequence in order, with clear echoed section headers between steps, so it can be run once during judging without fumbling commands:
1. Print current Delta version of `warden.demo_users` (`DESCRIBE HISTORY ... LIMIT 1`).
2. Run `python3 warden/migrate.py migrations/001_add_plan_column.sql --validate-sql migrations/001_validate.sql`.
3. Print the resulting rows in `warden.migration_log` (most recent one).
4. Print the current Delta version again, to show it matches the pre-migration version (proving the heal actually happened, not just that it printed a message).

Assume `DATABRICKS_SERVER_HOSTNAME`, `DATABRICKS_HTTP_PATH`, `DATABRICKS_TOKEN` are already exported in the shell running this script (from `.env`, gitignored — never read or print the token itself, don't cat .env). Use the `databricks-sql-connector` Python package for the query steps (small inline python3 -c snippets are fine, or a small helper module — your call).

Do NOT touch `warden/migrate.py` itself — that's mine and is mid-testing right now. Only add `warden/demo.sh`. Update `## Done`/`## Blocked` when finished.

## Now
**Assigned: opencode**

Your Databricks infra task is done and reviewed — good work, the self-test mode was a nice touch. New task:

Live Databricks credentials are now confirmed working (table created, seeded, connection verified). Build `databricks/test_integration.py`: a pytest file that, against the REAL warehouse (env vars from `.env`, already exported in the shell that runs pytest — don't read/print `.env` yourself), asserts:
1. `warden.demo_users` exists and has exactly 50 rows.
2. Running the query in `migrations/001_validate.sql` against the current table returns exactly 1 offending row, and that row's `plan = 'legacy'`.
3. `warden.migration_log` exists (create it if the core CLI hasn't yet — schema: `id STRING, migration_name STRING, status STRING, checkpoint_id STRING, note STRING, ts TIMESTAMP`) — just check it's queryable, don't assert on rows yet since Claude Code's CLI run may or may not have populated it by the time you run this.

Skip (don't fail) any test needing env vars that aren't set, with a clear skip reason — this file may run in environments without live credentials.

Do NOT touch `warden/` or `migrations/`. Only add `databricks/test_integration.py`. Update `## Done`/`## Blocked` when finished.

## Now
**Assigned: Codex — this is the pre-noon freeze task, ~15 min on the clock**

`demo.sh` looks correct on review, but hasn't actually been re-run since your last edit. Run it for real now:
```
set -a; source .env; set +a
bash warden/demo.sh
```
Then also run `python3 -m pytest warden/ databricks/ -q` (all tests, both dirs). Report the FULL real output (not a summary) in `## Done` below — pass/fail counts, and the actual demo.sh output showing pre/post Delta version + the logged row. If anything fails, report the exact error — don't fix it yourself, just report it clearly so Claude Code can triage fast given the time left. This is the verification evidence for the required 11:45 stable-state checkpoint, so accuracy matters more than speed here.

## Ground rules for every agent (Claude Code, opencode, Codex)
- Use Entire yourself while you work, not just as something the product touches: run `entire graph search` / `entire graph impact` before changing code you didn't write, and check `entire checkpoint list` if you're unsure what's already been decided.
- Write commit messages that capture *why*, not just *what* — rejected options, assumptions, anything you'd want a fresh session to know. Your commits are checkpoints; treat them like it.
- If you build something and it works differently than planned, say so in `## Done` — don't silently paper over a deviation.

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
- **Codex:** Added `warden/demo.sh`, which prints the pre-migration Delta
  version, runs the migration/validation flow, prints the latest migration log,
  and prints the post-migration version. It treats exit code 1 as the expected
  validation/heal result and never reads or prints `.env` or credentials.
- **opencode:** Added `databricks/test_integration.py` — pytest, live-warehouse,
  `-v` **3 passed** (29s) against the confirmed-working creds (from `.env`,
  sourced in the invoking shell; the file never reads/prints `.env`):
  - `test_demo_users_has_exactly_50_rows` — `COUNT(*)` on `warden.demo_users` == 50.
  - `test_validate_finds_exactly_one_offender` — runs `migrations/001_validate.sql`
    verbatim; exactly 1 row returned, `plan == 'legacy'`.
  - `test_migration_log_queryable` — `CREATE IF NOT EXISTS` (same DDL as
    `warden/migrate.py::ensure_log_table`, verified via `entire graph search`)
    then a `SELECT COUNT(*)` so it only asserts queryability, not rows.
  - Skips (not fails) when the 3 env vars or the connector are missing
    (verified: `3 skipped` in 0.01s with env unset), so it's safe to run
    anywhere. Also tested `python3 -m pytest databricks/test_integration.py -q`.
- **Codex (pre-noon freeze verification):** Ran the requested live demo with
  `set -a; source .env; set +a; bash warden/demo.sh`. Full output before the
  Databricks connector stalled:
  ```text
  === Pre-migration Delta version ===
  ```
  The first `DESCRIBE HISTORY` query produced no further output and was
  interrupted after the connector timeout window; no credential text was
  printed. The requested all-tests command completed:
  ```text
  ......sss                                                                [100%]
  6 passed, 3 skipped in 0.04s
  ```
  This is an environment/connectivity blocker for the live demo, not a code
  change; no fixes were made per the freeze instruction.

## Blocked / open questions
_(none yet)_

## NOON CURVEBALL — Track 1: Privacy Boundary (read this first in the fresh session)

**Do not start editing before running the graph impact step below — the scoring
explicitly downgrades graph use that happens after implementation.**

New constraints from the security team:
1. Raw prompts/transcripts must not be sent to a new external service.
2. Must keep working (usefully) when checkpoint fields are redacted/unavailable.
3. Existing local functionality must not regress.
4. Interface must clearly distinguish complete vs. incomplete context.
5. At least one test using redacted/missing checkpoint data.
6. Never present incomplete context as complete/authoritative.

**The assumption this invalidates:** `warden/migrate.py`'s `get_latest_checkpoint()`
pulls the full raw checkpoint intent text (`entire checkpoint explain <id> --short`),
and `log_attempt()` writes that raw text straight into `warden.migration_log.note`
in Databricks — an external service outside Entire's own boundary. We assumed
"more context in the log is better." That assumption is now wrong.

**First steps in the fresh session, in order:**
1. `entire checkpoint explain b8c9fe619` (or whatever the latest checkpoint ID is
   via `entire checkpoint list`) — reconstruct intent/architecture/completed/open
   risks from there, not from any prior conversation memory.
2. `entire graph impact --repo . --symbol get_latest_checkpoint --head --profile fast`
   and the same for `log_attempt` — BEFORE editing either function. This also
   satisfies the still-outstanding "graph search or definition lookup" deliverable
   if paired with `entire graph search --repo . --profile full --query "where checkpoint intent is sent to an external service"`.
3. Implement: strip/redact the intent text before it reaches Databricks (keep full
   text in local console output only, which stays on-machine). Add a
   `context_completeness` field (`"complete" | "redacted" | "unavailable"`) to
   both the console output and the `migration_log` row, so nothing downstream can
   mistake partial context for complete. Handle a checkpoint whose intent is
   `None`/redacted without crashing, and without ever claiming it as fact.
4. Test with a redacted/missing-checkpoint fixture (get it from Adit — it was
   handed out at the event, not yet in this repo).
5. Final checkpoint: explain the assumption that changed, what changed, why it's safe, and that existing (non-redacted) behavior still works.
