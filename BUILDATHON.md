# Warden

## One-sentence summary
Warden is a self-healing database migration guard: it checkpoints a migration's intent before running it, and if the migration fails validation, it auto-rolls-back via Databricks Delta time-travel while explaining the failure using the original intent recorded in the checkpoint — not just "reverted."

## Problem, intended user and why it matters
Database migrations fail in production regularly, and when they do, the standard response is a blind revert with no memory of what the migration was actually trying to achieve. The developer picking up the failure has to reconstruct intent from scratch. Warden's user is any developer or team running schema/data migrations who wants automatic recovery that explains itself, not just a rollback.

## Selected Entire track and why Entire is essential
**Track 1 — Checkpoint-Native Developer Experience.** The healing decision is checkpoint-driven, not just checkpoint-logged: when a migration fails, Warden doesn't merely time-travel the Delta table back — it reads the pre-migration checkpoint's recorded intent to explain *why* the migration was attempted and what should have happened, then surfaces that alongside the rollback. Without the checkpoint, there is a revert with no explanation; with it, there is a recovery with reasoning. Entire Graph runs an impact analysis before the migration lands, so the blast radius is known before the risk is taken, not just after.

## Architecture and main workflow
1. `warden migrate <migration.sql> --validate-sql <check.sql>`:
   a. Read the most recent Entire checkpoint's recorded intent (what's changing, why) via `entire checkpoint explain`.
   b. Run `entire graph impact --repo . --symbol <affected>` for a relationship/impact check before the change lands.
   c. Apply the migration to a Databricks Delta table.
   d. Run the supplied validation query as a second, independent check.
   e. On failure at either step: `RESTORE TABLE ... TO VERSION AS OF <n>` (Delta time-travel) to roll back, then use the checkpoint's recorded intent to generate a human-readable explanation of what was attempted and why it failed.
   f. Log the attempt (applied/healed/failed) to `warden.migration_log`, with the raw checkpoint intent and full error text kept local-only (see Security).
2. Databricks is the substrate the whole mechanic depends on: Delta Lake's native versioning is the rollback primitive, and a Lakeview dashboard visualizes migration attempts/heals over time.

**Verified live which check actually fires (not assumed):** the demo migration adds a Delta `CHECK` constraint (`ALTER TABLE ... ADD CONSTRAINT ... CHECK (plan IN (...))`), and Delta validates *existing* data at `ADD CONSTRAINT` time. Against the live warehouse, that ALTER TABLE step itself throws on the seeded offending row (`plan='legacy'`) — the separate `001_validate.sql` SELECT step (d above) is never reached in practice for this particular migration, because Delta's own constraint mechanism is stricter and catches the problem first. Warden's healing logic (step e) is correctly written to catch a failure from *either* source — the ALTER TABLE or the validation SELECT — since not every migration will use a Delta `CHECK` constraint the way this demo does; this one just happens to fail at the earlier point. This was confirmed by a real run, not inferred: see the Checkpoint links section.

Build split: Claude Code drives the core Warden CLI and checkpoint logic; opencode/Codex build the Databricks Delta table setup, synthetic seed data, and dashboard in parallel, coordinated via `TASKS.md`.

## Entire Graph findings and verification
Ran `entire graph impact --repo . --symbol demo_users --head --profile fast` before the demo migration landed (impact analysis before a high-risk change, as required). Real, verified output — not asserted as fact, shown with its own evidence:
```
Index: cache-miss (26413ms) | Query: 16ms | Total: 26429ms
Completeness: no parse failures in SQL (4 files parsed); 1 elsewhere (JSON 1) cannot affect this answer
IMPACT DEGENERATE: warden.demo_users has no callers, callees or type consumers
```
This is the correct, honest answer: `demo_users` is a newly-introduced symbol, so it genuinely has no code dependents yet. Warden shows this evidence to the operator rather than silently skipping the check — `graph_impact()` degrades to an explicit "(graph impact unavailable: ...)" string on timeout/error instead of hiding the failure, per the guide's own warning that graph output is evidence, not fact.

**Impact analysis on the two functions the Curveball actually changed.** The Curveball instructions asked for this *before* editing, and both were run before the privacy fix landed; `log_attempt`'s query initially exceeded the 30s window on a cold index and was recorded as unavailable rather than guessed at. Re-run on a warm index, it completes (`entire graph impact --repo . --symbol log_attempt --head --profile fast`, 62s total, 106ms query):
```
Impact: log_attempt (warden/migrate.py:180) def=180 span=180-194 [function]
Blast radius: 2 callers (1 direct, 1 transitive), 1 callee, 0 type consumers.
Callers (who breaks if behavior changes):
- apply_migration (warden/migrate.py:246)
- main (warden/migrate.py:337) [via apply_migration]
Callees (what it depends on):
- ensure_log_table (warden/migrate.py:149)
```
**Verified against source and tests, not quoted blind:** the two callers are exactly the applied/healed/failed call sites in `apply_migration`, each covered by `warden/test_migrate.py`; the single callee `ensure_log_table` is the function whose swallow-everything `except` an automated review pass caught and which is now pinned by `test_ensure_log_table_propagates_non_duplicate_alter_errors`. The Graph's claimed blast radius and the test suite's coverage agree — which is the point of checking, since `log_attempt` is the function that writes to the external service the Curveball was about.

**Final semantic diff** (`entire graph diff --base b8c9fe619 --head HEAD`, i.e. pre-Curveball stable state → final). Real output, abridged to `warden/migrate.py` — the file the Curveball actually changed:
```
warden/migrate.py (Python)
  + class LocalOnlyText added
  + method LocalOnlyText.reveal added
  + method LocalOnlyText.__str__ added
  + function classify_completeness added
  ~ function get_latest_checkpoint body changed (6 dependents)
  ~ function ensure_log_table body changed (3 dependents)
  ~ function log_attempt signature changed (2 dependents)
  + function error_summary added
  + function describe_failure added
  ~ function apply_migration body changed (4 dependents)
```
This is the Curveball response expressed structurally, and it is verified against source and tests rather than quoted blind: `log_attempt`'s **signature change** is the privacy boundary itself (it gained the `context_completeness` parameter, and its 2 dependents are the applied/healed call sites in `apply_migration`); `LocalOnlyText` and `error_summary` are the two new guards; `get_latest_checkpoint`'s 6 dependents are `apply_migration` plus the five checkpoint tests that pin its degraded/redacted/unavailable behavior. Each edge named here is covered by a test in `warden/test_migrate.py`.

**Curveball-targeted Graph follow-up:** `entire graph impact --repo . --symbol get_latest_checkpoint --head --profile fast` was rerun against the hardened tree and found two callers (`apply_migration` directly and `main` transitively) plus the expected dependencies (`run_entire`, `LocalOnlyText`, and `classify_completeness`). Source and unit tests verify those edges: `apply_migration` consumes the returned completeness-wrapped intent, while the checkpoint tests cover committed-checkpoint selection, unavailable Entire output, malformed JSON, and redacted intent. The corresponding `log_attempt` impact query exceeded the local 30-second Graph window in this session; source inspection and the migration tests verify its callers (`apply_migration` through applied/healed/failed paths) and its external-boundary behavior, but that unavailable Graph result is not presented as a successful finding.

## Noon Curveball: what changed and how we adapted
The curveball invalidated the assumption that sending the full checkpoint
explanation in `warden.migration_log.note` was useful. A checkpoint can contain
sensitive prompts or transcripts, and Databricks is outside Entire's local
privacy boundary.

Warden now keeps complete intent local for operator-facing explanations only.
Databricks receives a sanitized failure summary, the checkpoint ID, and a
`context_completeness` value of `complete`, `redacted`, or `unavailable`.
Redacted or missing context is labelled as incomplete and never presented as
authoritative. Existing migration/healing behavior remains intact, including
the Delta time-travel rollback. Unit tests cover complete, redacted, and
unavailable checkpoint data and assert that raw intent is absent from the
external log note.

## Security: what's already true, and how this gets more secure from here

**Already true today, not aspirational:**
- **No secrets ever touch the repo or an external service.** `DATABRICKS_SERVER_HOSTNAME`/`HTTP_PATH`/`TOKEN` are read from env vars only (`warden/migrate.py::connect()`), sourced from a gitignored `.env`; the connector fails closed with a clear error if any are missing, and nothing in the codebase reads or prints `.env` itself.
- **Checkpoint intent has a hard, structurally-enforced local/external boundary** (curveball work, hardened same-session): recorded intent is wrapped in `LocalOnlyText`, whose default `str()`/`repr()` return a redaction placeholder rather than the real text — the real text is reachable only through one explicit `.reveal()` call, at the two genuinely local-only console-print sites. A future call site that carelessly interpolates the wrapper into a string bound for Databricks gets the placeholder, not a leak — this is a property of the type, not just a convention checked by review. What actually reaches Databricks is a sanitized summary, the checkpoint ID, and an explicit `context_completeness` label (`complete`/`redacted`/`unavailable`), so a partially-redacted checkpoint can never be mistaken for authoritative context downstream.
- **The same boundary covers database error text, not just checkpoint intent.** Reviewing the curveball fix surfaced a second leak of the identical shape: some of Delta's own constraint-violation errors embed the offending row's actual column values (`DELTA_VIOLATE_CONSTRAINT_WITH_VALUES`, raised on an `INSERT`/`UPDATE` against an existing constraint), so forwarding raw exception text to `migration_log` would leak table data through a different door than the one the curveball closed. `error_summary()` reduces any exception to its type name (e.g. `ServerOperationError`) before it crosses the external-service boundary; the full message still prints locally for operator triage. **Confirmed live:** the demo's own failure actually raises `DELTA_NEW_CHECK_CONSTRAINT_VIOLATION` (Delta's `ADD CONSTRAINT` validating existing data — see Architecture), which reports only a row *count*, not values — so this specific run wasn't exposed to the values-embedding variant. `error_summary()` is a blanket guard for any future migration that does hit a value-embedding error, not a reaction to this one; the logged row for this run confirms no raw intent and no error detail beyond the type name.
- **Warden inherits Entire's own checkpoint-security substrate**, rather than re-implementing it: transcripts are redacted before they're ever written to a checkpoint (regex + entropy scanners, with an optional OpenAI Privacy Filter layer), the `.entire` directory refuses to operate through a symlink (so a malicious repo can't redirect where checkpoint data is read from or written to), and exec-bearing settings (like a custom redaction command) are only ever honored from an untracked, developer-local file — never from anything a pull request could commit. Warden's checkpoint reads (`entire checkpoint list/explain`) sit on top of all of this for free.

**Where this goes next if we had more time (credible, not built):**
- `DATABRICKS_TOKEN` here is a long-lived personal token for demo purposes; a real deployment should use a Databricks service principal with a short-lived OAuth token instead.
- `checkpoint_id` in `migration_log` is an unsigned string today — anyone with warehouse write access could forge one. An HMAC over `(checkpoint_id, migration_name)`, signed with a key that never leaves the machine running Warden, would let a reader verify a log row's checkpoint claim without trusting the warehouse.
- `migrate.py` currently has no access gate of its own — any user holding the three env vars can apply a migration. A real deployment should require the migration to reference a checkpoint that's already been reviewed/merged (not just the latest one), turning "checkpoint-driven" into "checkpoint-authorized."
- The `note` column in `warden.migration_log` is plaintext; column-level encryption or Unity Catalog row/column ACLs would let the security team restrict who can read even the sanitized failure summaries, not just who can write them.

## Checkpoint links and what each checkpoint proves
- **Initial understanding** (`28dcc3fee`) — original architecture (Handoff), before the pivot.
- **Pivot** (`666631970`) — rejected Handoff, chose Warden, with the rubric-based reasoning recorded.
- **Core implementation** (`68001846c`, `ed612f27c`) — checkpoint-driven migration guard + unit tests.
- **Multi-agent build** (`11525915f`, `8e089315f`) — opencode's Databricks infra, Codex's migration scenario, each with their own `Entire-Checkpoint` trailer.
- **Real bugs found and fixed against the live warehouse** (`874f4a0e7`) — proves the loop was actually run, not just written: `uuid()` inline-table bug, graph impact profile/timeout fix.
- **Demo runner** (`50ffe776c`) — one-command live demo flow.
- **Pre-noon stable state** (`b8c9fe619`) — required intent/architecture/risk summary before the curveball.
- **Privacy boundary + hardening** (`cc16573cc`, `1784305b7`) — the curveball fix (`context_completeness`, local-only intent) plus a same-session follow-up that closed a second leak of the same shape (raw DB exception text reduced to its type name before crossing the external boundary) and made the intent boundary structural (`LocalOnlyText`) rather than convention-only.
- **Post-curveball live verification + Lakeview dashboard** (`7274590b7`) — Codex confirmed live which failure path actually fires (Delta's `ADD CONSTRAINT` validation, not the manual SELECT — see Architecture) and shipped a real dashboard object via the Lakeview API.
- **Code-review fixes from live evidence** (`4774afcbe`) — two real bugs found by an automated review pass and fixed (an `ALTER TABLE` backfill that silently swallowed genuine failures and could misclassify a healthy migration as failed; an `UnboundLocalError` when the Delta version lookup itself failed), plus a tightened redaction-marker regex. Also corrected a speculative error-name citation once the live run showed the actual error was `DELTA_NEW_CHECK_CONSTRAINT_VIOLATION`.
- **Safe resume report** (`f8f9599e5`) — read-only checkpoint readiness CLI that reuses the existing privacy boundary rather than inventing a second one.

**The four required milestones map to:** initial understanding (`28dcc3fee`) → pivot and core implementation (`666631970`, `68001846c`) → pre-Curveball stable state (`b8c9fe619`) → Curveball response and verification (`cc16573cc`, `1784305b7`, `4774afcbe`).

### The fresh-session criterion was met by the actual working history, not a staged test

The rubric asks whether a fresh session can resume from these checkpoints. That was not simulated here — it is how the Curveball response was actually produced, and the history shows it:

1. `0d29a022c` ("Curveball received … Stopping implementation here") deliberately ended the pre-Curveball session at a stable point.
2. A **new agent session** was started with no conversational memory of the prior work. Its first action was `entire checkpoint explain 0d29a022c`, and it was instructed to rely on nothing else.
3. From that checkpoint alone it reconstructed the architecture, located the offending assumption (`get_latest_checkpoint()` sending raw intent into `warden.migration_log`), ran `entire graph impact` on `get_latest_checkpoint` and `log_attempt` *before* editing, and implemented the full privacy boundary — `context_completeness`, `LocalOnlyText`, `error_summary` — with tests.

So the resumed work was not a summary or a status read: a cold session reconstructed intent from a checkpoint and then made the single most significant change in the project. Every commit from `cc16573cc` onward is that session's output. A second, narrower check was also run in a scrubbed environment (`env -i`), where `entire checkpoint explain 01M1TWD4BP5ZTG9SJWHM7BJNZP` alone was enough to recover the batch's scope, touched files, and next action.

`python3 warden/resume_report.py <checkpoint_id>` is the productized form of that same capability, with the privacy boundary applied: it tells a fresh operator or agent whether context is complete enough to proceed, without ever exposing the checkpoint text itself.

## Setup, run and test instructions
```
# 1. Entire (already set up in this fork)
entire login
entire enable -y --agent claude-code   # or codex / opencode
entire plugin install graph && entire graph init-agents --repo .

# 2. Databricks credentials (gitignored .env, never commit)
echo 'DATABRICKS_SERVER_HOSTNAME=...' >> .env
echo 'DATABRICKS_HTTP_PATH=...' >> .env
echo 'DATABRICKS_TOKEN=...' >> .env
set -a; source .env; set +a

# 3. Provision the demo table + synthetic seed data
python3 -c "from databricks import sql; import os; c=sql.connect(server_hostname=os.environ['DATABRICKS_SERVER_HOSTNAME'],http_path=os.environ['DATABRICKS_HTTP_PATH'],access_token=os.environ['DATABRICKS_TOKEN']); cur=c.cursor(); cur.execute('CREATE SCHEMA IF NOT EXISTS warden'); [cur.execute(s) for s in open('databricks/setup.sql').read().split(';') if s.strip()]"
python3 databricks/seed.py

# 4. Run the live demo (fail -> heal, real Delta time-travel)
bash warden/demo.sh

# No credentials required: verify the migration, validation, and seed fixtures
bash warden/demo.sh --self-test

# 5. Tests
python3 -m pytest warden/ databricks/ -q
```

## Databricks use, data sources and limitations
Free Edition, one 2X-Small SQL warehouse, one Delta table for the demo migration target, synthetic/clearly-labeled seed data only. The seed generator creates exactly 50 deterministic-looking synthetic users on the reserved `example.invalid` domain; user 7 deliberately has `plan='legacy'` so the business-rule failure is reproducible, and no production or personal data is used. Delta time-travel (`RESTORE TABLE ... TO VERSION AS OF`) is the rollback mechanism, and Delta's own `CHECK` constraint enforcement is what actually catches the demo's seeded bad row — both are load-bearing, not decorative. Migration attempts/heals are visualized in a real Lakeview dashboard object in the workspace (created via `databricks/create_dashboard.py` against the Lakeview REST API, not just a stub query file): [Warden Migration Health](https://dbc-89334694-0d5f.cloud.databricks.com/dashboardsv3/01f1a9c471e5137fba57a227f9b91452).

## Known limitations and next steps

**What's demonstrated today:** one Delta table, one migration, one validation check, one heal path. This is a narrow vertical slice chosen deliberately to prove the mechanism end-to-end within a one-day build, not a general migration framework.

**Known limitations, disclosed rather than hidden:**
- `RESTORE TABLE` is a metadata-only operation (it repoints the transaction log, it doesn't rewrite data), which is exactly why this approach scales to large tables in principle — but it fails outright if VACUUM has already purged the target version's files, so a production deployment needs a retention policy that guarantees the rollback window survives.
- The validation step here is a full-table scan. At real scale that needs to become partition-scoped or incremental (validate only what the migration actually touched), not a full scan.
- Everything today is single-migration, single-table, sequential.

**Where this goes next:** the actual ambition behind Warden is a zero-downtime, parallel migration system for large, custom, and messy data setups — the kind of migration a company with a complex bespoke schema (e.g. a high-traffic consumer platform, not a clean textbook schema) can't afford to take offline for. Concretely:
- Parallelize validation and healing across partitions/shards instead of one sequential table-level check, so a migration on a huge dataset doesn't serialize on a single validation pass.
- A caching/staging layer so reads and writes continue against a consistent view while a migration is in flight underneath, rather than requiring a maintenance window.
- Generalize beyond one language/stack — the checkpoint-driven intent lookup is language-agnostic by construction (it reads Entire checkpoints and Delta metadata, not application code), so the same core mechanism could sit in front of a migration pipeline written in any language.
- Multi-migration orchestration with dependency ordering, not just one migration at a time.

`python3 warden/resume_report.py <checkpoint_id>` is a narrow proof of the safe-resume-report idea: it gives a fresh operator or agent a checkpoint completeness label, migration target, safe latest-log status, and next action without exposing raw checkpoint text. A future control plane could extend that same boundary with versioned caches, Delta Change Data Feed catch-up, parallel backfills, and an optional read-only MCP surface.

**One piece of that direction is already built, as a narrow proof rather than a claim:** `python3 warden/resume_report.py <checkpoint_id>` gives a fresh operator or agent a checkpoint completeness label, migration target, safe latest-log status, and a recommended next action — without ever exposing raw checkpoint text (it never calls `LocalOnlyText.reveal()`, and a test plants a secret to prove output cannot leak it). It is a single read-only CLI, not a control plane.

The rest of the direction above — versioned cache reads, Delta CDF/outbox write catch-up, compatibility-view cutover, partition-aware validation, an optional read-only MCP surface — is **not built**, and is described here as the credible next step this architecture is aimed at, not as shipped functionality.

**A bounded multi-table scheduler and a privacy-safe health report were also prototyped** (`warden/orchestrate.py`, `warden/health_report.py`, on branch `handoff` past this commit). They pass unit tests but were deliberately left out of this submission commit: their accompanying seed change did not fully re-verify against the live warehouse before the deadline, and shipping an unverified change to the demo's data path was judged a worse trade than shipping the smaller, fully-verified slice. That decision is itself recorded in the checkpoint history.
