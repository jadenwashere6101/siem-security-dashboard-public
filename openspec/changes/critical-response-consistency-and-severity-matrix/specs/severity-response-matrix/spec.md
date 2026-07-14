## ADDED Requirements

### Requirement: Read-only Severity & Response Matrix API
The system SHALL expose a read-only backend endpoint that composes severity definitions, per-detection default/maximum severity, incident/notification/response behavior, and current notification-policy destinations from their authoritative sources (`engines/detection_config.py`, the correlation/detection engine severities, `core/playbook_store` seeded definitions, and the effective `notification_policy`), rather than a separately maintained data model.

#### Scenario: Matrix API returns composed, live data
- **WHEN** an authenticated `super_admin` or `analyst` requests `GET /api/severity-response-matrix`
- **THEN** the response SHALL include the four severity definitions from `critical-alert-severity-contract`, and one row per active detection/correlation rule reflecting its current default severity, maximum reachable severity, whether it creates an incident, its notification behavior, and its response/playbook behavior, sourced from live configuration rather than a hardcoded frontend copy.

#### Scenario: Matrix reflects a severity change without a frontend deploy
- **WHEN** a detection rule's severity or a playbook's trigger/steps changes in the backend (e.g., the `web_to_app_attack_pattern` reclassification in this change)
- **THEN** the next `GET /api/severity-response-matrix` response SHALL reflect the new value without requiring any frontend code change.

#### Scenario: Rules that cannot reach Critical are labeled explicitly
- **WHEN** the matrix includes a detection rule whose maximum severity is below Critical (e.g., `password_spraying_threshold`)
- **THEN** its `maximum_severity` field SHALL be its actual ceiling (not Critical), and the frontend contract SHALL make this explicit rather than omitting or implying Critical support.

### Requirement: Each detection row includes a backend-authored Why explanation
Every row in the matrix SHALL include a one-sentence, analyst-facing `why` field explaining why that detection's maximum severity is appropriate, authored once in the same backend module that defines the rule's severity and read live by the frontend — not composed, duplicated, or overridden in React.

#### Scenario: Why field is present and sourced from the backend contract
- **WHEN** the matrix API returns a row for `port_scan_threshold`, `pfsense_firewall_repeated_deny`, `successful_login_after_spray`, or `web_to_app_attack_pattern`
- **THEN** each row SHALL include a non-empty `why` string consistent with its severity (for example: Port Scan/High → "Internet reconnaissance alone does not prove compromise."; Repeated Deny/High → "Blocked activity indicates malicious intent but no successful access."; Successful Login After Spray/Critical → "Successful authentication after coordinated credential attacks is a likely-compromise indicator."; Web-to-App Attack Pattern/High → "Correlated attack-chain evidence without proof of successful compromise.").

#### Scenario: Why text changes only when the backend contract changes
- **WHEN** the frontend renders the `Why` column
- **THEN** it SHALL render the `why` string returned by the matrix API verbatim, with no frontend-side text authored, templated, or hardcoded as a fallback or override.

### Requirement: Critical is not equated with confirmed compromise
The severity definitions and every per-rule `why` explanation SHALL be worded so that Critical is understood as the highest-confidence attack-chain or likely-compromise signal requiring immediate human review, and SHALL NOT state or imply that Critical means confirmed compromise; confirmed compromise SHALL be described as a conclusion that generally requires analyst validation or evidence beyond telemetry, not a state the detection pipeline itself asserts.

#### Scenario: Critical definition text is available and correctly worded
- **WHEN** the matrix API's severity-definitions payload is inspected for the Critical entry
- **THEN** its text SHALL match the D1 definition in `design.md` and SHALL NOT contain or imply the phrase "confirmed compromise" as something Critical alone establishes.

#### Scenario: Even the strongest Critical rule is worded as an indicator
- **WHEN** the matrix API's row for `successful_login_after_spray` (the system's only Critical-severity rule) is inspected
- **THEN** its `why` field SHALL describe it as a "likely-compromise indicator" (or equivalent evidentiary framing), not as confirmed compromise.

### Requirement: Matrix API is read-only and RBAC-scoped
The matrix endpoint SHALL NOT accept writes in this version, and SHALL be accessible only to authenticated users with `super_admin` or `analyst` roles.

#### Scenario: No write endpoint exists
- **WHEN** the severity-response-matrix API surface is reviewed
- **THEN** it SHALL expose only `GET` access; no `POST`/`PUT`/`PATCH`/`DELETE` method SHALL be defined for it in this version.

#### Scenario: Unauthorized role is denied
- **WHEN** a request to `GET /api/severity-response-matrix` is made by an authenticated user whose role is neither `super_admin` nor `analyst`, or by an unauthenticated caller
- **THEN** the endpoint SHALL deny the request consistent with the existing RBAC pattern used by other analyst-facing read endpoints.

### Requirement: Severity & Response Matrix frontend workspace
The frontend SHALL provide one read-only workspace, registered in `sectionsConfig.js`, that renders the matrix API's severity definitions and per-detection table without maintaining a second, independently-authored copy of severity or response policy in React.

#### Scenario: Workspace renders severity definitions and detection table
- **WHEN** an analyst or super_admin opens the Severity & Response Matrix workspace
- **THEN** it SHALL display, per severity level, the definition, analyst expectation, incident behavior/priority, Slack eligibility/timing, approval requirement, and containment behavior, plus a detection-level table with columns Detection, Default severity, Escalation conditions, Maximum severity, Creates incident, Notification behavior, Response/playbook behavior, and Why — all values fetched from the matrix API.

#### Scenario: Workspace has no editing controls
- **WHEN** the Severity & Response Matrix workspace is rendered
- **THEN** it SHALL NOT present any control that writes severity, routing, playbook, or notification-policy configuration; configuration changes remain in the existing Notification Policy and Runtime Configurables (Detection Rules) workspaces, which the matrix workspace links to.
- **AND** it SHALL display a short, explicit statement that the page explains current system behavior and is not a configuration interface, directing analysts who want to change behavior to Detection Rules, Runtime Configurables, or Notification Policy.

### Requirement: Matrix answers common analyst operational questions
The workspace SHALL be usable as an operational reference such that, for any listed detection, an analyst can determine — without inspecting detector code — why it is at its current severity rather than a higher one, what causes it to escalate, what response is expected, whether it creates an incident, whether Slack will notify, and whether containment requires approval.

#### Scenario: A single row answers the standard analyst questions
- **WHEN** an analyst reads one row of the detection table for a rule such as `web_to_app_attack_pattern`
- **THEN** the row's `Default severity`, `Escalation conditions`, `Maximum severity`, `Why`, `Creates incident`, `Notification behavior`, and `Response/playbook behavior` fields together SHALL answer, without further lookup: why this rule is not Critical, what would cause it to escalate, whether it creates an incident, whether Slack notifies, and whether containment requires approval.

#### Scenario: Workspace is visible to analysts, not just super_admin
- **WHEN** a user with the `analyst` role opens the sidebar
- **THEN** the Severity & Response Matrix section SHALL be visible and navigable, consistent with other analyst-facing read surfaces gated by `canTakeAlertActions`.

#### Scenario: Workspace is accessible and narrow-layout friendly
- **WHEN** the Severity & Response Matrix workspace is rendered at a narrow viewport width or evaluated with accessibility tooling
- **THEN** the severity definitions and detection table SHALL remain usable (e.g., via responsive layout or horizontal scroll containment for the table) and SHALL expose accessible roles/labels consistent with the project's existing dark-theme accessibility conventions.
