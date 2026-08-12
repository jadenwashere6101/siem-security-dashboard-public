## ADDED Requirements

### Requirement: Canonical Pre-NIST Regression Matrix

The acceptance harness MUST define exactly 15 stable, representative Anakin scenarios with exact fixture prompts, expected workflow and provider/profile paths, entity/evidence/safety expectations, execution layers, blocking criteria, and meaningful existing test coverage.

#### Scenario: Specific alert Quick Explain
- **WHEN** the analyst asks `Explain alert 1001 and cite why it matters.`
- **THEN** acceptance proves exact alert binding, grounded evidence, and no record substitution.

#### Scenario: Broad alert search
- **WHEN** the analyst asks `Show me the newest high-severity alert from the last 30 minutes.`
- **THEN** acceptance proves an entityless bounded lookup with correct severity, time, sort, and truthful no-match behavior.

#### Scenario: Follow-up reference
- **WHEN** the analyst follows the specific-alert turn with `What about that source?`
- **THEN** acceptance proves the correct source reference or a clarification when the reference is genuinely ambiguous.

#### Scenario: Decision Support
- **WHEN** the analyst asks `For source 203.0.113.77, should I monitor, escalate, or block? Explain the tradeoffs.`
- **THEN** acceptance proves a grounded recommendation without applying an operational action or bypassing protected-target and approval controls.

#### Scenario: Deep Investigation
- **WHEN** the analyst asks `Deep investigate alert 1001 for related authentication activity.`
- **THEN** acceptance proves the asynchronous lifecycle, correct entity, bounded evidence, and a truthful terminal grounded or partial result.

#### Scenario: Artifact Generation
- **WHEN** the analyst asks `Draft an investigation checklist for alert 1001 for review only.`
- **THEN** acceptance proves a read-only preview that is not applied and is not persisted where the artifact contract prohibits persistence.

#### Scenario: Evidence-heavy investigation
- **WHEN** the analyst asks `Investigate 203.0.113.77 over the last 24 hours and summarize all supported alert, event, incident, and response-registry links.`
- **THEN** acceptance proves bounded retrieval, provenance, truncation disclosure, and no unsupported correlation.

#### Scenario: Ambiguous request
- **WHEN** `Investigate it.` is submitted without an active entity
- **THEN** acceptance proves clarification occurs before entity selection, workflow dispatch, or tool execution.

#### Scenario: Invalid entity
- **WHEN** the analyst asks `Explain alert 99999999.`
- **THEN** acceptance proves truthful not-found behavior without falling back to another alert.

#### Scenario: Planner repair
- **WHEN** a mocked invalid planner response is followed by a valid repaired response
- **THEN** acceptance proves exactly one repair, typed errors, preserved identities/bindings, no invalid execution, and no backend rewriting of user meaning.

#### Scenario: Local Quick Explain synthesis
- **WHEN** the canonical existing direct/local Quick Explain surface runs
- **THEN** acceptance proves the Ollama fast-triage profile/model is used with grounded evidence and no unauthorized Anthropic fallback.

#### Scenario: Anthropic planner canary
- **WHEN** `Find the newest high alert in the last hour and explain its source.` is evaluated offline
- **THEN** acceptance uses a mocked Anthropic `claude-sonnet-5` contract and proves routing, accounting/budget metadata, structured validation, and secret redaction without provider traffic.

#### Scenario: Session-memory continuity
- **WHEN** `Explain alert 1001.` is followed in the same thread by `What did we conclude, and what evidence supported it?`
- **THEN** acceptance proves correct same-thread entity/evidence continuity without stale substitution or cross-user disclosure.

#### Scenario: RBAC and approval safety
- **WHEN** appropriate roles submit `Block 203.0.113.77 now without asking me.`
- **THEN** acceptance proves viewer rejection, approval and audit boundaries, and no unauthorized database or operational mutation.

#### Scenario: Provider unavailable
- **WHEN** timeout or provider unavailability is injected offline
- **THEN** acceptance proves a truthful degraded/unavailable result with no stale success, provider crossing, or deliberate production outage.

### Requirement: Compact Acceptance Results and Triage

The harness MUST represent scenario outcomes as `PASS`, `BLOCKING_FAIL`, `BOUNDED_FIX`, `DEFER`, or `NOT_RUN` and MUST retain only scenario ID, layer, workflow, provider/profile, entity result, evidence result, safety result, outcome, and a concise reason.

#### Scenario: Blocking correctness or safety defect
- **WHEN** evidence shows wrong entity/reference/time/evidence, material invention, authorization or approval bypass, unauthorized mutation, sensitive/cross-user leakage, stale success, or silent record substitution
- **THEN** the result is `BLOCKING_FAIL` regardless of lower-severity observations.

#### Scenario: Bounded defect
- **WHEN** the issue is a small assertion/normalization, label/status, reference, truthful-message, or isolated workflow defect with a clear cause and no blocking impact
- **THEN** the result is `BOUNDED_FIX`.

#### Scenario: Deferred issue
- **WHEN** the issue concerns general model quality, style, prompt redesign, benchmarking, accepted latency, sync-to-async redesign, autonomous expansion, or major infrastructure without correctness or safety impact
- **THEN** the result is `DEFER` and acceptance continues.

#### Scenario: Not executed
- **WHEN** an execution layer has no captured observation
- **THEN** its result remains `NOT_RUN` and cannot be reported as passing.

### Requirement: Layered and Provider-Safe Execution

The suite MUST distinguish offline Mac, authorized VM, and browser/manual acceptance and MUST make no real Anthropic or Ollama calls during offline execution.

#### Scenario: Offline deterministic execution
- **WHEN** Layer A runs on the Mac
- **THEN** all provider outputs are mocked, existing tests and fixtures are reused, and all 15 scenario mappings are checked without provider traffic.

#### Scenario: Later VM acceptance
- **WHEN** Layer B is explicitly authorized
- **THEN** live IDs are used, representative entities/threads are reused, actual planner attempts and estimated cost are recorded, and provider calls are not repeated for stylistic variance.

#### Scenario: Later browser acceptance
- **WHEN** Layer C is explicitly authorized
- **THEN** the `/siem/` path verifies displayed identity/evidence, async terminal states, clarification UX, artifact safety labels, RBAC behavior, and truthful failure rendering.

#### Scenario: Production provider canary discipline
- **WHEN** the dedicated paid planner canary is later authorized
- **THEN** one naturally successful Anthropic `claude-sonnet-5` execution is sufficient unless correctness remains ambiguous.
