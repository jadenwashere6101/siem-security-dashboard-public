## Why

The SOAR subsystem has accumulated a mature execution engine (leases, approval gates, dead letters, canonical response outcomes) but the project has never stepped back to ask whether the *playbook layer itself* — the thing a SOC analyst or interviewer would actually look at — reflects realistic SOC automation. A direct code audit found that zero concrete, named playbook definitions exist anywhere in the repository (no seeds, fixtures, or demo data insert rows into `playbook_definitions`); the "library" is currently an empty, if well-built, framework. Separately, alert-triggered automation is split across two independently evolved paths — the playbook engine and the older `response_actions_queue`/`soar_action_worker` path — that fire in parallel on the same ingest event with materially different safety semantics (e.g., protected-target checks apply on one path and not the other). Before investing further engineering effort, the project needs a single documented assessment of what exists, what it's worth, what's missing, and what order to build it in.

## What Changes

- Perform a read-only architectural audit of the SOAR playbook subsystem: engine, registry, step executor, orchestrator, worker, store, response action queue, response outcome architecture, enrichment (AbuseIPDB) and MITRE usage.
- Produce a single audit deliverable (this change's `design.md`) containing: executive summary, current playbook inventory, quality assessment, per-unit KEEP/IMPROVE/MERGE/REPLACE/RETIRE recommendations, a catalog of missing high-value playbooks with full SOC justification per entry, a gap analysis of missing SOAR capabilities, architectural recommendations, a prioritized (value × effort) roadmap, risks, and a future implementation strategy.
- No application code, schema, playbook records, or tests are modified by this change. It is a planning artifact only, intended to seed future scoped OpenSpec changes.

## Capabilities

### New Capabilities
- `soar-playbook-library-audit`: establishes the audit deliverable itself as a tracked capability — what the audit document must contain, and the guardrail that this change makes no functional modification to the codebase.

### Modified Capabilities
(none — this change does not alter behavior of any existing capability)

## Impact

- **Affected code:** none (read-only audit; no files under `engines/`, `core/`, `routes/`, `migrations/`, or `frontend/` are touched).
- **Affected artifacts:** adds `openspec/changes/audit-soar-playbook-library/` (proposal, design, tasks, spec) as a new, unimplemented change.
- **Downstream effect:** the roadmap in `design.md` is expected to seed one or more future OpenSpec changes (e.g., a first concrete playbook pack, a dual-path SOAR consolidation change, an enrichment-in-playbook change). None of that follow-on work is authorized or started by this change.
- **Dependencies:** none. Read access to the existing SOAR codebase only.
