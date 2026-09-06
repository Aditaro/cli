# Handoff

## One-sentence summary
Handoff mines Entire checkpoint history into a structured onboarding briefing so a fresh agent session can reconstruct full project context in seconds instead of re-reading raw transcripts.

## Problem, intended user and why it matters
Every agent-assisted workflow eventually forces a handoff: a session ends, a teammate picks up the work, or (as this Buildathon's own Noon Curveball requires) you deliberately start fresh and have to reconstruct intent before touching code. Git shows *what* changed; it doesn't show *why*, what was tried and rejected, or what's still unresolved. Developers and agents currently do this reconstruction by hand, re-reading raw transcripts or guessing from diffs. Handoff's user is any developer or agent that needs to resume someone else's (or their own past) work with confidence.

## Selected Entire track and why Entire is essential
**Track 1 — Checkpoint-Native Developer Experience.** Entire Checkpoints are not a logging side-effect here; they are Handoff's only source material. The "landmines" feature — decisions that were reversed or thrashed on more than once — is only extractable from checkpoint reasoning (prompts, rejected options, assumptions), never from a plain git diff. Without Entire, there is no product.

## Architecture and main workflow
1. Pull checkpoint data: `entire checkpoint list` / `entire checkpoint explain <id>`.
2. Synthesize structured JSON (architecture summary, current state, unresolved risks, landmines) via an LLM pass.
3. Enrich with Entire Graph evidence (`entire graph search`, `entire graph impact`) on recently touched symbols — shown as evidence, not asserted as fact.
4. Render `HANDOFF.md` for the next agent session to read first.
5. (Databricks) push the same structured record into a Delta table for durable, queryable decision-health analytics.

Build split: Claude Code drives the core, checkpointed workflow; opencode/Codex execute independent workstreams (Databricks ingestion + dashboard) under Claude Code's direction, coordinated via `TASKS.md` — itself a live demonstration of Track 1's "hand work to another agent without losing the original reasoning."

## Entire Graph findings and verification
_(to fill in during the build — will include one search/lookup, one pre-Curveball impact analysis, and the final semantic diff)_

## Noon Curveball: what changed and how we adapted
_(to fill in at/after 12:00)_

## Checkpoint links and what each checkpoint proves
_(to fill in — must cover: initial understanding/architecture, last stable pre-Curveball state, Curveball response, final implementation/verification)_

## Setup, run and test instructions
_(to fill in once Handoff's CLI exists)_

## Databricks use, data sources and limitations
_(to fill in if/as built — Free Edition, one Delta table `handoff.briefings`, one SQL dashboard)_

## Known limitations and next steps
_(to fill in before submission)_
