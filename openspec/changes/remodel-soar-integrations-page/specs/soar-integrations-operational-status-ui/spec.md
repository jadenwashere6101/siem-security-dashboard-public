## ADDED Requirements

### Requirement: Operational Status First
The SOAR Integrations page SHALL present each integration as an operational status card before showing engineering internals.

#### Scenario: Adapter cards answer primary operational questions
- **WHEN** an authenticated analyst opens the SOAR Integrations page
- **THEN** each integration card SHALL show Current Mode, Health, Used By, External Delivery, Ready for Real Mode, Last Delivery, Last Tested, Supported Actions, and a short integration description.

#### Scenario: Default view avoids implementation-detail dominance
- **WHEN** integration cards are first rendered
- **THEN** circuit breaker fields, cooldown fields, retry fields, half-open probe fields, and manual simulation controls SHALL NOT dominate the default card view.

#### Scenario: Existing dark theme is preserved
- **WHEN** the remodeled page renders
- **THEN** it SHALL remain consistent with the existing dark SIEM/SOC dashboard style.

### Requirement: Clear Mode and Health Labels
The SOAR Integrations page SHALL translate raw adapter state into clear operational labels without changing backend semantics.

#### Scenario: Simulation mode is clear
- **WHEN** an adapter is not ready for real external delivery
- **THEN** the primary card SHALL label the mode as Simulation or Disabled rather than only showing "Real Integration Disabled".

#### Scenario: Real mode readiness is clear
- **WHEN** an adapter is real-mode ready according to existing backend status
- **THEN** the card SHALL show Ready for Real Mode as Yes and External Delivery as Enabled.

#### Scenario: Firewall dry-run is clear
- **WHEN** the firewall adapter is shown
- **THEN** the card SHALL clearly communicate that it is dry-run or simulation-only and does not perform real firewall mutation.

#### Scenario: Raw internal state remains available
- **WHEN** raw state such as `closed`, `open`, or `half_open` is useful for engineering diagnosis
- **THEN** it SHALL be available in Advanced rather than replacing primary operational health labels.

### Requirement: Missing Configuration Is Secret-Safe
The SOAR Integrations page SHALL show missing configuration using env variable names only.

#### Scenario: Missing env names are shown
- **WHEN** an integration is not ready for real mode because required configuration is missing
- **THEN** the card SHALL show the missing env variable names, such as `TEAMS_WEBHOOK_URL` or `SOAR_REAL_TEAMS_ENABLED`.

#### Scenario: Secret values are never shown
- **WHEN** the page renders configuration readiness, missing configuration, status JSON, or advanced details
- **THEN** it SHALL NOT display webhook URLs, tokens, SMTP passwords, usernames, host values, or other secret values.

#### Scenario: Unknown missing config degrades safely
- **WHEN** existing backend status does not provide all missing env variable names
- **THEN** the frontend SHALL show only safe known env names or a non-secret fallback, and SHALL NOT infer or expose values.

### Requirement: Usage Visibility
The SOAR Integrations page SHALL distinguish integrations used by default/core playbooks from integrations that are merely available.

#### Scenario: Default usage count is visible
- **WHEN** an integration is used by default/core playbooks according to the current frontend mapping or available status data
- **THEN** the card SHALL show the number of default/core playbooks or a clear used-by label.

#### Scenario: Unused default integrations are clear
- **WHEN** an integration is not used by default/core playbooks
- **THEN** the card SHALL show "Not used by default" or equivalent clear wording.

#### Scenario: Static usage mapping is bounded
- **WHEN** v1 uses a frontend-owned mapping for default/core playbook usage
- **THEN** the UI SHALL label the value as default/core usage and SHALL NOT imply full dynamic usage discovery.

### Requirement: Advanced Internals Are Collapsible
The SOAR Integrations page SHALL move engineering internals into an Advanced section that is collapsed by default.

#### Scenario: Advanced section contains reliability internals
- **WHEN** an adapter has circuit breaker or reliability fields
- **THEN** Advanced SHALL include state, failure threshold, consecutive failures, retry eligibility, timeout, cooldown, half-open probe availability, manual action fields, and internal adapter details where available.

#### Scenario: Advanced section is collapsed by default
- **WHEN** an integration card first renders
- **THEN** Advanced internals SHALL be hidden behind an explicit expandable control.

#### Scenario: Super-admin controls remain advanced-only
- **WHEN** a super-admin views the page
- **THEN** existing simulation circuit breaker controls SHALL be available only inside Advanced and SHALL continue to require a reason.

#### Scenario: Analyst controls remain read-only
- **WHEN** an analyst views the page
- **THEN** privileged simulation controls SHALL NOT be shown.

### Requirement: Operational Terminology
The SOAR Integrations page SHALL prefer user-facing operational wording for primary controls and labels.

#### Scenario: Simulation control labels are clearer
- **WHEN** super-admin simulation controls are shown
- **THEN** labels SHOULD use operational wording such as Restore Healthy State, Simulate Failure, and Simulate Recovery while preserving the current underlying circuit breaker API calls.

#### Scenario: Engineering terms are not removed entirely
- **WHEN** an engineer expands Advanced
- **THEN** precise implementation terms MAY remain visible where useful for debugging.

### Requirement: Frontend-Only Remodel
The SOAR Integrations page remodel SHALL preserve existing backend behavior and shall not add real execution behavior.

#### Scenario: Backend contract remains unchanged
- **WHEN** this remodel is implemented
- **THEN** it SHALL use the existing integration status/service contract unless a future spec explicitly approves backend changes.

#### Scenario: No real integration traffic is triggered
- **WHEN** a user opens the page, expands Advanced, or uses existing simulation controls
- **THEN** the page SHALL NOT send Slack, Teams, Email, or Webhook traffic and SHALL NOT execute firewall changes.

#### Scenario: No new test buttons are introduced
- **WHEN** this remodel is implemented
- **THEN** it SHALL NOT add test-connection, run-adapter, send-notification, or execute-firewall controls.

#### Scenario: Existing status states continue to work
- **WHEN** the integration status request is loading, errors, returns no adapters, or returns partial adapter data
- **THEN** the page SHALL render a safe loading, error, empty, or partial-data state without crashing.
