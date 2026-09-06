# Warden

## One-sentence summary
Warden is a self-healing database migration guard: it checkpoints a migration's intent before running it, and if the migration fails validation, it auto-rolls-back via Databricks Delta time-travel while explaining the failure using the original intent recorded in the checkpoint — not just "reverted."

## Problem, intended user and why it matters
Database migrations fail in production regularly, and when they do, the standard response is a blind revert with no memory of what the migration was actually trying to achieve. The developer picking up the failure has to reconstruct intent from scratch. Warden's user is any developer or team running schema/data migrations who wants automatic recovery that explains itself, not just a rollback.

## Selected Entire track and why Entire is essential
**Track 1 — Checkpoint-Native Developer Experience.** The healing decision is checkpoint-driven, not just checkpoint-logged: when a migration fails, Warden doesn't merely time-travel the Delta table back — it reads the pre-migration checkpoint's recorded intent to explain *why* the migration was attempted and what should have happened, then surfaces that alongside the rollback. Without the checkpoint, there is a revert with no explanation; with it, there is a recovery with reasoning. Entire Graph runs an impact analysis before the migration lands, so the blast radius is known before the risk is taken, not just after.

## Architecture and main workflow
1. `warden migrate <migration.sql>`:
   a. Write a pre-migration Entire checkpoint: intent (what's changing, why), files/schema touched.
   b. Run `entire graph impact --repo . --symbol <affected>` for a relationship/impact check before the change lands.
   c. Apply the migration to a Databricks Delta table.
   d. Run a validation check (schema/data-quality assertion).
   e. On failure: `RESTORE TABLE ... TO VERSION AS OF <n>` (Delta time-travel) to roll back, then read the pre-migration checkpoint's intent to generate a human-readable explanation of what was attempted and why it failed.
   f. Record the full attempt → failure → heal trail as a new Entire checkpoint.
2. Databricks is the substrate the whole mechanic depends on: Delta Lake's native versioning is the rollback primitive, and a SQL dashboard visualizes migration attempts/heals over time.

Build split: Claude Code drives the core Warden CLI and checkpoint logic; opencode/Codex build the Databricks Delta table setup, synthetic seed data, and dashboard in parallel, coordinated via `TASKS.md`.

## Entire Graph findings and verification
Ran `entire graph impact --repo . --symbol demo_users --head --profile fast` before the demo migration landed (impact analysis before a high-risk change, as required). Real, verified output — not asserted as fact, shown with its own evidence:
```
Index: cache-miss (26413ms) | Query: 16ms | Total: 26429ms
Completeness: no parse failures in SQL (4 files parsed); 1 elsewhere (JSON 1) cannot affect this answer
IMPACT DEGENERATE: warden.demo_users has no callers, callees or type consumers
```
This is the correct, honest answer: `demo_users` is a newly-introduced symbol, so it genuinely has no code dependents yet. Warden shows this evidence to the operator rather than silently skipping the check — `graph_impact()` degrades to an explicit "(graph impact unavailable: ...)" string on timeout/error instead of hiding the failure, per the guide's own warning that graph output is evidence, not fact. Final semantic diff to be captured at submission time from the last commit's `entire graph diff` / `entire graph commit`.

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
- **Checkpoint intent has a hard local/external boundary** (today's curveball work): the full recorded intent is only ever printed to the operator's own console. What reaches Databricks — an external service outside Entire's own trust boundary — is a sanitized summary, the checkpoint ID, and an explicit `context_completeness` label (`complete`/`redacted`/`unavailable`), so a partially-redacted checkpoint can never be mistaken for authoritative context downstream.
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
- **Pre-noon stable state** — this commit. See below for the required intent/architecture/risk summary.

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

# 5. Tests
python3 -m pytest warden/ databricks/ -q
```

## Databricks use, data sources and limitations
Free Edition, one 2X-Small SQL warehouse, one Delta table for the demo migration target, synthetic/clearly-labeled seed data only. Delta time-travel is the rollback mechanism — this is why Databricks is essential, not incidental.

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

None of this is built today — it's the credible next step this architecture is aimed at, not a claim about what's shipped.
