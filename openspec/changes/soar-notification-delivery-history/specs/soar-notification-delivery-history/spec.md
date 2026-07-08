## ADDED Requirements

### Requirement: Provider Delivery Summary
The system SHALL expose provider-level notification delivery evidence for Slack, Teams, Email, and Webhook.

#### Scenario: Providers are always represented
- **WHEN** an authenticated analyst or super-admin reads notification delivery summary
- **THEN** the response SHALL include Slack, Teams, Email, and Webhook even when a provider has no delivery attempts.

#### Scenario: Empty provider has no fabricated evidence
- **WHEN** a provider has no matching delivery attempt rows
- **THEN** last successful delivery, last failed delivery, and last tested SHALL be null or equivalent empty values, and the UI SHALL NOT imply Delivered or Tested status.

### Requirement: Last Successful Delivery
The system SHALL report the latest successful real delivery per provider using `notification_delivery_attempts`.

#### Scenario: Real success is delivered evidence
- **WHEN** a provider has a latest row with `mode = "real"` and `status = "success"` for a non-test delivery action
- **THEN** that row SHALL be eligible as the provider's last successful delivery.

#### Scenario: Simulation success is not delivered evidence
- **WHEN** a provider has only successful Simulation rows
- **THEN** the provider SHALL NOT be shown as Delivered, and those rows SHALL be labeled as Simulation.

### Requirement: Last Failed Delivery
The system SHALL report the latest failed real delivery per provider without exposing secrets.

#### Scenario: Real failed statuses are failure evidence
- **WHEN** a provider has a latest real non-test delivery row with status `failed`, `timeout`, or `blocked`
- **THEN** that row SHALL be eligible as the provider's last failed delivery.

#### Scenario: Failure reason is secret-free
- **WHEN** a failed delivery row includes failure details
- **THEN** the API and UI SHALL show only sanitized failure code, sanitized failure message, safe classification, or generic status-derived reason, and SHALL NOT expose webhook URLs, SMTP credentials, tokens, headers, raw payloads, raw responses, or secret values.

### Requirement: Last Tested
The system SHALL report Last Tested from manual test-send delivery attempt rows created by the readiness-test child spec.

#### Scenario: Successful manual test sets tested evidence
- **WHEN** a provider has a latest manual test row with `status = "success"`
- **THEN** the provider's Last Tested SHALL reference that attempt and SHALL indicate the test succeeded.

#### Scenario: Failed manual test is distinct from delivered failure
- **WHEN** a provider has a latest manual test row with `status = "failed"`, `timeout`, or `blocked`
- **THEN** Last Tested SHALL show the test result and safe reason, but the row SHALL NOT be counted as a last failed playbook delivery.

#### Scenario: Manual test marker is reused
- **WHEN** manual test rows are queried
- **THEN** the implementation SHALL reuse the marker established by `soar-notification-readiness-test-buttons`, expected as `action = "test_notification"` unless that child implemented an equivalent documented marker.

### Requirement: Recent Delivery Attempts
The system SHALL expose recent delivery attempts per provider in newest-first order.

#### Scenario: Recent attempts include type labels
- **WHEN** recent attempts are returned
- **THEN** each attempt SHALL identify whether it is a manual test, real delivery, or Simulation.

#### Scenario: Recent attempts are bounded
- **WHEN** a provider has many attempts
- **THEN** the API SHALL return a bounded recent list suitable for the SOAR Integrations UI rather than an unbounded history.

### Requirement: SOAR Integrations UI Evidence
The SOAR Integrations UI SHALL show clear, compact delivery evidence for Slack, Teams, Email, and Webhook.

#### Scenario: Summary fields are visible
- **WHEN** a user views a provider on the SOAR Integrations page
- **THEN** the UI SHALL show Last successful delivery, Last failed delivery, Last tested, and provider-level delivery status.

#### Scenario: Advanced attempts are collapsed
- **WHEN** recent delivery attempts are available
- **THEN** the UI SHALL keep detailed attempt history collapsed or otherwise secondary so the page is not overwhelmed.

#### Scenario: Simulation is clearly labeled
- **WHEN** an attempt was Simulation
- **THEN** the UI SHALL label it as Simulation and SHALL state or imply that no external call was made.

#### Scenario: Firewall remains simulation-only
- **WHEN** Firewall appears near the SOAR Integrations evidence UI
- **THEN** it SHALL be labeled simulation/dry-run only and SHALL NOT have real delivery evidence controls or Delivered status.

### Requirement: Read-Only Evidence Surface
This child spec SHALL add only read-oriented delivery evidence behavior.

#### Scenario: No notification is sent
- **WHEN** a user views delivery history or provider delivery summary
- **THEN** the system SHALL NOT contact Slack, Teams, SMTP, Webhook, Firewall, VM, or Azure.

#### Scenario: No Active state changes
- **WHEN** this spec is implemented
- **THEN** it SHALL NOT add provider Active/Inactive toggles or change provider Active state.

#### Scenario: No playbook enforcement changes
- **WHEN** this spec is implemented
- **THEN** it SHALL NOT change whether playbooks attempt, skip, retry, or fail notification steps.
