## ADDED Requirements

### Requirement: Parent Roadmap Tracks Integration Delivery Controls Suite
The project SHALL maintain a parent roadmap for the SOAR notification Integration Delivery Controls initiative that lists the planned child specs, their sequencing, their scope boundaries, and their validation/deployment gates without implementing application behavior.

#### Scenario: Child specs are listed
- **WHEN** the roadmap is reviewed
- **THEN** it SHALL list `soar-notification-readiness-test-buttons`, `soar-notification-provider-active-controls`, `soar-playbook-notification-enforcement`, and `soar-notification-delivery-history` as future child specs, in that sequenced order.

#### Scenario: Roadmap remains coordination-only
- **WHEN** this parent change is reviewed
- **THEN** it SHALL NOT modify application source files, tests, backend schema, migrations, deployment scripts, or runtime configuration.

### Requirement: Shared Terminology Is Defined
The roadmap SHALL define Configured, Tested, Active, Delivered, and Simulation, and every future child spec under this roadmap SHALL use these terms consistently with the definitions given here.

#### Scenario: Terminology distinguishes code existing from proven delivery
- **WHEN** the roadmap terminology is reviewed
- **THEN** it SHALL make clear that a provider having real-mode code (Configured-capable) is not by itself evidence of Tested, Active, or Delivered status.

### Requirement: Current Adapter Reality Is Recorded Accurately
The roadmap SHALL record, based on the current codebase, which notification providers have real-mode code paths, their guard model, and which have been proven to deliver.

#### Scenario: Slack is recorded as the only proven provider
- **WHEN** the current adapter reality table is reviewed
- **THEN** Slack SHALL be recorded as the only provider with a confirmed prior real delivery, Teams SHALL be recorded as attempted-but-unproven, and Email and Webhook SHALL be recorded as never proven.

#### Scenario: Firewall is recorded as simulation-only with no real-mode path
- **WHEN** the current adapter reality table is reviewed
- **THEN** Firewall SHALL be recorded as having no real-mode code path at all, and the roadmap SHALL state that any future real firewall execution requires a separate, explicitly approved OpenSpec.

### Requirement: Database And Backend Findings Are Recorded
The roadmap SHALL record which existing database tables and backend routes are relevant to Integration Delivery Controls, and which parts of the planned system likely require new migrations or new backend endpoints.

#### Scenario: Existing delivery-attempt storage is identified
- **WHEN** the roadmap's database findings are reviewed
- **THEN** it SHALL identify the existing `notification_delivery_attempts` table and `core/notification_delivery_store.py` as the current, reusable foundation for delivery-history evidence.

#### Scenario: Missing durable provider-state storage is identified
- **WHEN** the roadmap's database findings are reviewed
- **THEN** it SHALL state that no durable per-provider Configured/Tested/Active status currently exists, and that a new migration is likely required to add it.

### Requirement: Firewall Simulation-Only Boundary Is Preserved
The roadmap SHALL state that Firewall remains dry-run/simulation only across every child spec in this initiative, with no real-execution path introduced.

#### Scenario: No child spec enables real firewall execution
- **WHEN** the child spec plan is reviewed
- **THEN** none of the four listed child specs SHALL introduce real firewall execution, and provider Active/Inactive controls SHALL explicitly exclude Firewall from real enablement.

### Requirement: Safe Failure Behavior Is Specified For Future Enforcement
The roadmap SHALL specify that future playbook notification enforcement must skip cleanly for inactive providers, must not fake success, must not retry endlessly, and must not block unrelated playbook steps unless explicitly required by a future spec.

#### Scenario: Skip behavior is described with a concrete example
- **WHEN** the roadmap's playbook enforcement plan is reviewed
- **THEN** it SHALL describe recording a clear skipped-by-policy outcome (for example, "Skipped: Teams integration inactive") distinct from a failed delivery attempt.

### Requirement: Phase Checklist Is Included
The roadmap SHALL include checklists for audit, child spec creation, implementation sequencing, validation, deployment/rebuild, and future expansion considerations.

#### Scenario: Required phases are present
- **WHEN** `tasks.md` is reviewed
- **THEN** it SHALL include checklist sections for audit, child spec creation, implementation sequencing, validation, deployment/rebuild, and future expansion considerations.

### Requirement: Roadmap Introduces No Runtime Or External Effects
This parent roadmap SHALL NOT trigger any real Slack, Teams, Email, Webhook, or Firewall action, and SHALL NOT expose credentials or secrets.

#### Scenario: No external call is made by this change
- **WHEN** this parent roadmap is created and reviewed
- **THEN** no Slack, Teams, Email, Webhook, or Firewall system SHALL be contacted or configured as a result.
