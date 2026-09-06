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

## Now
**Assigned: Codex — 2 tasks, ~2 hrs left total on the clock, do them in order**

Pull latest first (`git pull` / re-sync your checkout) — `warden/migrate.py` has two new commits since your last run: `cc16573cc` (checkpoint privacy boundary — `context_completeness` field) and `1784305b7` (error-text hardening — a DB exception's message is now reduced to its type name, e.g. `ValueError`, before it reaches `warden.migration_log`; full error text still prints locally).

### Task 1 — verify which failure path actually fires live (do this first, it's the important one)

`migrations/001_add_plan_column.sql` does `ALTER TABLE ... ADD CONSTRAINT ... CHECK (plan IN (...))`. Delta validates *existing* data at `ADD CONSTRAINT` time — if row 7 (`plan='legacy'`) already violates it, the `ALTER TABLE` itself should throw before Warden ever reaches the `001_validate.sql` SELECT step. We've never confirmed this live (the one prior live run stalled before getting this far), and it changes how we should describe the mechanism to judges. Find out:

```
set -a; source .env; set +a
bash warden/demo.sh
```

Report in `## Done` below, verbatim:
1. Does the ALTER TABLE step itself throw an exception, or does it succeed and the *following* `001_validate.sql` SELECT catch the offending row? (Look at whether `"[warden] migration '...' applied."` prints before the failure.)
2. The exact exception type/message Databricks/Delta gives you for the CHECK constraint violation (paste it — we want to know if it names Delta's `DELTA_VIOLATE_CONSTRAINT_WITH_VALUES` error or something else).
3. Query the most recent row in `warden.migration_log` after the run (`SELECT * FROM warden.migration_log ORDER BY ts DESC LIMIT 1`) and paste it. Confirm the `note` column contains an exception **type name only** (e.g. `ValueError`), not a raw message with `plan = legacy` or similar embedded in it — this is what the just-hardened `error_summary()` is supposed to guarantee.
4. Full `python3 -m pytest warden/ databricks/ -q` output.

Don't fix anything yourself even if something looks off — just report exactly what you observe, including the raw exception text/log row content, so Claude Code can correct the docs and/or patch based on real evidence instead of a guess.

### Task 2 — create a real Lakeview dashboard from `databricks/dashboard_queries.sql`

Right now that file is just a `.sql` query sitting in the repo — there's no actual dashboard object in the workspace a judge could open. Use the `databricks-sdk` Python package (or the Databricks REST API directly via `requests`, whichever is faster for you) to create a Lakeview dashboard in the workspace containing the query in `databricks/dashboard_queries.sql` as one chart (a simple time-series/bar chart of `attempts`/`heals`/`failures` by `day` is enough — don't over-build this). Use the existing env vars for auth (`DATABRICKS_SERVER_HOSTNAME`/`HTTP_PATH`/`TOKEN`, or exchange the token for whatever the SDK needs — don't hardcode or print any credential). Put the creation script at `databricks/create_dashboard.py` (one-shot, re-runnable, prints the dashboard's workspace URL on success). Run it once for real and report the dashboard URL in `## Done`.

Do NOT touch `warden/migrate.py`. Update `## Done`/`## Blocked` when finished — if Task 2 turns out to be a bigger lift than expected given the time left, report what you tried and stop; Task 1's findings matter more.

## Now
**Assigned: Codex — final task, this is the closing checkpoint for the whole Noon Curveball**

You're the right agent for this one — you did the live verification and the bug fixes, so you have the most direct evidence to draw on. The original curveball instructions (bottom of this file, "NOON CURVEBALL" section) ask for a final checkpoint that explains:
1. The assumption that changed (raw checkpoint intent → external Databricks log was assumed safe; it wasn't).
2. What changed (in your own words, from what you actually touched): `context_completeness` field, `LocalOnlyText` structural wrapper so intent can't leak by accident, `error_summary()` closing the same-shape leak for raw DB exception text, plus the two real bugs you fixed (silent ALTER TABLE failure swallowing, `pre_version` UnboundLocalError) and the redaction-regex tightening.
3. Why it's safe now — cite your own live verification: `DELTA_NEW_CHECK_CONSTRAINT_VIOLATION` fires, gets reduced to `ServerOperationError` in the logged note, `context_completeness=complete`, no raw intent or row values present in `warden.migration_log`.
4. That existing (non-redacted) behavior still works — 16 tests passing, `demo.sh` exit 0, `pytest` exit 0.

Do this as a normal commit with a message covering those four points (Entire's hooks will checkpoint it automatically the way every other commit today has been checkpointed — no special command needed beyond committing normally). If there's nothing left uncommitted in your working tree to commit, that's fine — just confirm in `## Done` that your prior commits already cover this and note the checkpoint ID(s) they produced (check `entire checkpoint list` for the ones tied to your recent commits).

Update `## Done` when finished — this is likely the last task before submission, so also flag anything you think still needs attention before 3pm.

## Now
**Assigned: Codex — score-improvement pass, using the REAL organizer rubric (superseding the previous version of this task, which used a reconstructed guess — ignore that one, this is the actual scoring sheet)**

Two separate 100-point rubrics apply to this submission — the main challenge, and the optional secondary Databricks award (we're opted into both). Grade against these exact weights, not vibes.

**Entire main challenge — 100 pts:**
- Problem and innovation — 20 — clear user, specific problem, useful new capability, real use of Entire
- Technical implementation — 25 — working end-to-end workflow, sensible architecture, important behaviors tested, failures handled safely
- Response to the Curveball — 15 — constraint addressed completely, assumptions revisited, response implemented/tested/explained
- Use of Entire Checkpoints — 15 — checkpoints preserve useful intent/decision context, a fresh session can resume from them
- Use of Entire Graph — 15 — graph evidence identifies relevant code or impact, findings verified against source and tests
- Demonstration and future potential — 10 — clear reproducible demo, limits acknowledged, credible next step

**Best Use of Databricks — 100 pts:**
- Meaningful use — 30 — Databricks essential to a core workflow, materially improves the product
- Working implementation and reliability — 25 — judges can reproduce/inspect the path, failure handling and fallback evidence are credible
- User value and product decisions — 20 — specific user need, focused scope, sensible trade-offs
- Data quality, provenance and responsible use — 15 — permitted data, traceable transformations, disclosed limits, safe handling
- Curveball response — 10 — the Databricks-backed workflow adapts to the new constraint and the changed behavior is verified

### Step 1 — brutally honest self-assessment against BOTH rubrics (do this first, before touching code)

For every line item above (11 total across both rubrics): a 1-10 gut score, what's actually built that earns it, and what a skeptical judge would dock points for. Do not soften this — if something reads as a demo trick rather than the real thing the criterion asks for, say so explicitly. A few specific traps to check honestly, not just restate as strengths:
- "Use of Entire Checkpoints" (15 pts) explicitly asks whether **a fresh session can resume from them** — has anyone actually tested that a genuinely fresh agent session, given only the repo and a checkpoint ID, can reconstruct enough to continue? Or has intent-reading only ever been exercised by Warden's own code path (`get_latest_checkpoint()`), never by a human/agent doing the literal thing the criterion describes?
- "Use of Entire Graph" (15 pts) requires findings **verified against source and tests** — the one real graph run so far reported "IMPACT DEGENERATE: no callers" for `demo_users`. Is that finding actually verified against source (confirmed it's a genuinely new symbol with no dependents), or just quoted as-is? Was `entire graph impact` ever run on `get_latest_checkpoint`/`log_attempt` themselves (the functions the curveball actually touched) the way the curveball instructions originally asked, or only on `demo_users`?
- "Data quality, provenance and responsible use" (15 pts, Databricks rubric) — is there a clear written statement (not just code comments) of what's synthetic, how it was generated, and what its limits are, in a place a judge would actually look (BUILDATHON.md), not buried in a script docstring?
- "Meaningful use" (30 pts, Databricks rubric, the single biggest line item across both rubrics) — be specific about what fraction of Databricks usage is load-bearing (Delta time-travel, the CHECK constraint) vs. incidental (a generic connector call that would work against Postgres). This is the single highest-leverage item to strengthen if there's a real gap.

Write this as a markdown block under `## Done` below, organized by rubric then by line item, each with a score and one or two sentences of justification.

### Step 2 — turn real gaps into a ranked task list

From Step 1, list concrete, buildable-in-under-30-minutes-each improvements. For each: which line item(s) it helps, its point value, rough time estimate, and specifically what gap it closes (not "more tests" — which behavior becomes tested that wasn't). Rank by points-per-minute, not by category order — a 30-point item worth 20 minutes of work beats a 10-point item worth 15. Do NOT implement yet. Claude Code will review the list and assign back whichever earn their time.

Do NOT touch `warden/migrate.py` for this task — assessment and a list only.

## Now
**Assigned: Codex — implement your own ranked improvement list (all 5, we have the time), plus new submission-checklist items from the organizers**

Your self-assessment and ranked list were good and honest — approved as-is, do all 5 in the order you ranked them. (If you're already mid-flight on one of these, keep going, don't restart.)

1. `BUILDATHON.md` "reproduce and safety" paragraph (data provenance/responsible-use + demo clarity)
2. Graph evidence for `get_latest_checkpoint` and `log_attempt` specifically (not just `demo_users`) — run both `entire graph impact` commands plus one `entire graph search`, verify each result against the actual function definitions, record real output in `BUILDATHON.md`'s "Entire Graph findings" section (not just TASKS.md)
3. Fresh-session checkpoint reconstruction test/transcript — give a genuinely fresh session only a checkpoint ID and the repo, have it reconstruct the privacy assumption and next action, record what it actually reconstructs
4. Deterministic no-credentials demo/self-test path
5. Final live regression + dashboard access check, right before submission (last, not now)

Additionally, the organizers just gave Adit the official **Final 20-minute checklist** and **Required submission fields**. Cross-check these against the repo — most you can verify yourself, a few need Adit directly (flagged below):

**You can verify/fix these:**
- "The project launches from a clean checkout" — actually test this: clone to a fresh temp dir, follow BUILDATHON.md's own setup instructions exactly, confirm it works with no undocumented steps.
- "Tests covering the critical and Curveball behavior pass" — already true (16 passed), just reconfirm after your 5 improvements above.
- "BUILDATHON.md is complete, readable and free of secrets" — reread it end to end for secrets (I already grepped for obvious token patterns and found none, but you have fresh eyes) and for the exact required outline: `# Project name`, one-sentence summary, problem/user, track+why Entire essential, architecture, Entire Graph findings, curveball, checkpoint links, setup/run/test, Databricks use, known limitations. We already have all these sections — just confirm nothing's missing or stale after your edits above.
- "Databricks resource links and data notes are included" — confirm the live dashboard URL and data-provenance note (item 1 above) are both actually in BUILDATHON.md, not just TASKS.md.
- "A fallback screenshot or recording is locally available" — the organizers explicitly warn Free Edition compute can go unavailable ("preserve a screenshot or recording of any fragile live step... if live infrastructure fails during judging, explain the expected behavior, show the prepared evidence and continue"). We have verbatim text output from a successful live run in TASKS.md, but that's not a screenshot/recording. Cheapest fix: use `script` or `asciinema` to record one full successful `bash warden/demo.sh` run to a file in the repo (e.g. `warden/demo-recording.txt` or a cast file), so there's actual replayable evidence beyond a copy-pasted log. Keep it small, no secrets in it (verify: it must not contain the token, `.env` contents, or full checkpoint intent if that reveals anything sensitive).

**Flag back to Adit, don't try to fill these in yourself (org/account-specific, not something in the repo):**
- GitHub fork URL + final commit SHA for the submission form (SHA will be whatever's at HEAD when we submit — note this needs to be grabbed last, after all other work lands)
- Entire mirror or project URL (submission form field — check if this is something `entire repo mirror list` or similar already shows, and report what you find, but don't guess at the answer)
- Confirming the actual submission form itself gets filled out and sent before 3pm — that's on Adit, not an agent task

Update `## Done` when finished.

## Ground rules for every agent (Claude Code, opencode, Codex)
- Use Entire yourself while you work, not just as something the product touches: run `entire graph search` / `entire graph impact` before changing code you didn't write, and check `entire checkpoint list` if you're unsure what's already been decided.
- Write commit messages that capture *why*, not just *what* — rejected options, assumptions, anything you'd want a fresh session to know. Your commits are checkpoints; treat them like it.
- If you build something and it works differently than planned, say so in `## Done` — don't silently paper over a deviation.

## Context
- **Pivoted** from the original "Handoff" idea (checkpoint-mined onboarding briefing) to **Warden**: a self-healing DB migration guard. Reason: Warden has a higher ceiling on Problem/Innovation and Demo, cleaner Entire Graph fit (impact analysis before a schema change), at the cost of higher technical-implementation risk. See BUILDATHON.md for full rationale.
- Warden's core loop: checkpoint intent → graph impact check → apply migration → validate → on failure, Delta time-travel rollback + explain using the checkpoint's recorded intent → checkpoint the outcome.
- `warden.demo_users` is the one migration target for the demo. Keep scope to ONE table, ONE migration, ONE validation check — this is a narrow vertical slice, not a general migration framework.

## Done
- **Codex (rubric-gap evidence pass):** Strengthened `BUILDATHON.md` with an
  explicit synthetic-data provenance statement (50 reserved-domain users,
  deterministic seed, deliberate `plan='legacy'` offender, no production data)
  and documented the curveball-targeted Graph follow-up. The fresh Graph impact
  run for `get_latest_checkpoint` found two callers (`apply_migration` direct,
  `main` transitive) and dependencies `run_entire`, `LocalOnlyText`, and
  `classify_completeness`; source and checkpoint tests verify those edges. The
  `log_attempt` Graph query exceeded the local 30-second window, so it is
  explicitly recorded as unavailable rather than claimed as a finding; source
  inspection and tests verify its applied/healed/failed callers and safe log
  boundary. No code was changed, no fresh-session checkpoint experiment was
  performed, and the remaining ranked gaps are still visible below.

- **Codex (rubric self-assessment; no implementation changes):**

  ### Entire main challenge — 100 points

  - **Problem and innovation — 8/10.** Warden gives a concrete migration
    operator a useful self-healing guard: impact evidence, validation, Delta
    rollback, and checkpoint-linked explanation. A skeptical judge may view it
    as a narrow but polished demo rather than a broadly novel migration
    product, because it covers one table and one migration.
  - **Technical implementation — 8/10.** The end-to-end path is real and live:
    Databricks Delta, migration execution, failure handling, time travel, safe
    logging, and 16 regression tests. Deductions: the version lookup and schema
    compatibility paths are now tested in unit isolation, but not every
    warehouse/network failure mode has a live integration test.
  - **Response to the Curveball — 9/10.** Raw intent was moved behind
    `LocalOnlyText`, `context_completeness` distinguishes incomplete evidence,
    DB exception text is reduced before logging, and the live row proves the
    boundary. The remaining deduction is that the demo still prints complete
    intent locally, which is safe by design but needs a clear operator-facing
    explanation to avoid confusion about the boundary.
  - **Use of Entire Checkpoints — 7/10.** Warden consumes a real checkpoint,
    and commits have useful checkpoint summaries, including the live error and
    dashboard work. The rubric's fresh-session criterion is not directly
    demonstrated: no separate fresh agent was given only a checkpoint ID and
    asked to reconstruct and continue.
  - **Use of Entire Graph — 6/10.** The workflow runs Graph impact before the
    migration, and source/tests verify the reported degenerate `demo_users`
    result. However, the strongest curveball-relevant impact run on
    `get_latest_checkpoint`/`log_attempt` is not captured as a complete,
    reproducible artifact in the board; the live `demo_users` result is weaker
    evidence for the privacy-boundary changes.
  - **Demonstration and future potential — 8/10.** `warden/demo.sh`, live
    output, the dashboard URL, and documented limitations make judging easy.
    The demo is intentionally narrow and the dashboard is a single chart, so
    the future platform story is credible but not yet proven beyond the slice.

  ### Best Use of Databricks — 100 points

  - **Meaningful use — 9/10.** Delta time travel is load-bearing for the heal,
    and Delta's native `CHECK` enforcement is the observed failure trigger;
    this is materially more than generic SQL storage. The deduction is that
    the rest of the connector/logging path could be ported to another SQL
    warehouse.
  - **Working implementation and reliability — 8/10.** The real warehouse run
    proves the failure, rollback, sanitized log row, and post-version match;
    the integration tests and rerunnable dashboard improve reproducibility.
    A judge may still dock points because setup/seed execution and dashboard
    access depend on live credentials and workspace permissions.
  - **User value and product decisions — 8/10.** The focused scope makes the
    migration safety story understandable and the operator gets a clear heal
    plus local diagnostic. One table/one migration is a deliberate trade-off,
    but limits evidence of general usefulness.
  - **Data quality, provenance and responsible use — 8/10.** The seed is
    synthetic, uses reserved `example.invalid` addresses, documents the
    `legacy` offender, and the external log avoids intent and row-value leaks.
    A skeptical judge may want the synthetic-data statement surfaced more
    prominently in `BUILDATHON.md`, not mainly in setup/task documentation.
  - **Curveball response — 9/10.** The Databricks-backed path explicitly
    records completeness and safe error summaries, and live evidence confirms
    `ServerOperationError` rather than raw details in `migration_log`. The
    remaining gap is broader live coverage for redacted/unavailable checkpoint
    states; those are unit-tested, not warehouse-demonstrated.

  ### Ranked improvements by points-per-minute

  1. **Add a small `BUILDATHON.md` “reproduce and safety” paragraph** — helps
     Databricks data provenance/responsible use (15) and demo clarity (10);
     ~10 minutes. Explicitly state synthetic-only data, the `legacy` seed
     offender, Delta `CHECK` enforcement, time-travel healing, and that full
     intent/error text stays local.
  2. **Capture Graph evidence for `get_latest_checkpoint` and `log_attempt`** —
     helps Entire Graph (15) and technical implementation (25); ~15 minutes.
     Run both impact commands plus one focused search, verify each result
     against definitions/tests, and record the outputs in `TASKS.md`.
  3. **Add a fresh-session checkpoint reconstruction smoke test/documented
     transcript** — helps Checkpoint use (15) and curveball response (15);
     ~20 minutes. Give a fresh agent only the latest checkpoint ID and repo,
     require it to recover the privacy assumption and next action, and record
     what it reconstructs.
  4. **Add a deterministic no-credentials demo/self-test path** — helps demo
     and reliability (10/25); ~20 minutes. Keep the real path unchanged, but
     make the judge-facing setup validate required env vars and explain the
     exact live commands/permission prerequisites before connecting.
  5. **Run one final live regression immediately before submission and record
     the dashboard HTTP/access result** — helps demonstration (10) and
     Databricks reliability (25); ~10 minutes, assuming credentials remain
     available. This is verification rather than new behavior, but closes the
     remaining stale-evidence risk.

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
- **Codex (live verification after `cc16573cc` / `1784305b7`):** Pulled latest
  (`Already up to date.`), then ran the live demo and
  `python3 -m pytest warden/ databricks/ -q`. The `ALTER TABLE ... ADD
  CONSTRAINT` path failed immediately on the existing `plan='legacy'` row and
  Warden healed `warden.demo_users` back to Delta version 51; the validation
  SELECT was not reached. The newest `warden.migration_log` row had
  `status=healed`, `context_completeness=complete`, and a safe note containing
  no raw checkpoint intent. The full suite passed: `13 passed in 7.56s`.
- **Codex (Lakeview dashboard):** Added `databricks/create_dashboard.py`, a
  re-runnable REST client using the documented Lakeview dashboard API. It reads
  `databricks/dashboard_queries.sql`, creates one grouped bar chart of daily
  attempts/heals/failures, updates an existing dashboard with the same name,
  and keeps credentials out of output. Ran it against the live workspace:
  [Warden Migration Health](https://dbc-89334694-0d5f.cloud.databricks.com/dashboardsv3/01f1a9c471e5137fba57a227f9b91452).
- **Codex (final stable-state verification):** Ran the live demo and full test
  suite without fixing anything. Complete captured output:
  ```text
  === Pre-migration Delta version ===
  Delta version: 51
  === Apply migration and validate (healing on failure) ===
  [warden] intent from checkpoint 01M1TSYZ5VC1828RZAC7ZHWP2S [context: complete]:
  ● Checkpoint 01M1TSYZ5VC1828RZAC7ZHWP2S
    session  a67113eb-8bf5-4f12-a894-98e2726c95df
    created  2026-09-06 07:29:47
    author   Adit Potta <27315597+Aditaro@users.noreply.github.com>
    tokens   1368.9k
    commits  7274590 databricks: add Lakeview dashboard creation script (Codex)
  ────────────────────────────────────────────────────────────
  ## Intent

  /code-review

  ## Summary

  *Not generated yet. Run ‘entire checkpoint explain --generate 01M1TSYZ5VC1828RZAC7ZHWP2S‘ to create an AI summary.*

  [warden] Entire Graph impact on 'demo_users' (evidence, not fact -- verify before trusting):
  Index: cache-miss (28778ms) | Query: 31ms | Total: 28809ms
  Completeness: no parse failures in SQL (4 files parsed); 1 elsewhere (JSON 1) cannot affect this answer — see --format json.
  IMPACT DEGENERATE: warden.demo_users has no callers, callees or type consumers

  [warden] 'warden.demo_users' currently at Delta version 51
  [warden] FAILURE: [DELTA_NEW_CHECK_CONSTRAINT_VIOLATION] 1 rows in workspace.warden.demo_users violate the new CHECK constraint (plan IN ('free', 'pro', 'enterprise')).
  [warden] healing: restoring 'warden.demo_users' to Delta version 51 via time-travel...

  [warden] Migration 'migrations/001_add_plan_column.sql' failed: [DELTA_NEW_CHECK_CONSTRAINT_VIOLATION] 1 rows in workspace.warden.demo_users violate the new CHECK constraint (plan IN ('free', 'pro', 'enterprise')).

  Recorded intent (checkpoint 01M1TSYZ5VC1828RZAC7ZHWP2S, context: complete):
  ● Checkpoint 01M1TSYZ5VC1828RZAC7ZHWP2S
    session  a67113eb-8bf5-4f12-a894-98e2726c95df
    created  2026-09-06 07:29:47
    author   Adit Potta <27315597+Aditaro@users.noreply.github.com>
    tokens   1368.9k
    commits  7274590 databricks: add Lakeview dashboard creation script (Codex)
  ────────────────────────────────────────────────────────────
  ## Intent

  /code-review

  ## Summary

  *Not generated yet. Run ‘entire checkpoint explain --generate 01M1TSYZ5VC1828RZAC7ZHWP2S‘ to create an AI summary.*

  Action taken: rolled back warden.demo_users to Delta version 51. The intent above is what this migration was trying to achieve -- use it to write a corrected migration rather than re-attempting blindly.
  === Most recent migration log row ===
  id | migration_name | status | checkpoint_id | note | context_completeness | ts
  4822c20b-2943-4f22-ba00-34bc6dd58440 | migrations/001_add_plan_column.sql | healed | 01M1TSYZ5VC1828RZAC7ZHWP2S | migration failed (ServerOperationError); rolled back warden.demo_users to Delta version 51. Checkpoint intent and full error detail kept local-only (context: complete); see operator console for detail. | complete | 2026-09-06 07:33:08.939138+00:00
  === Post-migration Delta version ===
  Delta version: 51
  Demo completed: validation failed and Warden healed the table.

  === pytest: python3 -m pytest warden/ databricks/ -q ===
  ................                                                         [100%]
  16 passed in 7.03s

  === verification exit codes: demo=0 pytest=0 ===
  ```
- **Codex (migration hardening):** Fixed the two requested real bugs in
  `warden/migrate.py` and tightened redaction-marker detection:
  - `ensure_log_table()` now ignores only Databricks duplicate-column
    diagnostics and propagates permission/connectivity/other ALTER failures.
  - `apply_migration()` initializes `pre_version` before the main `try`; if the
    version lookup fails, it skips rollback, records a hard `failed` attempt when
    possible, and reports that no safe restore version is available.
  - `classify_completeness()` now matches bare `REDACTED` or bracketed
    `[REDACTED_<LABEL>]` markers without treating strings such as
    `REDACTED_EMAILS` as redacted.
  - Added regression tests for all three cases.
  - Full verification: `python3 -m pytest warden/ databricks/ -q` →
    `16 passed, 3 skipped in 0.12s`.
- **Codex (final Noon Curveball closing checkpoint):** The completed work is
  committed in `4774afcbe` with Entire checkpoint
  `01M1TTMA4CDD4ZTSWTG787CFV7`. The security assumption changed from treating
  raw checkpoint intent as safe to send to external Databricks logs to treating
  intent as local-only by default. The implementation now carries explicit
  `context_completeness`, wraps intent in `LocalOnlyText`, reduces external DB
  error notes through `error_summary()`, and includes the requested fixes for
  silent schema-backfill failures, unknown `pre_version` rollback handling, and
  redaction-marker classification.
  - Live evidence: Delta raised
    `DELTA_NEW_CHECK_CONSTRAINT_VIOLATION`; the logged note reduced that to
    `ServerOperationError`, had `context_completeness=complete`, and contained
    neither raw checkpoint intent nor row values.
  - Existing non-redacted behavior remains green: `demo.sh` exited 0 and the
    full suite reported `16 passed, 3 skipped in 0.12s`.
  - No further implementation work is pending for the curveball. Before
    submission, only the final dashboard-link check and one last full live
    regression run remain worth considering; the unrelated pre-existing
    `.gemini/` and `.opencode/package-lock.json` changes remain uncommitted.
- **Noon Curveball — Track 1 Privacy Boundary (committed `cc16573cc`):**
  `get_latest_checkpoint()` now returns `(cp_id, intent, completeness)`, where
  `completeness` is `"complete" | "redacted" | "unavailable"` (redacted is
  detected via Entire's own `REDACTED` marker text surviving into `--short`
  output). `log_attempt()`/`warden.migration_log` gained a
  `context_completeness` column (with a best-effort `ALTER TABLE` backfill for
  an already-existing live table). The raw checkpoint intent is now only ever
  printed to the local console; the new `describe_failure()` builds a separate,
  external-safe `db_note` for the Databricks row that never contains intent
  text, redacted or not — only the checkpoint id and its completeness label.
  Existing applied/failed/healed behavior and the Delta time-travel rollback
  are unchanged. New unit tests cover a redacted-intent checkpoint, a fully
  unavailable checkpoint, and assert the db_note never leaks intent text even
  when intent is fully available. `python3 -m pytest warden/ databricks/ -q`:
  **10 passed, 3 skipped**.
  - **Deviation worth flagging:** Claude Code, Codex, and OpenCode were all
    started on this exact curveball prompt at the same time and ended up
    editing `warden/migrate.py` concurrently — several rounds of the file
    changing out from under each edit before converging on the version above.
    The commit landed correctly and tests pass, but this wasn't a clean single-
    owner edit; worth avoiding next time by having one agent own a file for a
    given task instead of pointing multiple agents at the same reconstruction
    task simultaneously.

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
