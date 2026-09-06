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
_(to fill in during the build — impact analysis before the demo migration, plus the final semantic diff)_

## Noon Curveball: what changed and how we adapted
_(to fill in at/after 12:00)_

## Checkpoint links and what each checkpoint proves
_(to fill in — includes the pivot checkpoint recording the move from the original "Handoff" concept to Warden, and why)_

## Setup, run and test instructions
_(to fill in once Warden's CLI exists)_

## Databricks use, data sources and limitations
Free Edition, one 2X-Small SQL warehouse, one Delta table for the demo migration target, synthetic/clearly-labeled seed data only. Delta time-travel is the rollback mechanism — this is why Databricks is essential, not incidental.

## Known limitations and next steps
_(to fill in before submission)_
