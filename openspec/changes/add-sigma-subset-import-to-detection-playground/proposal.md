## Why

The Detection Playground already has the right safety boundary for analyst-authored simulations: pasted events flow through reused parser and preview paths inside a rollback-only transaction, and nothing persists or executes. What it lacks is a text-based rule format that helps analysts practice realistic detection-engineering work, especially Sigma structure, YAML, field mapping, and ATT&CK tagging, without creating a second detection engine or implying production-rule parity.

## What Changes

- Add a Sigma YAML import mode to the existing Detection Playground so analysts can paste a bounded Sigma rule and simulate it safely against pasted events.
- Define a strict Version 3 Sigma subset with explicit support, rejection, and validation behavior for metadata, logsource mapping, field mapping, detection selections, simple boolean conditions, and a small modifier allowlist.
- Expand the current temporary-rule contract only as much as needed to represent Sigma selections and simple `and` / `or` / `not` logic, while keeping the existing rollback-safe evaluator as the only execution path.
- Add backend-safe YAML parsing, canonical source resolution, field alias mapping, unsupported-construct errors, and a normalized internal-rule preview for analyst review before simulation.
- Extend the existing Detection Simulator UI with a Sigma editor/import surface, validation feedback, normalized-rule preview, and existing pipeline/explainability reuse.
- Preserve all current non-goals: no custom DSL, no arbitrary Python or SQL, no Sigma correlation or aggregation language, no persistence, no rule promotion, no import/export, and no production mutation path.

## Capabilities

### New Capabilities
- `detection-playground-sigma-subset-import`: safe Sigma YAML subset parsing, validation, mapping, compilation into the existing playground evaluator, and analyst-facing simulation feedback inside the Detection Playground.

### Modified Capabilities
- None.

## Impact

- Backend planning impact: `routes/detection_simulator_routes.py`, `engines/detection_simulator.py`, a new Sigma validation/compilation helper layer, canonical source and field-mapping tables, and simulator safety/regression tests.
- Frontend planning impact: `frontend/src/components/DetectionSimulatorPanel.js`, a new Sigma editor/import component, validation and normalized-preview rendering, shared pipeline/explainability reuse, and focused accessibility/responsive checks.
- Dependency impact: safe YAML parsing support on the backend if no acceptable built-in parser already exists.
- Safety impact: no second evaluator, no durable writes, no worker-visible rows, no production-rule modification, no external integrations, explicit fail-closed validation for unsupported Sigma features, and preserved request/resource limits.
- Operational impact: no migration expected, no VM sync required for this spec-only change, and no deployment activity included in this change.
