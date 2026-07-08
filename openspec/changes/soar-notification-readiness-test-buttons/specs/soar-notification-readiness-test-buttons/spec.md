## ADDED Requirements

### Requirement: Readiness Model Distinguishes Configured, Tested, And Ready
The system SHALL define and display three distinct states per notification provider: Configured (required env vars/secrets present), Tested (result of the most recent manual test send), and Ready (Configured AND Tested = Passed).

#### Scenario: Ready requires both Configured and a passing test
- **WHEN** a provider's readiness is evaluated
- **THEN** Ready SHALL be Yes only if Configured is Yes and the most recent manual test recorded a passing result, and SHALL be No otherwise.

#### Scenario: Existing adapter guard readiness is not renamed or replaced
- **WHEN** this spec's Ready concept is implemented
- **THEN** it SHALL be a new, separately named value and SHALL NOT rename, remove, or repurpose the existing adapter-layer `real_mode_ready`/`real_mode_allowed` fields already relied on elsewhere in the codebase.

### Requirement: Scope Is Limited To Slack, Teams, Email, And Webhook
This spec SHALL plan readiness and test-send capability only for Slack, Teams, Email, and Webhook. Firewall SHALL be excluded entirely.

#### Scenario: No Firewall test button or endpoint
- **WHEN** the readiness UI or test-send backend is planned or implemented
- **THEN** no Firewall test button, test endpoint, or real-mode code path SHALL be introduced.

#### Scenario: Unknown or excluded adapter names are rejected
- **WHEN** a test-send request names an adapter other than `slack`, `teams`, `email`, or `webhook`
- **THEN** the request SHALL be rejected without attempting any adapter action.

### Requirement: Manual Test Send Reuses Existing Guards Without Weakening Them
A manual test send SHALL invoke the same four-guard fail-closed real-mode model (`INTEGRATION_MODE`, `SOAR_ENV` allowlist, per-adapter `SOAR_REAL_<PROVIDER>_ENABLED`, credential env vars) already enforced for playbook-triggered sends, and SHALL NOT introduce any bypass, shortcut, or weaker path.

#### Scenario: Guard-blocked test does not send
- **WHEN** a manual test is requested for a provider missing one or more required guards
- **THEN** no external call SHALL be made, and the result SHALL be recorded as blocked rather than as a fabricated success or an indistinguishable failure.

#### Scenario: Guard-blocked results are not shown as Failed
- **WHEN** a test result is guard-blocked rather than attempted-and-unsuccessful
- **THEN** the UI SHALL distinguish that outcome from a genuine delivery failure, and SHALL NOT display it merely as "Failed."

### Requirement: Test Sends Are Rate-Limited And Auditable
Manual test sends SHALL go through the existing per-adapter rate limiter and SHALL be recorded through the existing secret-redacted audit/delivery-attempt mechanisms.

#### Scenario: Rapid repeated test clicks are throttled
- **WHEN** a user triggers multiple test sends for the same provider in rapid succession
- **THEN** the existing adapter rate limit SHALL apply exactly as it does for real playbook-triggered sends.

#### Scenario: No secrets appear in recorded results
- **WHEN** a test-send attempt is recorded
- **THEN** no webhook URL, SMTP credential, or webhook auth token SHALL appear in the stored record, the audit log, or any API response.

### Requirement: Missing Configuration Is Shown As Exact Env Var Names
For each provider, the system SHALL display the specific missing environment variable names required to reach Configured, without exposing secret values.

#### Scenario: Fully configured provider shows no missing configuration
- **WHEN** all required env vars for a provider are present
- **THEN** its Missing Configuration list SHALL be empty.

#### Scenario: Partially configured provider lists only the missing names
- **WHEN** some required env vars for a provider are absent
- **THEN** the Missing Configuration list SHALL contain only the names of the absent variables, and SHALL NOT include unrelated deployment-mode guard names or any variable's value.

### Requirement: Last Test Result And Timestamp Are Displayed
For each provider, the system SHALL display the outcome (Passed / Failed / Never Tested) and timestamp of the most recent manual test send.

#### Scenario: Never-tested provider is shown honestly
- **WHEN** a provider has no recorded manual test attempt
- **THEN** its Tested state SHALL display as "Never Tested" and no Last Test timestamp SHALL be shown as if a test had occurred.

#### Scenario: Most recent test result is authoritative
- **WHEN** a provider has multiple recorded manual test attempts
- **THEN** the displayed Tested state and Last Test timestamp SHALL reflect only the most recent attempt.

### Requirement: Test Sends Reuse The Existing Delivery-Attempt Table
Manual test-send attempts SHALL be recorded using the existing `notification_delivery_attempts` table and its existing helper functions, distinguished from playbook-triggered attempts by a dedicated marker, without requiring a new database migration.

#### Scenario: Test attempts are queryable independently of playbook attempts
- **WHEN** the most recent test result for a provider is looked up
- **THEN** it SHALL be distinguishable from playbook-triggered delivery attempts for the same provider.

#### Scenario: No schema change is required
- **WHEN** this spec is implemented
- **THEN** it SHALL reuse the existing `notification_delivery_attempts` columns and SHALL NOT require a new migration to support Configured/Tested/Ready display or manual test recording.

### Requirement: No Production Enablement Is Introduced By This Spec
This spec SHALL NOT introduce Active/Inactive provider toggles, playbook executor changes, notification-skipping behavior, or delivery-history dashboards.

#### Scenario: Passing a test does not change playbook behavior
- **WHEN** a provider's manual test passes and it becomes Ready
- **THEN** no playbook step behavior, execution routing, or automatic enablement SHALL change as a result — Ready is a display state only in this spec.

#### Scenario: Later child specs own enablement and enforcement
- **WHEN** provider Active/Inactive state or playbook enforcement is discussed
- **THEN** it SHALL be understood as scoped to `soar-notification-provider-active-controls` and `soar-playbook-notification-enforcement`, not this spec.

### Requirement: This Spec Introduces No Runtime Or External Effects By Itself
Creating this spec SHALL NOT implement code, modify tests, or contact any real Slack, Teams, Email, or Webhook endpoint.

#### Scenario: Spec creation sends no notifications
- **WHEN** this spec document is created and reviewed
- **THEN** no real notification of any kind SHALL be sent, and no application source file or test SHALL be modified.
