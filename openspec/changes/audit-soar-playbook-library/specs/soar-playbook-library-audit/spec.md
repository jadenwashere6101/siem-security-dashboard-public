## ADDED Requirements

### Requirement: Playbook Library Audit Deliverable
The project SHALL maintain a single audit deliverable documenting the current state of the SOAR playbook subsystem, covering: an executive summary, a current playbook inventory, a playbook quality assessment, per-unit recommendations (KEEP / KEEP WITH IMPROVEMENTS / MERGE / REPLACE / RETIRE), a catalog of missing high-value playbooks, a gap analysis of missing SOAR capabilities, architectural recommendations, a prioritized roadmap classified by value (High/Medium/Low) and effort (Small/Medium/Large), risks, and a future implementation strategy.

#### Scenario: Inventory reflects actual persisted playbook state
- **WHEN** the audit's Current Playbook Inventory section is read
- **THEN** it SHALL state the actual number of concrete, named, persisted playbook definitions found in the codebase at time of audit, and SHALL NOT imply named playbooks exist if none are persisted in `playbook_definitions`.

#### Scenario: Every existing unit receives an explicit recommendation
- **WHEN** the audit's Individual Playbook Recommendations section is read
- **THEN** every existing playbook-subsystem unit assessed in the Quality Assessment section SHALL carry exactly one of: KEEP, KEEP WITH IMPROVEMENTS, MERGE, REPLACE, or RETIRE, with a stated justification.

#### Scenario: Missing playbooks are grounded, not speculative
- **WHEN** the audit's Missing Playbooks section lists a candidate playbook
- **THEN** each entry SHALL state its SOC problem, trigger, required enrichment, automation steps, approval requirements, response actions, interview value, implementation complexity, and dependencies, and SHALL identify whether its trigger already exists in the codebase or depends on a detection/ingestion capability that does not yet exist.

#### Scenario: Roadmap items are independently classified
- **WHEN** the audit's Prioritized Roadmap section lists an item
- **THEN** each item SHALL carry both a value classification (High, Medium, or Low) and an independent effort classification (Small, Medium, or Large).

### Requirement: Audit-Only Change Boundary
This change SHALL NOT modify application source code, database schema, migrations, playbook definitions, or tests, and SHALL NOT introduce new APIs. It SHALL be limited to the OpenSpec change artifacts under `openspec/changes/audit-soar-playbook-library/`.

#### Scenario: No functional files touched
- **WHEN** this change is reviewed via `git status`/`git diff` after being written
- **THEN** the only files added or modified SHALL be under `openspec/changes/audit-soar-playbook-library/`, with zero changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.

#### Scenario: No commit performed as part of this change
- **WHEN** this change's artifacts are created
- **THEN** no git commit SHALL be created as part of producing this deliverable; committing, if desired, SHALL be a separate explicit user action.
