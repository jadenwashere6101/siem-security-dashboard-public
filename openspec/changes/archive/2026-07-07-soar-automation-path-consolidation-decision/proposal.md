## Why

The SOAR playbook audit (`audit-soar-playbook-library`) found that alert-triggered automation is split across two independently-evolved paths — the response-action queue (`soar_enqueue_orchestrator` → `response_actions_queue` → `soar_action_worker`) and the playbook engine (`soar_playbook_orchestrator` → `playbook_executions` → `playbook_step_executor`) — both wired directly into `routes/ingest_routes.py` and both capable of acting on the same alert. They already implement overlapping actions (`block_ip`) with materially different safety guarantees: the queue path enforces `soar_protected_targets.require_unprotected_target` and a fixed approval-required-action set; the playbook path's `block_ip` step enforces neither. Every downstream modernization item — correctness hardening, new playbook content, branching, chaining — depends on knowing which path is authoritative going forward. This decision must be made before any of that work starts, or the ambiguity compounds.

## What Changes

- Document the current architecture of both paths and the concrete risk of leaving them ambiguous.
- Record a single, exact decision on their target relationship (merge / permanently separate / retire one / designate one authoritative over the other), with alternatives considered and the criteria used to choose.
- Define the implementation boundaries a later child spec must respect when enforcing this decision (what is and isn't in scope for that future work).
- Define acceptance criteria and a validation plan for confirming the decision has been correctly enforced once implemented.
- No code, schema, or playbook content changes are made by this spec. It is a decision-and-boundary document only; enforcement is deferred to a later, separately-scoped child spec.

## Capabilities

### New Capabilities
- `soar-automation-path-consolidation-decision`: records the architecture decision on the relationship between the response-action queue and the playbook engine, and the boundary a future enforcement spec must operate within.

### Modified Capabilities
(none — this change does not alter behavior of any existing capability)

## Impact

- **Affected code:** none (decision document only; no files under `engines/`, `core/`, `routes/`, `migrations/`, or `frontend/` are touched).
- **Affected artifacts:** adds `openspec/changes/soar-automation-path-consolidation-decision/` as a new, unimplemented child change under the `soar-playbook-modernization-roadmap` parent.
- **Downstream effect:** this decision gates `Playbook Engine Correctness Hardening` (protected-target guard placement), `Core Playbook Pack v1` (which path new playbooks must target), and `Playbook Chaining & Cross-Path Orchestration Layer` (enforcing the decision in code). None of that work is authorized or started by this change.
- **Dependencies:** the `audit-soar-playbook-library` audit (source of the dual-path finding) and the `soar-playbook-modernization-roadmap` parent (this is its first tracked child).
