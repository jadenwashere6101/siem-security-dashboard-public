## ADDED Requirements

### Requirement: Severity definitions
The system SHALL define exactly four alert/incident severities with fixed meanings: Low (expected/background activity, dashboard visibility only), Medium (credible activity requiring analyst review), High (high-confidence malicious activity requiring prompt investigation), and Critical (highest-confidence attack-chain or likely-compromise signal requiring immediate human review). Critical SHALL NOT be described as confirmed compromise in any user-facing text unless the underlying rule's evidence includes an observed successful authentication or equivalent proof.

#### Scenario: Critical definition text does not overstate evidence
- **WHEN** the Critical severity definition is rendered anywhere in the system (matrix UI, API, documentation)
- **THEN** its wording SHALL describe it as the highest-confidence attack-chain or likely-compromise signal requiring immediate human review, and SHALL NOT state or imply confirmed compromise unless the specific rule proves it.

### Requirement: successful_login_after_spray remains Critical
`successful_login_after_spray` SHALL remain severity `critical` because its detection logic requires an observed `successful_login` event correlated against distinct failed-username evidence within the configured window, which constitutes real compromise evidence.

#### Scenario: successful_login_after_spray alert severity
- **WHEN** `_generate_successful_login_after_spray_alerts_core` inserts a new alert
- **THEN** the inserted `severity` column SHALL be `"critical"`.

### Requirement: web_to_app_attack_pattern is High, not Critical
`web_to_app_attack_pattern` SHALL be severity `high`. Its evidence (an nginx error/rate signal correlated with a bank_app failed-login/spray signal from the same source IP within the rule's window) is a credible multi-source attack pattern without confirmed compromise, and therefore does not meet the Critical bar defined in this capability.

#### Scenario: web_to_app_attack_pattern alert severity
- **WHEN** `generate_targeted_correlation_alerts` inserts an alert for the `web_to_app_attack_pattern` rule
- **THEN** the inserted `severity` column SHALL be `"high"`.

#### Scenario: web_to_app_attack_pattern playbook trigger matches the new severity
- **WHEN** the `core-v1-web-to-app-attack-investigation` playbook definition is evaluated against a newly created `web_to_app_attack_pattern` alert
- **THEN** its `trigger_config.min_severity` SHALL be `"high"` (not `"critical"`), so the playbook still matches the alert and still runs `enrich_context`, `monitor`, and `notify_slack` with no `block_ip` or `require_approval` step.

### Requirement: spray_then_success_pattern is a corroborating High-severity signal, not an independent Critical containment trigger
`spray_then_success_pattern` SHALL be severity `high`. Because its detection logic requires `successful_login_after_spray` to already be open for the same source IP, it SHALL NOT independently drive a second approval-gated containment playbook execution for the same evidence; `successful_login_after_spray` remains the sole canonical Critical containment trigger for "spray followed by success" evidence on a given source IP.

#### Scenario: spray_then_success_pattern alert severity
- **WHEN** `generate_targeted_correlation_alerts` inserts an alert for the `spray_then_success_pattern` rule
- **THEN** the inserted `severity` column SHALL be `"high"`.

#### Scenario: spray_then_success_pattern playbook is investigation-only
- **WHEN** the `core-v1-spray-then-success-correlation-investigation` playbook definition is evaluated against a newly created `spray_then_success_pattern` alert
- **THEN** its `trigger_config.min_severity` SHALL be `"high"`, and its steps SHALL be `enrich_context`, `monitor`, `notify_slack` only — it SHALL NOT include `require_approval` or `block_ip`.

#### Scenario: No duplicate containment for the same spray-then-success evidence
- **WHEN** a source IP produces both an open `successful_login_after_spray` alert and a subsequent `spray_then_success_pattern` alert within the correlation window
- **THEN** only the `successful_login_after_spray` alert's playbook (`core-v1-spray-success-response`) SHALL run `require_approval` and `block_ip` for that source IP's spray-then-success evidence; the `spray_then_success_pattern` alert SHALL NOT trigger a second `require_approval`/`block_ip` cycle.

### Requirement: Critical alerts never present a response_action that understates required response
When an alert is inserted with severity `critical`, its `response_action` SHALL be floored to at least `flag_high_priority` — it SHALL NOT be `monitor` — regardless of the reputation-derived value `determine_response_action` would otherwise select. This floor SHALL NOT cause `response_action` to become `block_ip` automatically; `block_ip` remains reachable only through an approved playbook `require_approval` → `block_ip` step sequence.

#### Scenario: Critical alert with low reputation score is not shown as monitor-only
- **WHEN** a Critical-severity alert is inserted for a source IP whose reputation score would otherwise select `response_action = "monitor"`
- **THEN** the inserted `response_action` SHALL be `"flag_high_priority"` instead of `"monitor"`.

#### Scenario: Floor never auto-selects containment
- **WHEN** the Critical response-action floor is applied to any alert
- **THEN** it SHALL NOT set `response_action` to `"block_ip"` under any reputation score — automatic blocking without approval remains disallowed.
