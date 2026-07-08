## ADDED Requirements

### Requirement: Durable Provider Active State
The system SHALL store durable Active/Inactive state for Slack, Teams, Email, and Webhook notification providers.

#### Scenario: Providers default inactive
- **WHEN** provider controls are first read with no existing stored rows
- **THEN** Slack, Teams, Email, and Webhook SHALL be treated as Active Off.

#### Scenario: Active state persists
- **WHEN** a super-admin changes a provider Active state
- **THEN** the new state SHALL be stored in the backend/database and SHALL survive browser reloads and backend process restarts.

#### Scenario: LocalStorage is not the source of truth
- **WHEN** provider Active state is read or updated
- **THEN** the state SHALL come from backend durable storage and SHALL NOT be stored as a localStorage-only preference.

### Requirement: Provider Scope
The Active/Inactive controls SHALL apply only to Slack, Teams, Email, and Webhook.

#### Scenario: Firewall has no Active toggle
- **WHEN** the SOAR Integrations page displays Firewall
- **THEN** Firewall SHALL NOT have an Active toggle and SHALL be labeled as simulation/dry-run only.

#### Scenario: Firewall update is rejected
- **WHEN** a client attempts to update Active state for Firewall
- **THEN** the backend SHALL reject the request and SHALL NOT create an activatable Firewall provider record.

#### Scenario: Unknown provider is rejected
- **WHEN** a client attempts to read or update an unknown notification provider
- **THEN** the backend SHALL return a safe error and SHALL NOT create provider state for it.

### Requirement: Configured Tested Active Ready Model
The provider controls SHALL use the parent roadmap terminology for Configured, Tested, Active, Ready, Delivered, and Simulation.

#### Scenario: Configured status is shown
- **WHEN** provider control state is displayed
- **THEN** each provider SHALL show whether required env vars/secrets are configured without exposing secret values.

#### Scenario: Tested status is shown
- **WHEN** provider control state is displayed
- **THEN** each provider SHALL show Tested as Passed, Failed, or Never Tested.

#### Scenario: Active status is shown
- **WHEN** provider control state is displayed
- **THEN** each provider SHALL show Active as On or Off.

#### Scenario: Ready status is shown
- **WHEN** provider control state is displayed
- **THEN** each provider SHALL show Ready as Yes or No based on existing readiness plus Active/Tested/Configured state according to the implementation design.

### Requirement: Activation Gating
The system SHALL prevent or clearly warn against activating providers that are not Configured or not Tested.

#### Scenario: Not configured provider cannot silently become production-ready
- **WHEN** a provider is missing required configuration
- **THEN** the UI and backend behavior SHALL block activation or present an explicit warning, and the provider SHALL NOT appear production-ready.

#### Scenario: Never-tested provider cannot silently become production-ready
- **WHEN** a provider has Tested set to Never Tested
- **THEN** the UI and backend behavior SHALL block activation or present an explicit warning, and the provider SHALL NOT appear production-ready.

#### Scenario: Failed-tested provider cannot silently become production-ready
- **WHEN** a provider has Tested set to Failed
- **THEN** the UI and backend behavior SHALL block activation or present an explicit warning, and the provider SHALL NOT appear production-ready.

#### Scenario: Deactivation is always allowed
- **WHEN** a super-admin turns Active Off for a provider
- **THEN** the system SHALL allow the deactivation regardless of Configured or Tested state.

### Requirement: Provider Control APIs
The backend SHALL expose authenticated APIs for reading provider controls and updating Active state.

#### Scenario: Analysts can read provider controls
- **WHEN** an authenticated analyst requests provider controls
- **THEN** the backend SHALL return provider state without secret values.

#### Scenario: Super-admins can read provider controls
- **WHEN** an authenticated super-admin requests provider controls
- **THEN** the backend SHALL return provider state without secret values.

#### Scenario: Only super-admins can update provider controls
- **WHEN** a non-super-admin attempts to toggle Active state
- **THEN** the backend SHALL reject the request.

#### Scenario: Update endpoint returns updated state
- **WHEN** a super-admin successfully toggles a provider Active state
- **THEN** the backend SHALL return the updated provider control record.

### Requirement: Audit Active State Changes
The backend SHALL audit provider Active/Inactive changes without exposing secrets.

#### Scenario: Activation is audited
- **WHEN** a super-admin turns Active On
- **THEN** an audit event SHALL record actor, provider, previous active state, new active state, and non-secret gating context.

#### Scenario: Deactivation is audited
- **WHEN** a super-admin turns Active Off
- **THEN** an audit event SHALL record actor, provider, previous active state, new active state, and non-secret gating context.

#### Scenario: Secrets are not audited
- **WHEN** provider control changes are audited
- **THEN** audit details SHALL NOT include webhook URLs, SMTP passwords, tokens, headers, or secret values.

### Requirement: Frontend Active Controls
The SOAR Integrations page SHALL display Active/Inactive controls for supported notification providers.

#### Scenario: Super-admin sees toggles
- **WHEN** a super-admin views Slack, Teams, Email, or Webhook
- **THEN** each provider SHALL show an Active/Inactive toggle or equivalent control.

#### Scenario: Analyst sees read-only state
- **WHEN** an analyst views Slack, Teams, Email, or Webhook
- **THEN** each provider SHALL show Active state but SHALL NOT allow toggling it.

#### Scenario: Missing config names are safe
- **WHEN** a provider is missing configuration
- **THEN** the frontend SHALL show env variable names only and SHALL NOT show secret values.

#### Scenario: No manual test send is added
- **WHEN** this spec is implemented
- **THEN** the frontend SHALL NOT add manual test-send buttons or trigger real notifications.

### Requirement: Out-Of-Scope Behavior Is Not Implemented
This child spec SHALL NOT change notification delivery behavior, playbook enforcement, or firewall execution.

#### Scenario: No real notification is sent by Active control
- **WHEN** a provider Active state is read or toggled
- **THEN** the system SHALL NOT contact Slack, Teams, SMTP, or Webhook providers as part of that operation.

#### Scenario: Playbooks are not enforced yet
- **WHEN** this child spec is implemented
- **THEN** playbook notification steps SHALL NOT yet skip or execute based on Active state; that behavior belongs to `soar-playbook-notification-enforcement`.

#### Scenario: Delivery history is not added
- **WHEN** this child spec is implemented
- **THEN** it SHALL NOT add a delivery history dashboard.

#### Scenario: Firewall remains simulation-only
- **WHEN** this child spec is implemented
- **THEN** no real firewall blocking, API call, subprocess execution, or blocklist mutation path SHALL be added.
