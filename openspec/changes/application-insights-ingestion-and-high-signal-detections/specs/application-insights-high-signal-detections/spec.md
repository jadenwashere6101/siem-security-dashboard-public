## ADDED Requirements

### Requirement: Application-tier authentication-abuse threshold detection
The system SHALL detect repeated 401/403 `AppRequests` responses from the same source IP within a configurable window as `app_insights_unauthorized_access_threshold`, scoped exclusively to the `azure_insights`/`cloud_api` source.

#### Scenario: Threshold rule fires on repeated app-tier authorization failures
- **WHEN** the configured threshold of `unauthorized_access` events from the same source IP occurs within the configured window
- **THEN** an alert of `alert_type = "app_insights_unauthorized_access_threshold"` and `severity = "high"` SHALL be created.

#### Scenario: Rule is scoped only to Application Insights
- **WHEN** `rule_applies_to_source("app_insights_unauthorized_access_threshold", source, source_type)` is evaluated for any source other than `azure_insights`/`cloud_api`
- **THEN** it SHALL return `False` — this rule SHALL NOT apply to `bank_app`, `nginx`, `pfsense`, or `honeypot` telemetry.

#### Scenario: Rule never exceeds High severity on its own
- **WHEN** `app_insights_unauthorized_access_threshold` fires under any configured threshold/window
- **THEN** the created alert's severity SHALL be `"high"`, never `"critical"` — this rule alone SHALL NOT be capable of producing a Critical alert.

### Requirement: Authentication-abuse-and-instability correlation detects attack progression
The system SHALL correlate application-tier authentication-abuse signals with a concurrent application exception spike from the same source IP as `azure_auth_abuse_exception_correlation`, representing corroborated attack-progression evidence rather than an isolated exception.

#### Scenario: Correlation fires only when both signals are present
- **WHEN** a source IP has both an open authentication-abuse signal (`app_insights_unauthorized_access_threshold`, `password_spraying_threshold`, or `failed_login_threshold` for the `azure_insights` source) and an open `application_exception_threshold` alert within the correlation window
- **THEN** an alert of `alert_type = "azure_auth_abuse_exception_correlation"` and `severity = "high"` SHALL be created.

#### Scenario: An isolated exception spike does not trigger this correlation
- **WHEN** `application_exception_threshold` is open for a source IP with no concurrent authentication-abuse signal for that IP
- **THEN** `azure_auth_abuse_exception_correlation` SHALL NOT fire.

#### Scenario: Correlation does not independently escalate to Critical
- **WHEN** `azure_auth_abuse_exception_correlation` fires for a source IP that also has an open `successful_login_after_spray` alert (Critical)
- **THEN** the correlation alert SHALL be created at `severity = "high"` and SHALL link to the same incident as the `successful_login_after_spray` alert via the existing incident-linking path, and SHALL NOT itself trigger a second `require_approval`/`block_ip` playbook cycle or independently set the incident above what `successful_login_after_spray` already established.

### Requirement: Critical severity for Application Insights signals requires corroborated compromise evidence
No detection rule introduced by this change SHALL be capable of producing Critical severity on its own; Critical remains reachable for Application Insights–sourced evidence only through the existing `successful_login_after_spray` path (an observed successful authentication), consistent with the platform's Critical philosophy.

#### Scenario: New rules' maximum severity is High
- **WHEN** the Severity & Response Matrix (once implemented) lists `app_insights_unauthorized_access_threshold` and `azure_auth_abuse_exception_correlation`
- **THEN** both SHALL show `maximum_severity = "high"`, and their `why` explanations SHALL describe why they stop short of Critical (probing/corroborated-attack evidence, not confirmed compromise).

#### Scenario: No new rule bypasses the successful-authentication bar for Critical
- **WHEN** any combination of `app_insights_unauthorized_access_threshold`, `application_exception_threshold`, `AppDependencies`-failure, or `AppAvailabilityResults`-failure signals occurs for a source IP without an observed successful login
- **THEN** no alert produced by this change's rules SHALL be assigned `severity = "critical"`.
