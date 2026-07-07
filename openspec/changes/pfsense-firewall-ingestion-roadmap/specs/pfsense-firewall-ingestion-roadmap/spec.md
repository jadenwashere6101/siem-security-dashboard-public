## ADDED Requirements

### Requirement: Parent Coordination Roadmap
The project SHALL maintain a parent roadmap for pfSense firewall log ingestion that coordinates code tasks and non-code/operator tasks from audit through production readiness.

#### Scenario: Roadmap tracks the full integration lifecycle
- **WHEN** the parent roadmap is read
- **THEN** it SHALL include phases for read-only environment audit, architecture audit, security review, detailed child OpenSpec creation, milestone implementation planning, deployment checklist, runtime validation, and production readiness/uncle handoff.

#### Scenario: Roadmap includes non-repo operational work
- **WHEN** the roadmap checklist is reviewed
- **THEN** it SHALL track operational tasks that may happen outside the repo, including Azure NSG planning, VM firewall checks, deployment verification, runtime service validation, and pfSense configuration handoff.

#### Scenario: Roadmap remains parent-only
- **WHEN** this change is created
- **THEN** it SHALL NOT create child implementation specs for listener, parser, adapter/route, event types, detection rules, or deployment/service setup.

### Requirement: Source-of-Truth and Runtime Guardrails
The parent roadmap SHALL explicitly preserve the Mac repo as the source of truth and the Azure VM as deployment/runtime only.

#### Scenario: Mac remains source of truth
- **WHEN** implementation work is planned from this roadmap
- **THEN** specs, source code, tests, commits, and pushes SHALL be performed from the Mac repo.

#### Scenario: VM remains deployment/runtime only
- **WHEN** VM work is planned from this roadmap
- **THEN** the VM SHALL be used only for deployment/runtime operations unless the user explicitly labels the work a VM emergency hotfix.

#### Scenario: Dirty VM blocks merge
- **WHEN** a VM sync or merge is planned
- **THEN** the plan SHALL require checking VM cleanliness before merge and SHALL stop if the VM is dirty.

### Requirement: Security and Deployment Gates
The parent roadmap SHALL enforce security, deployment, and validation gates before runtime exposure or production log collection.

#### Scenario: No implementation before audits
- **WHEN** implementation is requested
- **THEN** Phase 0 read-only environment audit and Phase 1 architecture audit SHALL be complete before implementation starts.

#### Scenario: Runtime-affecting work requires deployment plan
- **WHEN** a runtime-affecting child feature is planned
- **THEN** the child spec SHALL include a deployment plan before implementation starts.

#### Scenario: No port opening before security review
- **WHEN** UDP listener exposure or port opening is considered
- **THEN** the security review SHALL be complete before any port is opened.

#### Scenario: No external pfSense configuration before readiness
- **WHEN** uncle/pfSense configuration is considered
- **THEN** our side SHALL be fully deployed and tested before any configuration request is sent.

#### Scenario: No production collection before runtime validation
- **WHEN** production/live pfSense log collection is considered
- **THEN** runtime validation SHALL pass before production collection begins.

### Requirement: Future Child Spec Scope
The parent roadmap SHALL require future child implementation specs to define explicit acceptance criteria, validation plans, and the exact ingestion flow before code changes are made.

#### Scenario: Child specs define ingestion flow
- **WHEN** child specs are created later
- **THEN** the listener flow SHALL document listener, source IP validation, packet length validation, control-character stripping, malformed syslog rejection, pfSense filterlog parsing, normalization, schema validation, ingest, detection engine, and SOAR/playbooks.

#### Scenario: Parent spec does not implement functionality
- **WHEN** this parent roadmap is validated
- **THEN** it SHALL NOT implement a listener, parser, adapter, route, event type, detection rule, deployment script, service unit, migration, or runtime configuration.

