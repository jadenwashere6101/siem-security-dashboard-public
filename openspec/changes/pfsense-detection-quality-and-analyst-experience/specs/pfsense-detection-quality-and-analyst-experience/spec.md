## ADDED Requirements

### Requirement: Port scan detection measures breadth on two axes
The system SHALL measure pfSense port-scan candidate traffic using both distinct destination-port count and distinct destination-host count within the rule's configured time window, and SHALL include both counts in the resulting alert's context.

#### Scenario: Many ports on one host is distinguishable from a sweep
- **WHEN** a source reaches the configured port-count threshold against a single destination host
- **THEN** the alert context reports a high distinct-port count and a distinct-host count of one, distinguishing single-host probing from multi-host sweeping

#### Scenario: Few ports across many hosts is still detected
- **WHEN** a source contacts a small number of distinct ports but across many distinct destination hosts within the window
- **THEN** the system SHALL be able to flag this breadth pattern using the distinct-host count rather than relying on port count alone

### Requirement: Suspicious-allow severity requires repetition or corroborating context
The system SHALL NOT assign `high` severity to a `pfsense_firewall_suspicious_allow` candidate from event count alone unless the event count meets the rule's configured repetition threshold, or the source carries corroborating context (known-bad reputation, or multiple distinct sensitive ports touched within the window).

#### Scenario: Single uncorroborated allow does not force high severity
- **WHEN** exactly one allowed inbound event to a sensitive port occurs for a source with no adverse reputation and no other qualifying context within the window
- **THEN** the resulting alert SHALL NOT be assigned `high` severity solely on that basis

#### Scenario: Repeated or corroborated allow escalates
- **WHEN** allowed inbound events to sensitive ports from one source meet the configured repetition threshold, or the source carries known-bad reputation context, within the window
- **THEN** the resulting alert SHALL be assigned `high` severity

### Requirement: Repeated-deny severity and messaging are direction-aware
The system SHALL treat LAN→WAN denied traffic as a distinct investigative signal from WAN→LAN denied traffic in `pfsense_firewall_repeated_deny` severity and alert messaging, without introducing a new `alert_type` value.

#### Scenario: Outbound repeated deny is distinguishable
- **WHEN** repeated denied traffic originates from an internal host toward external destinations and meets the existing repeated-deny threshold
- **THEN** the alert's message and severity input SHALL reflect the outbound/internal-source context distinctly from inbound WAN-sourced denies

#### Scenario: Inbound repeated deny behavior is unchanged
- **WHEN** repeated denied traffic originates from an external source toward internal destinations
- **THEN** existing repeated-deny severity behavior applies unchanged

### Requirement: Alert suppression persists briefly across closure for an unresolved source
The system SHALL suppress re-creation of a pfSense alert for the same `(source_ip, alert_type)` for a bounded cooldown window after the prior alert for that pair was closed, unless the source meets an explicit escalation-breakout condition.

#### Scenario: Closed alert does not immediately regenerate
- **WHEN** a pfSense alert for a given `(source_ip, alert_type)` is closed and the same underlying condition recurs from the same source within the configured cooldown window
- **THEN** the system SHALL suppress creating a duplicate alert and SHALL make the suppression decision visible in alert/detection context

#### Scenario: Escalation breaks suppression
- **WHEN** a source under an active cooldown subsequently meets a higher-severity condition (e.g., port-scan breadth, known-bad reputation, or suspicious-allow escalation criteria) for a different or elevated alert_type
- **THEN** the system SHALL NOT suppress the new, higher-severity alert

#### Scenario: Cooldown determination does not require a new persisted timestamp
- **WHEN** the system determines whether a prior alert for a `(source_ip, alert_type)` pair was closed within the cooldown window
- **THEN** it SHALL derive the closure time from already-persisted data (e.g., the existing alert-status audit trail) unless an implementation-time review explicitly adopts a new persisted column, which SHALL be documented as a deliberate migration decision rather than assumed silently

### Requirement: Notification urgency is decoupled from alert existence for investigation-only outcomes
The system SHALL route investigation-only (non-containment) pfSense playbook outcomes at a lower notification urgency than containment playbook outcomes, without suppressing the underlying alert, its dashboard visibility, or any containment playbook's existing approval-gated behavior.

#### Scenario: Investigation-only outcome does not page at containment urgency
- **WHEN** a pfSense playbook whose steps do not include an approval-gated containment action (`require_approval` + `block_ip`) completes its `monitor`/`enrich_context` steps
- **THEN** its notification step SHALL NOT use the same urgency/channel behavior as a containment playbook's post-approval notification

#### Scenario: Containment notification timing is unchanged
- **WHEN** a pfSense containment playbook's approval request is approved and `block_ip` executes
- **THEN** the existing post-decision Slack notification behavior SHALL be unchanged by this requirement

### Requirement: Alert investigation context is derivable without new data collection
The system SHALL provide a read-only "why this fired" projection for pfSense alerts using only data already persisted on the alert (including its `context` field), and SHALL NOT require new event or alert fields to populate it.

#### Scenario: Why-fired context reflects stored detection evidence
- **WHEN** an analyst requests investigation context for a pfSense alert
- **THEN** the system SHALL return the alert's detection-specific evidence (e.g., event/port/host counts, first-seen/last-seen, direction, suppression state) already stored on that alert

### Requirement: Detection Health is a small, fixed-shape ranked rule list
The system SHALL provide a read-only Detection Health view scoped to exactly the four pfSense rules in this capability (`pfsense_firewall_repeated_deny`, `pfsense_firewall_port_scan`, `pfsense_firewall_suspicious_allow`, `pfsense_firewall_noisy_source`), computed entirely from already-persisted `alerts` rows, with no new metrics/rollup table. For each rule the view SHALL report exactly: rule name, fired count within a fixed trailing 24-hour window (by `alerts.created_at`), the highest alert severity observed for that rule within the same window, the timestamp of that rule's most recent alert, and — only as specified below — a deterministic status badge. Rows SHALL be ranked by 24-hour fired count descending, ties broken by rule name ascending. The rule name SHALL link to the existing `/admin/detection-rules/<rule_id>` configuration workspace rather than expose any threshold-editing control of its own.

The system SHALL NOT include, as part of Detection Health: charts or graphical trend visualizations, historical trend analytics beyond the fixed 24-hour count, false-positive scoring, AI-generated or heuristic-judgment health assessments, a new rule-management interface, a general analytics dashboard, or any threshold-editing control duplicating `/admin/detection-rules/<rule_id>`.

#### Scenario: Ranked list reflects only the four in-scope rules
- **WHEN** Detection Health is requested
- **THEN** the response SHALL contain exactly one row per pfSense rule in scope, each with rule name, 24-hour fired count, highest observed severity in that window, and last-fired timestamp, and no rows for rules outside this capability's four pfSense rules

#### Scenario: Rule name links to existing configuration workspace
- **WHEN** an analyst selects a rule's name in the Detection Health view
- **THEN** the system SHALL navigate to that rule's existing `/admin/detection-rules/<rule_id>` entry rather than rendering a new threshold-editing surface

#### Scenario: Status badge, if present, uses fixed deterministic thresholds
- **WHEN** a rule's Detection Health row includes a status badge
- **THEN** the badge SHALL be computed solely from that rule's 24-hour fired count using fixed, documented cutoffs — `Noisy` when the count is 20 or more, `Needs Review` when the count is at least 5 and below 20, `Normal` when the count is below 5 — with no reputation, false-positive, or AI-derived input, and no per-rule configurability of these cutoffs

#### Scenario: No chart or trend surface is produced
- **WHEN** Detection Health is implemented
- **THEN** it SHALL NOT render or expose a chart, sparkline, historical trend series, or any visualization beyond the single fixed-window count per rule

### Requirement: Existing SOAR, approval, and queue architecture is preserved
This change SHALL NOT modify the SOAR playbook engine's execution model, the approval-gate mechanism, the frozen response-action queue, ingest-time filtering, or any archived/active spec other than adding this new capability.

#### Scenario: No architectural changes outside detection quality and analyst UX
- **WHEN** this change is implemented later
- **THEN** it SHALL NOT alter `engines/playbook_step_executor.py`'s execution/lease/approval model, `engines/soar_action_worker.py`'s frozen queue behavior, or `engines/pfsense_ingest_filter.py`'s ingest-time retention categories
