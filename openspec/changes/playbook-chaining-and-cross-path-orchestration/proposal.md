## Why

Two gaps remain once `soar-automation-path-consolidation-decision`, `playbook-engine-correctness-hardening`, `core-playbook-pack-v1`, and `conditional-branching-primitive` are all in place. First, no playbook can trigger another — every prior capability extended what a single execution can do, never let one execution hand off to a second. Second, the consolidation decision named the playbook engine authoritative and froze the response-action queue, but only as a documented convention — both paths still fire unconditionally for every alert today, and nothing in code enforces "exactly one path acts." This spec, sequenced last on purpose, closes both gaps by reusing infrastructure the audit found already exists for other purposes: the canonical outcome ledger's parent/child correlation column, the existing `(playbook_id, alert_id)` dedup index, the existing alert-id-based incident-timeline fallback, and the exact call sites where both orchestration paths are already invoked.

## What Changes

- Define an explicit, single-hop `trigger_playbook` step that dispatches a second playbook execution asynchronously (fire-and-forget onto the existing worker batch loop), with parent/child linkage via one new `playbook_executions` column (`parent_execution_id`) plus reuse of the existing `soar_response_decisions.parent_soar_correlation_id`.
- Define two independent, fail-closed loop-prevention guards: a definition-time self-reference rejection, and a dispatch-time depth cap plus bounded ancestor-cycle walk — deliberately not a full cross-definition graph-reachability validator.
- Define a precedence guard that reorders the two existing ingest-time orchestration calls and threads the playbook-matched alert-id set into the queue path, so the already-decided authoritative path is enforced in code rather than documented as a convention.
- Build a concrete coverage map (queue's three reputation-based response actions against `core-playbook-pack-v1`'s five already-designed playbooks), confirm the consolidation decision's parity criterion is already satisfied, and define a staged, criteria-gated retirement sequence for the queue's ingest-time trigger — without authorizing that removal in this spec.
- No implementation, no schema changes, and no code changes in this proposal step.

## Capabilities

### New Capabilities
- `playbook-chaining-and-cross-path-orchestration`: records the requirements for explicit playbook-to-playbook chaining and for enforcing the playbook engine's authoritative status over the frozen response-action queue path. No existing spec under `openspec/specs/` covers either domain.

### Modified Capabilities
(none — this proposal does not change the behavior of any shipped capability; chaining is additive, and the precedence guard only changes behavior for alerts that would otherwise have been double-handled, which the consolidation decision already said should never happen)

## Impact

- **Affected code (future implementation phase, not this proposal step):** `engines/playbook_registry.py`, `engines/playbook_step_executor.py`, `engines/soar_playbook_orchestrator.py` (no signature change, new caller only), `engines/soar_enqueue_orchestrator.py`, `engines/soar_action_worker.py` (freeze notice only), `routes/ingest_routes.py` (call-order change), a new migration adding two `playbook_executions` columns.
- **Affected artifacts (this step):** adds `openspec/changes/playbook-chaining-and-cross-path-orchestration/` as a new, unimplemented child change under the `soar-playbook-modernization-roadmap` parent — its final tracked child.
- **Downstream effect:** completes the roadmap's designed path from "two ambiguous automation paths with no real playbook content" to "a single authoritative, chainable, auditable orchestration layer with a criteria-gated queue retirement sequence." Full queue retirement remains gated on this spec's coverage-gap resolution and is not itself authorized here.
- **Dependencies:** `SOAR Automation Path Consolidation Decision` (the decision this spec enforces), `Playbook Engine Correctness Hardening` (parity criterion already confirmed satisfied), `Core Playbook Pack v1` (source of the coverage map's playbook side), `Conditional Branching Primitive` (hardened, extended executor base this spec's `trigger_playbook` step builds on the same way `branch` did).
