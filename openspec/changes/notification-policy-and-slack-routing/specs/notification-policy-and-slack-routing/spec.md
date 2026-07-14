## ADDED Requirements

### Requirement: Notification policy is independent from detection logic
The system SHALL evaluate Slack notification policy after an alert or incident already exists, using the existing object severity and source fields as inputs rather than duplicating detector logic.

#### Scenario: Existing alert severity is the only severity input
- **WHEN** notification policy evaluates whether to send Slack for an alert
- **THEN** it SHALL consume the alert's existing severity value
- **AND** SHALL NOT recompute severity from detector thresholds, rule internals, or custom notification-only logic

#### Scenario: Detection logic remains unchanged by notification policy
- **WHEN** notification policy is enabled, disabled, or reconfigured at runtime
- **THEN** alert creation thresholds, severity assignment, and source attribution SHALL remain unchanged

### Requirement: Runtime notification policy is configurable
The system SHALL expose one runtime-configurable notification policy for Slack delivery that includes enablement, minimum severity, object type switches, format, and bounded source routes.

#### Scenario: Runtime policy exposes required fields
- **WHEN** an operator reads effective notification policy
- **THEN** the policy SHALL include Slack enabled or disabled, minimum notification severity, notify-on-alerts, notify-on-incidents, Slack format, and source route channel labels

#### Scenario: Runtime policy persists beyond a browser session
- **WHEN** an operator updates notification policy
- **THEN** the updated policy SHALL remain effective across browser refreshes and backend process restarts

#### Scenario: Browser-local settings are not the source of truth
- **WHEN** effective notification policy is read or updated
- **THEN** the policy SHALL NOT be sourced solely from frontend localStorage or other per-browser UI settings

#### Scenario: Dedicated durable policy row is authoritative
- **WHEN** effective notification policy is loaded after backend restart or browser refresh
- **THEN** the system SHALL read one authoritative current policy row from the dedicated backend notification-policy store
- **AND** SHALL NOT derive effective policy from secrets, UI-local settings, or hardcoded delivery logic

### Requirement: Notification policy reuses existing runtime configuration architecture where possible
The system SHALL follow the repository's existing backend runtime-configuration approach before introducing a new framework.

#### Scenario: Existing durable runtime configuration is reused when suitable
- **WHEN** implementation finds an existing backend runtime configuration surface that can safely own notification policy
- **THEN** the implementation SHALL reuse that pattern rather than introduce a parallel configuration architecture

#### Scenario: New storage is additive only when required
- **WHEN** no existing durable backend runtime configuration surface can safely own notification policy
- **THEN** the implementation SHALL use the smallest additive storage and API design necessary for runtime policy

#### Scenario: Additive store remains single-purpose
- **WHEN** the dedicated notification-policy store is implemented
- **THEN** it SHALL remain a bounded, single-purpose table for this capability
- **AND** SHALL NOT become a broad generic settings framework

### Requirement: Slack notification scope is bounded
This capability SHALL govern Slack notifications only and SHALL NOT add other notification providers or advanced policy engines.

#### Scenario: Non-Slack providers remain out of scope
- **WHEN** this capability is implemented
- **THEN** it SHALL NOT add Teams, Discord, Email, SMS, PagerDuty, or webhook-editor notification policy behavior

#### Scenario: Advanced policy features remain out of scope
- **WHEN** this capability is implemented
- **THEN** it SHALL NOT add quiet hours, schedules, escalation chains, per-rule notification settings, or arbitrary template editing

### Requirement: Source-based Slack routing is bounded and source-aware
The system SHALL route Slack notifications by the existing alert source family, with two initial source routes: pfSense and honeypot.

#### Scenario: pfSense source routes to the pfSense Slack destination
- **WHEN** notification policy evaluates an alert or incident whose source belongs to the pfSense source family
- **THEN** the Slack notification SHALL use the pfSense route configuration

#### Scenario: Honeypot source routes to the honeypot Slack destination
- **WHEN** notification policy evaluates an alert or incident whose source belongs to the honeypot source family
- **THEN** the Slack notification SHALL use the honeypot route configuration

#### Scenario: Routing does not depend on individual detection rules
- **WHEN** two alerts share the same routed source family but come from different detection rules
- **THEN** notification policy SHALL route them by source family rather than per-rule mappings

#### Scenario: Future sources can extend the same routing model
- **WHEN** a future telemetry source is added after this capability
- **THEN** it SHALL be able to plug into the same source-routing contract without redesigning notification policy fundamentals

### Requirement: Slack route channel names are runtime configurable
The system SHALL treat Slack destination labels for the pfSense and honeypot routes as runtime-configurable policy values rather than hardcoded strings.

#### Scenario: pfSense channel label is configurable
- **WHEN** an operator updates the pfSense Slack route configuration
- **THEN** notification policy SHALL use the configured pfSense channel label rather than a hardcoded default

#### Scenario: Honeypot channel label is configurable
- **WHEN** an operator updates the honeypot Slack route configuration
- **THEN** notification policy SHALL use the configured honeypot channel label rather than a hardcoded default

#### Scenario: Arbitrary channel mapping is not introduced
- **WHEN** route configuration is reviewed
- **THEN** the policy SHALL expose bounded route entries for the supported source families rather than a generic arbitrary mapping engine

#### Scenario: Stored destinations are labels only
- **WHEN** the pfSense or honeypot destination is stored or returned by runtime policy APIs
- **THEN** it SHALL be treated as a validated routing label only
- **AND** SHALL NOT store webhook URLs, credentials, or other Slack secrets

### Requirement: Slack policy respects enablement, severity floor, and object-type toggles
The system SHALL evaluate runtime policy gates before attempting Slack delivery.

#### Scenario: Slack disabled suppresses notification attempts
- **WHEN** Slack notifications are disabled in runtime policy
- **THEN** the system SHALL NOT attempt Slack delivery for alerts or incidents
- **AND** alerts, incidents, playbooks, audit evidence, and UI visibility SHALL remain otherwise unchanged

#### Scenario: Below-minimum severity suppresses notification attempts
- **WHEN** an alert or incident severity is below the configured minimum notification severity
- **THEN** the system SHALL NOT attempt Slack delivery

#### Scenario: Alert notifications can be disabled independently
- **WHEN** notify-on-alerts is disabled and notify-on-incidents remains enabled
- **THEN** alert-created notification attempts SHALL be suppressed while incident-created notification attempts remain eligible

#### Scenario: Incident notifications can be disabled independently
- **WHEN** notify-on-incidents is disabled and notify-on-alerts remains enabled
- **THEN** incident-created notification attempts SHALL be suppressed while alert-created notification attempts remain eligible

### Requirement: Slack formatting is limited to compact and detailed modes
The system SHALL support exactly two Slack notification formats: compact and detailed.

#### Scenario: Compact format stays short
- **WHEN** Slack format is set to compact
- **THEN** the resulting notification SHALL use a short, scan-friendly summary suitable for busy analyst channels

#### Scenario: Detailed format includes existing context when available
- **WHEN** Slack format is set to detailed
- **THEN** the resulting notification SHALL include the compact summary plus available existing context such as severity, rule, source, MITRE, response action, and target context

#### Scenario: No custom template editor exists
- **WHEN** operators configure Slack notification format
- **THEN** they SHALL choose only between compact and detailed and SHALL NOT edit arbitrary message templates

### Requirement: Detailed formatting reuses existing investigation context
Detailed Slack notifications SHALL reuse existing alert or incident context when it is already available and SHALL NOT invent a second enrichment pipeline.

#### Scenario: Existing MITRE and response context is reused
- **WHEN** detailed Slack formatting has access to existing MITRE or response-action context
- **THEN** the notification SHALL reuse that context rather than recompute it through separate notification-only logic

#### Scenario: Missing optional context does not block delivery
- **WHEN** detailed Slack formatting lacks optional context such as MITRE or target fields
- **THEN** the notification SHALL still render safely using the fields that are available

### Requirement: Policy evaluation fails closed when unavailable
The system SHALL avoid Slack delivery when notification policy cannot be read or interpreted safely.

#### Scenario: Policy read failure suppresses Slack delivery
- **WHEN** the runtime notification policy store is unavailable, invalid, or unreadable
- **THEN** the system SHALL NOT attempt Slack delivery

#### Scenario: Policy-unavailable outcome is distinguishable
- **WHEN** Slack delivery is suppressed because notification policy is unavailable
- **THEN** the resulting evidence SHALL distinguish policy-unavailable from disabled, below-severity, or unrouted-source outcomes

### Requirement: Notification policy preserves existing security boundaries
This capability SHALL preserve RBAC, audit logging, redaction, and fail-closed integration safeguards.

#### Scenario: Policy mutation requires elevated permissions
- **WHEN** a user attempts to update runtime notification policy
- **THEN** the system SHALL require the same elevated operator permissions used for comparable runtime configuration changes

#### Scenario: Policy reads and writes are audited safely
- **WHEN** notification policy is read or updated through backend runtime APIs
- **THEN** the system SHALL record audit evidence without logging secrets or webhook values

#### Scenario: Formatted notifications do not expose secrets
- **WHEN** compact or detailed Slack formatting runs
- **THEN** it SHALL NOT include webhook URLs, raw secrets, or unbounded unsafe payload fields
