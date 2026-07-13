## Why

The existing Detection Simulator safely previews how pasted events flow through the production parser, normalization, detection, MITRE, and SOAR-preview pipeline for existing production rules, but it does not let analysts test a candidate rule without editing real detector code or production rule configuration. Analysts need a guided playground for temporary rule experimentation that stays inside the simulator's rollback-only boundary, never persists configuration, and never implies that a playground rule is already a production detector.

This change is needed now because the rollback-safe Version 1 simulator already provides the correct containment boundary and preview contracts. Version 2 should extend that boundary with a deliberately small declarative temporary-rule path instead of introducing a general-purpose rule language, a second pipeline, or any production mutation path.

## What Changes

- Add a new Detection Simulator mode, `Temporary Playground Rule`, alongside the existing `Existing Production Rule` mode, while preserving Version 1 behavior for production-rule simulation.
- Define an authoritative, narrow temporary-rule contract for one condition plus one bounded threshold/window aggregation, with exact allowed fields, operators, severities, limits, and validation errors.
- Add a small backend temporary-rule evaluator that runs only inside the existing rollback-only simulation transaction, reuses existing parser/normalizer, normalized-event schema, MITRE enrichment, alert-preview shape, playbook matching, and SOAR preview, and never writes durable rows or executes integrations.
- Make temporary-rule evaluation request-scoped only: no rule table, no draft table, no simulation history table, no migration, no promotion-to-production path, and no server-side persistence.
- Extend the existing Detection Simulator workspace with a mode switch, guided builder controls, plain-language summary, explainability evidence, and explicit rollback/non-persistence disclosure.
- Require focused backend/frontend tests, build validation, browser verification, OpenSpec strict validation, and a later VM deployment handoff phase without performing that deployment in this change.

## Capabilities

### New Capabilities
- `detection-rule-playground`: guided creation and rollback-safe evaluation of a temporary declarative detection rule against pasted or sample events, including validation, explainability, alert preview, MITRE preview, and SOAR preview.

### Modified Capabilities
- None. Version 1 production-rule simulation remains intact; Version 2 adds a separate additive playground capability rather than changing production ingest or existing detector semantics.

## Impact

- Backend planning impact: `routes/detection_simulator_routes.py`, `engines/detection_simulator.py`, parser/normalizer reuse paths, playbook-preview reuse paths, and simulator transaction-safety tests.
- Frontend planning impact: the existing Detection Simulator workspace, builder controls, response rendering, accessibility, and responsive layout verification.
- Security/safety impact: strict validator-owned rule contract, resource limits, no custom code execution, no arbitrary SQL, no audit-log writes, no worker-visible rows, and no external integrations.
- Operational impact: no migration expected, no production-config mutation path, and no VM sync required for this spec-only change.
