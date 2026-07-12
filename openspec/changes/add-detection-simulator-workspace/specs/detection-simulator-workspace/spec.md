## ADDED Requirements

### Requirement: Zero durable production writes
The Detection Simulator SHALL execute the production ingest, detection, MITRE-mapping, and playbook/response-selection pipeline inside one database transaction that is unconditionally rolled back, and SHALL NOT allow any row to remain committed in `events`, `alerts`, `playbook_executions`, `soar_response_decisions`, `response_actions_queue`, `incidents`, `incident_alerts`, or `audit_log` as a result of a simulation run, including when the run raises an unhandled exception. The simulator SHALL NOT call `core/audit_helpers.log_audit_event` or otherwise write to `audit_log` for any reason, including a record of the simulation request itself, because that table is written through its own independently-committing connection and is not protected by the simulation's rollback boundary.

#### Scenario: Successful simulation leaves no durable rows
- **WHEN** an authorized analyst runs a simulation that would, on the real `/ingest` path, produce an alert and a matched playbook execution
- **THEN** the response describes the alert preview and matched playbook, and no row is added to `events`, `alerts`, `playbook_executions`, `soar_response_decisions`, `response_actions_queue`, `incidents`, `incident_alerts`, or `audit_log`

#### Scenario: Mid-pipeline failure still rolls back
- **WHEN** an unexpected exception occurs after the simulated event has been inserted within the simulation transaction but before the response is built
- **THEN** the transaction is rolled back before the request completes and no row is added to any table listed above

#### Scenario: Simulation never invokes the production ingest route
- **WHEN** the simulation endpoint processes a request
- **THEN** it calls engine-layer functions directly and does not call the `/ingest`, `/ingest/honeypot`, or other production ingest route handlers

#### Scenario: No audit trail row is ever written for a simulation
- **WHEN** any simulation request completes, succeeds, fails, or raises an exception, for any source, rule, or input
- **THEN** no row is added to `audit_log`, and no code path in the simulator calls `log_audit_event`

### Requirement: Reuse of production pipeline logic without duplication
The Detection Simulator SHALL evaluate existing detection rules by calling the same parser, normalizer, detection-applicability, detection-evaluation, threshold/window, alert-generation, MITRE-mapping, and playbook-trigger-matching functions used by the production `/ingest` path, and SHALL NOT maintain a separate reimplementation of threshold, window, or rule-matching logic for existing rules.

#### Scenario: Detection result matches what production would produce
- **WHEN** a simulated event and its supporting simulated event history would satisfy an existing detector's threshold within its configured window
- **THEN** the simulator reports the alert exactly as the production detector's query would report it, using the same rule configuration, thresholds, and windows

#### Scenario: Rule configuration changes apply to simulation immediately
- **WHEN** a detection rule's threshold, window, or active state is changed through the existing detection-rule configuration path
- **THEN** the simulator reflects the updated configuration on its next run without any simulator-specific configuration change

### Requirement: Version 1 supports existing rules only
The Detection Simulator SHALL support selection only from existing, currently-configured production detection rules in Version 1, and SHALL NOT accept custom rule definitions, Python code, or SQL text as simulation input.

#### Scenario: Rule selector lists existing rules
- **WHEN** an authorized analyst opens the rule selector
- **THEN** it lists only rules present in the production detection-rule configuration, using their existing identifiers and applicability metadata

#### Scenario: Custom rule input is rejected
- **WHEN** a request to the simulation endpoint includes a custom rule definition, Python source, or SQL text instead of an existing rule identifier
- **THEN** the endpoint rejects the request without executing it

### Requirement: Simulation endpoint authentication and authorization
The Detection Simulator API SHALL require an authenticated session with the analyst or super-admin role, matching the existing analyst-or-super-admin read-mostly workspace boundary.

#### Scenario: Authorized analyst can simulate
- **WHEN** an authenticated analyst or super administrator submits a simulation request
- **THEN** the endpoint processes the request and returns a simulation result

#### Scenario: Unauthenticated request is rejected
- **WHEN** a request has no valid authenticated session
- **THEN** the endpoint rejects the request using existing authentication behavior without executing any pipeline stage

#### Scenario: Insufficient role is rejected
- **WHEN** an authenticated user without the analyst or super-admin role submits a simulation request
- **THEN** the endpoint enforces the existing role restriction and does not execute any pipeline stage

### Requirement: Supported simulation input
The Detection Simulator SHALL accept one or more pasted raw log lines or pasted JSON events, an explicit source selection from the existing canonical source inventory, and an existing detection rule selection, per simulation request.

#### Scenario: Raw log line input
- **WHEN** an analyst pastes one or more raw log lines and selects a source whose adapter parses that raw format
- **THEN** the simulator runs the matching production parser against the pasted text

#### Scenario: JSON event input
- **WHEN** an analyst pastes one or more JSON events
- **THEN** the simulator runs the matching production normalizer against the parsed JSON

#### Scenario: Unparseable input is reported, not silently dropped
- **WHEN** pasted input cannot be parsed by the selected source's parser
- **THEN** the simulation response reports a parser-stage failure with the parser's own failure reason and does not proceed to later pipeline stages for that input

#### Scenario: Unsupported source/rule combination
- **WHEN** an analyst selects a detection rule that is not applicable to the selected source, per the existing detection-applicability registry
- **THEN** the simulation response reports the rule as not applicable to the selected source without executing that rule's detector

### Requirement: External API isolation during simulation
The Detection Simulator SHALL NOT issue live calls to the production IP-reputation or IP-geolocation third-party APIs during a simulation run, and SHALL use a clearly labeled simulated/stubbed result for those enrichment fields instead.

#### Scenario: Reputation lookup is stubbed
- **WHEN** a simulation run reaches a stage that would call the production reputation lookup
- **THEN** the response includes a stubbed reputation value explicitly labeled as simulated, and no outbound call is made to the real third-party reputation API

#### Scenario: Geolocation lookup is stubbed
- **WHEN** a simulation run reaches a stage that would call the production geolocation lookup
- **THEN** the response includes a stubbed location value explicitly labeled as simulated, and no outbound call is made to the real third-party geolocation API

### Requirement: SOAR and playbook preview without execution
The Detection Simulator SHALL preview matched playbooks, selected response actions, and approval requirements for a simulated alert using the existing playbook-matching and response-selection logic, and SHALL NOT enqueue a response-action queue entry, create a durable playbook execution, or invoke any external integration adapter (Slack, Teams, email, webhook, firewall).

#### Scenario: Matched playbook is previewed
- **WHEN** a simulated alert's attributes satisfy an existing enabled playbook's trigger configuration
- **THEN** the response identifies the matched playbook and its selected response action without creating a playbook execution row or invoking any integration adapter

#### Scenario: No playbook match is reported explicitly
- **WHEN** no enabled playbook's trigger configuration matches the simulated alert
- **THEN** the response explicitly reports no playbook match rather than omitting the SOAR preview section

#### Scenario: Approval requirement is surfaced without creating an approval
- **WHEN** a matched playbook's step configuration requires approval
- **THEN** the response indicates approval would be required and SHALL NOT create an approval record

### Requirement: Pipeline-stage result reporting
The Detection Simulator response SHALL report a per-stage result for Parser, Normalized Event, Detection Applicability, Detection Evaluation, Threshold/Window Evaluation, Alert Preview, MITRE Mapping, and SOAR Preview, each marked as succeeded, skipped, or failed.

#### Scenario: Full pipeline success
- **WHEN** a pasted event parses successfully, normalizes successfully, is applicable to a selected rule, and satisfies that rule's threshold within its window
- **THEN** every stage from Parser through SOAR Preview is marked succeeded, and the response includes each stage's output

#### Scenario: Early-stage failure skips downstream stages
- **WHEN** the Parser stage fails
- **THEN** Normalized Event through SOAR Preview stages are marked skipped, each with a reason referencing the upstream failure

#### Scenario: Detection Applicability stage explicitly fails closed
- **WHEN** the selected rule is not applicable to the selected source
- **THEN** the Detection Applicability stage is marked failed with that reason, and Detection Evaluation through SOAR Preview are marked skipped

### Requirement: Detection reasoning and near-miss explainability
The Detection Simulator response SHALL explain why a detection rule did or did not produce an alert, including, at minimum, the observed count or condition value compared against the rule's configured threshold when the rule did not fire due to an unmet threshold, and whether an existing open alert suppressed alert creation via the production dedup check.

#### Scenario: Threshold not met is explained with observed value
- **WHEN** a rule's threshold is not met by the simulated event and any qualifying real historical events within the rule's window
- **THEN** the response reports the observed count or condition value and the configured threshold, without creating a real alert

#### Scenario: Existing open alert suppression is surfaced
- **WHEN** a simulated event would otherwise satisfy a rule's threshold but the source IP already has a real open alert of that alert type
- **THEN** the response explicitly reports that alert creation was suppressed by an existing open alert, rather than reporting a plain non-match

#### Scenario: Near-miss evidence never runs on, or alters, the production ingest path
- **WHEN** any event is ingested through the real `/ingest` path
- **THEN** no detector is ever invoked with a threshold other than its real configured value, `engines/detection_engine.py` and `engines/correlation_engine.py` contain no simulator-specific branching, and the set of alerts created and their field values are unaffected by the existence of the Detection Simulator

### Requirement: Disclosure of real production history influence
The Detection Simulator response SHALL disclose when its detection or dedup result was influenced by real, already-committed production events or alerts for the selected source or IP, rather than presenting the result as based solely on the pasted input.

#### Scenario: Result blended with real history is disclosed
- **WHEN** a rule's threshold evaluation counts real, already-committed events in addition to the pasted simulated event within the same source and time window
- **THEN** the response indicates that real production history contributed to the result

### Requirement: Detection Simulator sidebar workspace
The frontend SHALL add a "Detection Simulator" workspace to the sidebar navigation, accessible to users with the analyst or super-admin role, containing a source selector, a raw log/JSON paste input, an existing-rule selector, and a Run Simulation action.

#### Scenario: Workspace visible to authorized roles
- **WHEN** an authenticated analyst or super administrator views the sidebar
- **THEN** Detection Simulator is present and selectable

#### Scenario: Workspace hidden or blocked for unauthorized roles
- **WHEN** an authenticated user without the analyst or super-admin role views the application
- **THEN** Detection Simulator is not accessible, consistent with the endpoint's role enforcement

#### Scenario: Run Simulation submits the current input
- **WHEN** an analyst selects a source, pastes input, selects an existing rule, and activates Run Simulation
- **THEN** the frontend submits exactly that source, input, and rule selection to the simulation endpoint and renders the returned per-stage results

### Requirement: Pipeline visualization matches production stage order
The Detection Simulator workspace SHALL render a visual representation of the pipeline stages in the exact order Raw Input, Parser, Normalized Event, Detection Applicability, Detection Evaluation, Threshold/Window Evaluation, Alert Preview, MITRE Mapping, SOAR Preview, with each stage visually distinguishing succeeded, skipped, and failed states.

#### Scenario: Stage order matches specification
- **WHEN** a simulation result is rendered
- **THEN** the visualized stage order is exactly Raw Input, Parser, Normalized Event, Detection Applicability, Detection Evaluation, Threshold/Window Evaluation, Alert Preview, MITRE Mapping, SOAR Preview

#### Scenario: Stage state is visually distinguishable
- **WHEN** a stage is marked succeeded, skipped, or failed in the response
- **THEN** the workspace renders a visually and programmatically distinguishable indicator for that state, including an accessible text label

### Requirement: No production data mutation from the workspace
The Detection Simulator workspace SHALL NOT create, modify, or delete any production event, alert, incident, approval, playbook execution, response-action queue entry, or audit record as a result of any workspace interaction.

#### Scenario: Repeated simulation runs do not accumulate state
- **WHEN** an analyst runs multiple simulations in sequence, including simulations of the same input
- **THEN** no cumulative production data results from any of the runs, and each run's dedup/history disclosure (per the Disclosure requirement) reflects only real production data, never prior simulation runs
