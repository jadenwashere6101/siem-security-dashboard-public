## Why

The playbook audit (`audit-soar-playbook-library`) found zero concrete, named playbooks in the system — a fully-built engine with no content. `Playbook Engine Correctness Hardening` has since closed the `block_ip` protected-target gap, unified the action vocabulary, and made stale-execution give-up reachable. `Dynamic Playbook Parameter Binding` (roadmap item 2.4, not yet implemented) will close the remaining engine gap: per-execution resolution of step `params` against the triggering alert so containment and alert-specific notifications work correctly.

This spec defines the five playbooks that SHOULD constitute Version 1 once that binding capability exists. It does not compromise around static parameters — playbooks include `block_ip` and alert-bound notification params where containment or alert context is required. Content authorship is BLOCKED until `dynamic-playbook-parameter-binding` is implemented.

## What Changes

- Inventory every existing alert type, the current playbook action vocabulary, existing enrichment, and approval-gate mechanics (completed during spec authoring).
- Design five Version 1 playbooks — Brute Force Containment, Password Spray Investigation, Successful Login After Spray Response, Malicious IP Containment, Reputation-Only Investigation — with triggers, steps, and dynamic parameter bindings as they should exist post-binding.
- Explicitly defer playbook ideas that need capabilities other than parameter binding (branching, chaining, ad hoc triggers, missing telemetry).
- No engine changes, no schema changes, no new actions, no UI changes in this spec-writing step. Implementation (later, separately-requested) is pure data authorship through the existing `POST /playbooks` API — but only after `dynamic-playbook-parameter-binding` lands.

## Capabilities

### New Capabilities
- `core-playbook-pack-v1`: records which five playbooks constitute Version 1, their exact trigger/step/approval shape including dynamic parameter bindings, and which candidate playbooks are deferred and why. No existing spec under `openspec/specs/` covers playbook content.

### Modified Capabilities
(none)

## Impact

- **Affected code (future implementation phase, not this proposal step):** none required — Version 1 playbooks are authored as `playbook_definitions` rows via the existing `POST /playbooks` route once binding is implemented. An optional seed script may be used purely for convenience.
- **Affected artifacts (this step):** updates `openspec/changes/core-playbook-pack-v1/` as a child change under the `soar-playbook-modernization-roadmap` parent.
- **Downstream effect:** gives the SOAR system its first real content design; implementation is gated on `dynamic-playbook-parameter-binding`.
- **Dependencies:** `SOAR Automation Path Consolidation Decision` (target the decided execution path), `Playbook Engine Correctness Hardening` (hardened primitives), and `Dynamic Playbook Parameter Binding` (per-execution param resolution — BLOCKING for implementation).
