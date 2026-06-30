## ADDED Requirements

### Requirement: Child Change Scope
This change SHALL implement Phases 12 and 13 from parent roadmap `openspec/changes/clarify-soar-response-outcomes` — documentation, analyst runbooks, interview notes, and production rollout/rollback checkpoints.

#### Scenario: Parent roadmap remains master
- **WHEN** this child change is implemented
- **THEN** the parent roadmap SHALL remain the master roadmap/spec and this child change SHALL be treated as the active implementation spec for Phases 12 and 13 work only

#### Scenario: No code changes
- **WHEN** this child change is implemented
- **THEN** it SHALL NOT add migrations, modify API routes, change canonical outcome writers, modify UI components, or add new tests

#### Scenario: Depends on all prior phases
- **WHEN** this child change is implemented
- **THEN** all Phases 1–11 SHALL be implemented and passing before rollout checkpoints are verified

### Requirement: SOAR Architecture Documentation Updated
The SOAR architecture documentation SHALL be updated with canonical outcome model definitions.

#### Scenario: Model documented
- **WHEN** this child change is complete
- **THEN** there SHALL be documentation covering the canonical decision/outcome-event model, `soar_correlation_id` propagation rules, latest-outcome read model, and all canonical enum values

#### Scenario: Boolean compatibility documented
- **WHEN** this child change is complete
- **THEN** there SHALL be documentation covering `external_executed`, `tracking_recorded`, and `simulated` compatibility rules

### Requirement: Dashboard Wording Guide Complete
A dashboard wording guide SHALL document canonical label text for all canonical conditions.

#### Scenario: All modes and states covered
- **WHEN** the wording guide is complete
- **THEN** it SHALL cover all four `execution_mode` values, all nine `execution_state` values, and all three execution boolean combinations

#### Scenario: Standalone executed prohibited
- **WHEN** the wording guide is complete
- **THEN** it SHALL explicitly state that standalone `"Executed"` MUST NOT be used in any canonical label

#### Scenario: Authoritative
- **WHEN** the wording guide is complete
- **THEN** it SHALL be marked as authoritative for all frontend label decisions in Phases 7–9

### Requirement: Rollback Behavior Documented
Schema additions and rollback behavior SHALL be documented.

#### Scenario: Safe rollback confirmed
- **WHEN** this child change is complete
- **THEN** there SHALL be documentation confirming that schema rollback does not require reconstructing old behavior because legacy tables remain authoritative during rollout

### Requirement: Backfill Strategy Documented
Backfill dry-run/write-mode strategy and legacy compatibility SHALL be documented.

#### Scenario: Dry-run documented
- **WHEN** this child change is complete
- **THEN** there SHALL be documentation covering dry-run output format, review requirements, and how to interpret results before write mode

#### Scenario: Idempotency documented
- **WHEN** this child change is complete
- **THEN** there SHALL be documentation confirming that write-mode backfill is idempotent and re-runnable without creating duplicate decisions/events

### Requirement: Real Execution Safety Boundaries Documented
Real execution safety boundaries SHALL be explicitly documented.

#### Scenario: Firewall remains dry-run
- **WHEN** this child change is complete
- **THEN** there SHALL be documentation explicitly stating the firewall adapter remains simulation/dry-run only and no Phase 1–13 work enables real firewall enforcement

#### Scenario: Future real execution requires new OpenSpec
- **WHEN** this child change is complete
- **THEN** there SHALL be documentation stating that changes to real execution boundaries require a separate approved OpenSpec

### Requirement: Analyst Runbooks Present
Step-by-step analyst runbooks SHALL answer the primary outcome questions.

#### Scenario: Primary question answerable
- **WHEN** runbooks are complete
- **THEN** an analyst SHALL be able to follow the runbooks to answer: "What happened?", "Was anything actually executed?", "Why was this blocked?", "What playbook ran?", and "What does this queue item mean?"

### Requirement: Interview Notes Complete
Interview notes SHALL document why canonical outcomes were introduced and how they reduce ambiguity.

#### Scenario: Notes cover introduction rationale
- **WHEN** interview notes are complete
- **THEN** they SHALL cover the problem with ambiguous `executed` semantics, what the canonical model replaces, and what was preserved

### Requirement: Rollout Checkpoints Verified
All six rollout checkpoints SHALL be verified and documented.

#### Scenario: Schema rollback checkpoint
- **WHEN** Checkpoint 1 is verified
- **THEN** it SHALL be confirmed that schema-only deployment can be rolled back without changing existing behavior

#### Scenario: Dual-write disable checkpoint
- **WHEN** Checkpoint 2 is verified
- **THEN** it SHALL be confirmed that dual-write can be disabled without runtime errors in queue, approval, playbook, or notification paths

#### Scenario: API legacy fallback checkpoint
- **WHEN** Checkpoint 3 is verified
- **THEN** it SHALL be confirmed that frontend can render with legacy fields only when `response_outcome` is absent

#### Scenario: UI null-outcome checkpoint
- **WHEN** Checkpoint 4 is verified
- **THEN** it SHALL be confirmed that Phase 7 components handle null `response_outcome` gracefully based on Phase 7 null-handling test results

#### Scenario: Production rollout order documented
- **WHEN** Checkpoint 5 is verified
- **THEN** there SHALL be documentation of the required production rollout sequence from schema to canonical UI enable

#### Scenario: Production rollback order documented
- **WHEN** Checkpoint 6 is verified
- **THEN** there SHALL be documentation of the required rollback sequence from UI revert to additive data preserved

### Requirement: Known Risks Documented
All known risks from the parent design section SHALL have documented mitigations confirmed as implemented.

#### Scenario: Risk mitigations confirmed
- **WHEN** this child change is complete
- **THEN** each risk from the parent design section SHALL have a mitigation entry confirming the mitigation was implemented during Phases 1–11

#### Scenario: Operator mitigations documented
- **WHEN** this child change is complete
- **THEN** there SHALL be documentation of operator-facing mitigations (dry-run review, backfill review, dual-write confirmation, e2e test pass, rollout order review) required before enabling canonical UI in production

### Requirement: OpenSpec Task Status Current
Parent roadmap task status SHALL be updated as tasks are completed.

#### Scenario: Parent tasks updated
- **WHEN** each Phase 12 and 13 task is completed
- **THEN** the corresponding task in `clarify-soar-response-outcomes/tasks.md` SHALL be marked complete
