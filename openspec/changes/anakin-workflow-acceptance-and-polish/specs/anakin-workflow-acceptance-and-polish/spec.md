# Spec: Anakin Workflow Acceptance And Polish

## ADDED Requirements

### Requirement: Canonical Workflow Acceptance Inventory

The acceptance harness MUST treat the six canonical workflows as the primary coverage unit and MUST prove every remaining frontend AI control maps to exactly one workflow.

#### Scenario: Remaining controls are mapped

- **GIVEN** the offline acceptance harness builds its inventory
- **WHEN** remaining frontend AI controls are evaluated
- **THEN** each control maps to exactly one of Quick Explain, Deep Investigate, Decision Support, Generate Artifact, SOC Briefing, or Repo Assistant
- **AND** obsolete frontend action IDs or removed labels fail the gate if they reappear.

### Requirement: Workflow Safety Gate

The final gate MUST verify workflow routing, envelopes, profile/model selection, context bounds, failure handling, and safety boundaries.

#### Scenario: Restricted paths are blocked

- **GIVEN** auto-routing or Decision Support requests
- **WHEN** restricted or mutating paths are requested
- **THEN** SOC Briefing, Repo Assistant, artifact confirmation, and mutation paths are not silently invoked
- **AND** low-confidence auto-routing returns a chooser state.

### Requirement: Structured Artifacts Remain Review-Only

Generate Artifact MUST keep strict schema validation, one bounded repair attempt, no automatic persistence, and preview/confirm separation.

#### Scenario: Artifact gate

- **GIVEN** Generate Artifact acceptance checks
- **WHEN** drafts are generated or repaired
- **THEN** outputs remain schema-compliant review content
- **AND** confirmation endpoints are not called by acceptance.

### Requirement: Response Quality Acceptance

Representative responses MUST be evaluated by reasoning properties rather than exact wording.

#### Scenario: Quality checks

- **GIVEN** representative model responses
- **WHEN** the quality gate runs
- **THEN** responses lead with the important observation, add value beyond visible fields, separate fact/inference/uncertainty, avoid generic filler, include specific next steps, challenge weak assumptions, and avoid fabricated conclusions.

### Requirement: Frontend Polish Gate

The consolidated frontend MUST expose only approved controls and render workflow feedback coherently.

#### Scenario: UI polish checks

- **GIVEN** focused frontend tests run
- **WHEN** AI surfaces render
- **THEN** labels, artifact menus, chooser state, loading/progress, timeout, degraded/partial, and error states are visible and usable across wrapped layouts.

### Requirement: Production-Safe Live Sweep Plan

The live acceptance sweep MUST be representative, production-safe, and opt-in for mutation-adjacent behavior.

#### Scenario: Live sweep matrix

- **GIVEN** live sweep planning runs
- **WHEN** no explicit mutation opt-in flag is set
- **THEN** drafts remain non-persistent, manual briefing creation is status-only, confirmation endpoints are skipped, and only representative workflow/status calls are planned.
