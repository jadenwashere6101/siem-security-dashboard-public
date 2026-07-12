## ADDED Requirements

### Requirement: Canonical telemetry source identities are authoritative
The system SHALL define and reuse the following exact normalized identities: Honeypot `("honeypot", "honeypot")`, Bank App `("bank_app", "custom")`, pfSense `("pfsense", "firewall")`, NGINX `("nginx", "web_log")`, Azure Application Insights `("azure_insights", "cloud_api")`, and OpenTelemetry `("opentelemetry", "telemetry")`. Matching SHALL be exact after existing normalization; unknown, blank, mismatched, and differently-cased pairs SHALL be unsupported rather than guessed or coerced by the detection layer.

#### Scenario: Canonical identity is recognized
- **WHEN** a normalized event carries one of the six exact authoritative source pairs
- **THEN** rule applicability evaluates it using that canonical identity

#### Scenario: Unknown or mismatched identity fails closed
- **WHEN** an event carries an unknown source, unknown source type, blank value, or a non-authoritative pairing of known values
- **THEN** no base detector treats that identity as supported

### Requirement: Every base detector has explicit source applicability
The system SHALL maintain one centralized applicability definition covering every current base detector, including its classification and exact allowed source pairs. Pairs not listed for a detector SHALL be unsupported.

The authoritative matrix SHALL be:

| Base detector | Classification | Allowed `(source, source_type)` pairs |
|---|---|---|
| `failed_login_threshold` | canonical multi-source authentication | `bank_app/custom`, `azure_insights/cloud_api`, `nginx/web_log`, `opentelemetry/telemetry` |
| `port_scan_threshold` | canonical legacy/custom telemetry | `bank_app/custom` |
| `password_spraying_threshold` | canonical multi-source authentication | `bank_app/custom`, `azure_insights/cloud_api` |
| `http_error_threshold` | canonical multi-source application/web | `honeypot/honeypot`, `nginx/web_log`, `azure_insights/cloud_api`, `opentelemetry/telemetry` |
| `application_exception_threshold` | canonical multi-source application | `azure_insights/cloud_api`, `opentelemetry/telemetry` |
| `high_request_rate_threshold` | partially source-aware becoming explicit | `nginx/web_log`, `opentelemetry/telemetry` |
| `successful_login_after_spray` | canonical multi-source authentication sequence | `bank_app/custom`, `azure_insights/cloud_api` |
| `honeypot_env_probe_threshold` | source-specific | `honeypot/honeypot` |
| `honeypot_admin_probe_threshold` | source-specific | `honeypot/honeypot` |
| `honeypot_scanner_detected` | source-specific | `honeypot/honeypot` |
| `honeypot_credential_stuffing_threshold` | source-specific | `honeypot/honeypot` |
| `pfsense_firewall_repeated_deny` | source-specific | `pfsense/firewall` |
| `pfsense_firewall_port_scan` | source-specific | `pfsense/firewall` |
| `pfsense_firewall_noisy_source` | source-specific | `pfsense/firewall` |
| `pfsense_firewall_suspicious_allow` | source-specific | `pfsense/firewall` |

#### Scenario: Inventory is complete
- **WHEN** the configured base-rule inventory is compared with the applicability definition
- **THEN** every base rule appears exactly once and has at least one exact allowed source pair

#### Scenario: Unlisted combination is unsupported
- **WHEN** a canonical source pair is not listed for a particular detector
- **THEN** that pair cannot execute or contribute to that detector

### Requirement: Applicability is enforced before detector execution
The ingest orchestrator SHALL evaluate the detector's effective `active` state and exact source applicability before invoking detector logic. An inactive or unsupported detector invocation SHALL return no alerts and SHALL not execute the detector's historical aggregation query.

#### Scenario: Unsupported source does not execute rule
- **WHEN** an event type could route to a detector but its source pair is not applicable
- **THEN** the detector is skipped before historical evaluation and creates no alert

#### Scenario: Supported source executes rule
- **WHEN** an active detector receives an event with an allowed source pair and relevant event type
- **THEN** the detector evaluates that source pair using its existing effective parameters

### Requirement: Historical aggregation is isolated by exact source identity
Every base detector's event queries, including threshold, distinct-value, temporal join, location/evidence lookup, and related historical selection, SHALL constrain rows to the same exact allowed `(source, source_type)` pair being evaluated. One allowed source SHALL NOT contribute events to another allowed source's threshold or sequence.

#### Scenario: Same IP across supported sources remains isolated
- **WHEN** events for the same source IP are split across two source pairs that are both supported by a detector
- **THEN** neither source pair reaches the threshold using the other pair's events

#### Scenario: Unsupported history cannot contribute
- **WHEN** an unknown or unsupported source has matching event types inside a detector window
- **THEN** those rows do not affect counts, distinct values, temporal joins, evidence, or alert creation

#### Scenario: Authentication sequence stays within one source
- **WHEN** failed-login evidence exists in one authentication source and a successful login exists in another
- **THEN** `successful_login_after_spray` does not combine them into a sequence alert

### Requirement: Base alerts retain truthful source evidence
A base detector SHALL create alerts only for the exact source pair it evaluated, SHALL write that pair to `alerts.source` and `alerts.source_type`, and SHALL derive representative evidence from rows constrained to that pair. A detector invocation SHALL not create alerts for unrelated qualifying IP groups discovered by a global scan.

#### Scenario: Alert attribution matches contributing events
- **WHEN** a supported source pair independently meets a detector threshold
- **THEN** the created alert source fields match the contributing event rows

#### Scenario: Current event cannot misattribute another aggregate
- **WHEN** ingestion of one source causes evaluation while qualifying history exists for another source or IP
- **THEN** no alert is created with the current event's source attached to the unrelated aggregate

### Requirement: Active state disables base detector execution
The effective `detection_config.active` value SHALL be enforced for all base detectors. `active=false` SHALL prevent dispatch, historical aggregation, and alert creation while leaving event ingestion, other detectors, correlation over already-existing eligible alerts, and stored global parameters unchanged.

#### Scenario: Inactive rule creates no alert
- **WHEN** a base detector has effective `active=false` and otherwise qualifying supported events are ingested
- **THEN** the events are stored but that detector performs no aggregation and creates no alert

#### Scenario: Re-enabled rule uses retained global parameters
- **WHEN** an inactive rule with global parameter overrides is set back to active
- **THEN** subsequent supported events use those retained effective threshold and window values

### Requirement: Global runtime overrides remain compatible
Threshold and window parameters SHALL remain global per `rule_id`, retain current validation and fallback behavior, and SHALL not gain per-source values in this change. Source applicability SHALL be code-owned metadata rather than mutable `detection_config.parameters`.

#### Scenario: Existing parameter override remains effective
- **WHEN** a supported active rule has a valid existing global threshold or window override
- **THEN** every allowed source pair uses that effective override while keeping its aggregation isolated

#### Scenario: Applicability cannot be edited as a parameter
- **WHEN** a caller attempts to submit source coverage inside runtime parameters
- **THEN** existing unknown-parameter validation rejects it

### Requirement: Detection Rules API exposes and updates accurate rule state
The super-admin Detection Rules read API SHALL return effective `active` and deterministic applicable-source metadata for every base rule. The update API SHALL accept a validated boolean `active` alongside parameters, persist it in the existing `detection_config` row, preserve omitted current values, and audit old/new active and parameter changes. Applicability metadata SHALL be read-only.

#### Scenario: Rule response shows source coverage
- **WHEN** a super admin lists detection rules
- **THEN** every rule includes effective active state, classification, and exact applicable source/source-type pairs matching the centralized contract

#### Scenario: Super admin disables rule
- **WHEN** a super admin patches a rule with `active=false`
- **THEN** the existing configuration row stores the state and the audit record identifies the active-state change

#### Scenario: Coverage mutation is rejected
- **WHEN** a caller attempts to modify applicable sources through the Detection Rules API
- **THEN** the API rejects the unsupported mutable field and does not alter coverage

### Requirement: Detection Rules UI presents active state and applicable sources
The Detection Rules panel SHALL show effective active/inactive state and readable applicable-source coverage for every rule, allow a super admin to save an active-state change through the existing editing flow, and preserve current threshold/window editing behavior. The presentation SHALL remain usable in the dark theme, keyboard accessible, and explicit when a rule is inactive.

#### Scenario: Source coverage is visible
- **WHEN** Detection Rules data loads successfully
- **THEN** each rule displays all authoritative applicable sources returned by the API without implying per-source thresholds

#### Scenario: Active state is editable and accessible
- **WHEN** a super admin changes and saves a rule's active state using keyboard or pointer input
- **THEN** the UI sends the boolean state, reloads effective data, and visibly communicates the resulting state

### Requirement: Existing cross-source correlation remains intentional
Generic and targeted correlation rules SHALL continue to evaluate accurately attributed alerts using their existing cross-source requirements, windows, order, and duplicate suppression. The base-rule applicability contract SHALL not restrict correlation queries to one source when the correlation rule intentionally requires multiple sources.

#### Scenario: Generic multi-source correlation still works
- **WHEN** independently source-isolated base alerts for the same IP satisfy the existing distinct-type and distinct-known-source requirements
- **THEN** `correlated_activity` is created as before

#### Scenario: Targeted source pattern still works
- **WHEN** accurately attributed alerts satisfy `web_to_app_attack_pattern` or `cloud_app_error_pattern`
- **THEN** the targeted correlation matches the existing required source groups

#### Scenario: Mixed raw events do not manufacture correlation inputs
- **WHEN** raw events from different sources would previously have combined into a misattributed base alert
- **THEN** no false base alert is created for correlation to consume
