## ADDED Requirements

### Requirement: Version 1 Playbook Set
The project SHALL define exactly five Version 1 playbooks — Brute Force Containment, Password Spray Investigation, Successful Login After Spray Response, Malicious IP Containment, and Reputation-Only Investigation — each specified with a trigger, purpose, step-by-step flow, the existing engine actions it uses, dynamic parameter bindings where required, its approval requirement, its expected outcome, and its justification for inclusion in Version 1.

#### Scenario: Every playbook targets a real, existing trigger
- **WHEN** a Version 1 playbook's trigger is read
- **THEN** it SHALL reference only `alert_type`, `min_severity`, `source`, `correlation_flag`, or `reputation_score_min` values that correspond to alert types or thresholds already produced by `engines/detection_engine.py` or `engines/correlation_engine.py` today.

#### Scenario: Containment playbooks use dynamic block_ip
- **WHEN** a Version 1 playbook's purpose requires blocking the offending source IP (Brute Force Containment, Successful Login After Spray Response, Malicious IP Containment)
- **THEN** its approved `block_ip` step SHALL bind `params.source_ip` to `{{alert.source_ip}}` (or equivalent syntax defined by `dynamic-playbook-parameter-binding`), not a static IP literal.

#### Scenario: Investigation playbooks omit block_ip by design
- **WHEN** Password Spray Investigation or Reputation-Only Investigation is read
- **THEN** it SHALL NOT include a `block_ip` step — not because of engine limitation, but because spray and low-tier reputation signals warrant investigation without automatic blocking.

### Requirement: Dynamic Parameter Bindings Are Used Where Required
Version 1 playbooks SHALL use dynamic parameter binding for any step whose correctness depends on the triggering alert's fields, including `block_ip` target IPs and notification messages that reference alert context.

#### Scenario: Notification steps bind alert context
- **WHEN** a Version 1 playbook includes a notification step whose message should reference the triggering alert
- **THEN** its `params` SHALL use dynamic bindings (e.g., `{{alert.source_ip}}`, `{{alert.alert_type}}`, `{{alert.severity}}`) as specified in `design.md`, not static placeholder text.

#### Scenario: Playbook designs assume binding capability exists
- **WHEN** any Version 1 playbook step with dynamic bindings is reviewed
- **THEN** its design SHALL assume `dynamic-playbook-parameter-binding` is implemented — not a static-params workaround.

### Requirement: Implementation Blocked on Parameter Binding
Content authorship for Version 1 playbooks SHALL NOT begin until `dynamic-playbook-parameter-binding` is implemented. This spec defines target playbook shapes only.

#### Scenario: No playbook rows before binding
- **WHEN** `dynamic-playbook-parameter-binding` is not yet implemented
- **THEN** no `playbook_definitions` row for any Version 1 playbook SHALL be created as part of this change or its implementation pass.

#### Scenario: Blocker is named in dependencies
- **WHEN** this change's dependencies are read
- **THEN** `dynamic-playbook-parameter-binding` SHALL be listed as a hard blocking dependency for implementation tasks.

### Requirement: Deferred Playbooks Are Enumerated With Blocking Dependencies
The project SHALL enumerate playbook ideas explicitly excluded from Version 1, each with the specific capability or data source it is blocked on (excluding parameter binding, which is now a tracked engine capability).

#### Scenario: Every deferred idea names its blocker
- **WHEN** the deferred-playbooks list is read
- **THEN** each entry SHALL state whether it is blocked on a missing ingestion source, a missing detection/correlation rule, or a not-yet-built roadmap engine capability other than parameter binding — no entry SHALL be listed without a stated reason.

### Requirement: Content-Only Change Boundary
This change SHALL NOT modify application source code, database schema, migrations, frontend files, or tests, SHALL NOT create any `playbook_definitions` rows, and SHALL NOT introduce any new engine capability, action, or UI change. Content authorship is deferred to a separate, later, explicitly-requested implementation pass under this same child spec, using only the existing `POST /playbooks` API after `dynamic-playbook-parameter-binding` is complete.

#### Scenario: No functional files touched
- **WHEN** this change is reviewed via `git status`/`git diff` after being written
- **THEN** the only files added or modified SHALL be under `openspec/changes/core-playbook-pack-v1/`, with zero changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.

#### Scenario: No playbook rows created as part of this change
- **WHEN** this change's artifacts are created or updated
- **THEN** no `playbook_definitions` row SHALL be created, and no existing engine behavior SHALL be modified — those remain deferred tasks tracked in `tasks.md` for a future implementation pass gated on parameter binding.
