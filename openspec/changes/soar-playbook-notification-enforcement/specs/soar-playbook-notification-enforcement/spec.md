## ADDED Requirements

### Requirement: Provider Active Enforcement For Notification Steps
The playbook executor SHALL check provider Active state before executing Slack, Teams, Email, or Webhook notification steps.

#### Scenario: Active Slack notification attempts delivery normally
- **GIVEN** Slack is Active
- **WHEN** a playbook runs a `notify_slack` step
- **THEN** the executor SHALL use the existing Slack adapter path and preserve existing env guards, fail-closed behavior, rate limits, delivery logging, and outcome logging.

#### Scenario: Active Teams notification attempts delivery normally
- **GIVEN** Teams is Active
- **WHEN** a playbook runs a `notify_teams` step
- **THEN** the executor SHALL use the existing Teams adapter path and preserve existing env guards, fail-closed behavior, rate limits, delivery logging, and outcome logging.

#### Scenario: Active Email notification attempts delivery normally
- **GIVEN** Email is Active
- **WHEN** a playbook runs a `notify_email` step
- **THEN** the executor SHALL use the existing Email adapter path and preserve existing env guards, fail-closed behavior, rate limits, delivery logging, and outcome logging.

#### Scenario: Active Webhook notification attempts delivery normally
- **GIVEN** Webhook is Active
- **WHEN** a playbook runs a `notify_webhook` step
- **THEN** the executor SHALL use the existing Webhook adapter path and preserve existing env guards, fail-closed behavior, rate limits, delivery logging, and outcome logging.

### Requirement: Inactive Provider Policy Skip
The playbook executor SHALL skip notification steps for Inactive providers without attempting external delivery.

#### Scenario: Inactive provider is skipped by policy
- **GIVEN** a provider is Inactive
- **WHEN** a playbook runs the matching notification step
- **THEN** the executor SHALL NOT call the provider adapter delivery path
- **AND** SHALL record the step as skipped by policy
- **AND** SHALL NOT mark the notification as Delivered.

#### Scenario: Inactive provider is not fake success
- **GIVEN** a provider is Inactive
- **WHEN** the matching notification step is skipped
- **THEN** the step and delivery evidence SHALL distinguish skipped-by-policy from success.

#### Scenario: Inactive provider is not system failure
- **GIVEN** a provider is Inactive
- **WHEN** the matching notification step is skipped
- **THEN** the executor SHALL NOT classify the skip as an adapter failure, timeout, credential failure, or system exception.

#### Scenario: Inactive provider does not retry endlessly
- **GIVEN** a provider is Inactive
- **WHEN** the matching notification step is skipped
- **THEN** the executor SHALL NOT create a retry loop for that notification step.

#### Scenario: Unrelated later steps continue
- **GIVEN** a provider is Inactive
- **AND** a playbook has unrelated steps after the skipped notification step
- **WHEN** the playbook does not explicitly require the notification to block later steps
- **THEN** the executor SHALL continue processing unrelated later steps.

### Requirement: Policy Read Failure Fails Closed
The playbook executor SHALL avoid external delivery when provider Active state cannot be read.

#### Scenario: Provider Active state cannot be read
- **GIVEN** provider Active-state storage is unavailable or unreadable
- **WHEN** a notification step is about to run
- **THEN** the executor SHALL NOT attempt provider delivery
- **AND** SHALL record a policy-read-failure outcome distinct from Inactive and delivery failure.

#### Scenario: Policy read failure is operator visible
- **GIVEN** provider Active state cannot be read
- **WHEN** the executor records the step result
- **THEN** the result SHALL include a safe reason such as `provider_policy_unavailable` without secret values.

### Requirement: Skipped-By-Policy Evidence
The system SHALL record skipped-by-policy evidence for notification steps without overloading Delivered, success, or adapter failure.

#### Scenario: Skipped policy outcome is recorded
- **GIVEN** a notification step is skipped because the provider is Inactive
- **WHEN** the execution is persisted
- **THEN** the playbook step log SHALL include skipped-by-policy status, provider, skip reason, and no external execution.

#### Scenario: Response outcome records skipped policy
- **GIVEN** a notification step is skipped because the provider is Inactive
- **WHEN** response outcome events are written for the execution
- **THEN** an outcome event SHALL record the policy skip with `external_executed=false` and without secret values.

#### Scenario: Delivery attempt status is honest
- **GIVEN** the implementation records a notification delivery attempt for an inactive provider
- **WHEN** the row is persisted
- **THEN** its status SHALL be `skipped` or an equivalent non-success value explicitly approved by the implementation
- **AND** it SHALL NOT use `success`, `failed`, `timeout`, or `blocked` to disguise skipped-by-policy.

### Requirement: Provider Active Source
The executor SHALL read provider Active state from the durable backend state created by `soar-notification-provider-active-controls`.

#### Scenario: Missing provider control row is inactive
- **GIVEN** no provider-control row exists for Slack, Teams, Email, or Webhook
- **WHEN** the executor reads Active state for that provider
- **THEN** the provider SHALL be treated as Inactive.

#### Scenario: Firewall is excluded
- **WHEN** the executor processes firewall or `block_ip` steps
- **THEN** this notification Active enforcement SHALL NOT create real firewall execution or real firewall Active/Inactive behavior.

### Requirement: Frontend Execution Visibility
Playbook execution views SHALL display skipped-by-policy notification steps clearly if existing rendering does not already make them clear.

#### Scenario: Timeline shows skipped by policy
- **GIVEN** a playbook execution contains a notification step skipped by policy
- **WHEN** an analyst or super-admin views the execution timeline
- **THEN** the UI SHALL show that the notification was skipped by policy and not delivered.

#### Scenario: No provider toggles added
- **WHEN** this spec is implemented
- **THEN** playbook execution views SHALL NOT add provider Active/Inactive toggles.

### Requirement: Scope Boundaries
This change SHALL NOT add unrelated notification-control or firewall capabilities.

#### Scenario: No manual test send
- **WHEN** this spec is implemented
- **THEN** the system SHALL NOT add manual test-send buttons or endpoints.

#### Scenario: No delivery history dashboard
- **WHEN** this spec is implemented
- **THEN** the system SHALL NOT add a delivery history dashboard.

#### Scenario: Firewall remains simulation-only
- **WHEN** this spec is implemented
- **THEN** no real firewall blocking, API call, subprocess execution, or blocklist mutation path SHALL be added.
