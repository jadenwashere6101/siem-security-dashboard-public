## ADDED Requirements

### Requirement: Read-only source-IP context endpoint
The system SHALL provide a read-only backend endpoint at `GET /source-ip-context?source_ip=<ip>` that returns normalized investigation context for one validated `source_ip`.

#### Scenario: Valid source IP returns context
- **WHEN** an authenticated analyst or super-admin requests `/source-ip-context?source_ip=8.8.8.8`
- **THEN** the system returns HTTP 200 with a JSON object containing `source_ip`, `generated_at`, `limits`, `alerts`, `incidents`, `queue`, `blocklist`, `reputation`, and `playbook_executions`

#### Scenario: Missing source IP is rejected
- **WHEN** an authenticated analyst or super-admin requests `/source-ip-context` without `source_ip`
- **THEN** the system returns HTTP 400 with an error explaining that `source_ip` is required

#### Scenario: Invalid source IP is rejected
- **WHEN** an authenticated analyst or super-admin requests `/source-ip-context?source_ip=not-an-ip`
- **THEN** the system returns HTTP 400 with an error explaining that `source_ip` is invalid

### Requirement: Permission-gated source-IP context
The system SHALL restrict the full source-IP context endpoint to authenticated analyst and super-admin users.

#### Scenario: Unauthenticated request is rejected
- **WHEN** an unauthenticated user requests `/source-ip-context?source_ip=8.8.8.8`
- **THEN** the system returns HTTP 401

#### Scenario: Viewer request is rejected
- **WHEN** an authenticated viewer requests `/source-ip-context?source_ip=8.8.8.8`
- **THEN** the system returns HTTP 403

#### Scenario: Analyst request is allowed
- **WHEN** an authenticated analyst requests `/source-ip-context?source_ip=8.8.8.8`
- **THEN** the system returns HTTP 200 with the normalized source-IP context payload

### Requirement: Preserve distinct status semantics
The source-IP context response MUST preserve existing lifecycle and operational status meanings and MUST NOT expose a fake top-level unified status field.

#### Scenario: Status fields remain scoped
- **WHEN** the response contains alert, incident, queue, and blocklist data
- **THEN** alert lifecycle values appear only under alert records, incident lifecycle values appear only under incident records, queue execution values appear only under queue records, and blocklist tracking values appear only under blocklist records

#### Scenario: No unified source status is returned
- **WHEN** the response is serialized
- **THEN** the top-level object does not contain a `status` field that attempts to summarize the entire source IP

### Requirement: Aggregate existing source-IP context
The endpoint SHALL aggregate existing information for the requested source IP from alerts, incidents, queue activity, blocklist entries, behavioral reputation, external reputation snapshots, and linked playbook executions.

#### Scenario: Alerts are included
- **WHEN** alerts exist with `alerts.source_ip` equal to the requested source IP
- **THEN** the `alerts.recent` collection includes bounded recent alert records with alert ID, type, severity, alert status, message, creation time, response action, response status, source, source type, location fields when available, and reputation snapshot fields when available

#### Scenario: Incidents are included by source IP and linked alerts
- **WHEN** incidents directly use the requested source IP or are linked to alerts for the requested source IP
- **THEN** the `incidents.recent` collection includes bounded recent incident records with incident ID, title, severity, priority, incident status, source IP, assignment, created time, resolved time, and linked alert IDs where available

#### Scenario: Queue activity is included
- **WHEN** response action queue rows exist for the requested source IP
- **THEN** the `queue.recent` collection includes bounded recent queue records with queue ID, alert ID when present, action, queue execution status, retry counts, last error, created time, and updated time

#### Scenario: Blocklist state is included
- **WHEN** blocklist rows exist for the requested source IP
- **THEN** the `blocklist.entries` collection includes matching entries and `blocklist.effective_status` reflects active, expired, inactive, or none using current expiry-aware blocklist semantics

#### Scenario: Playbook executions are included by linked records
- **WHEN** playbook executions are linked to alerts or incidents associated with the requested source IP
- **THEN** the `playbook_executions.recent` collection includes bounded recent execution records with execution ID, playbook ID, alert ID, incident ID, execution status, started time, completed time, and created time

### Requirement: Reputation concepts remain separate
The source-IP context response SHALL return current behavioral reputation separately from historical external reputation snapshots.

#### Scenario: Behavioral reputation is current
- **WHEN** the endpoint calculates source-IP context
- **THEN** `reputation.behavioral` is populated from the existing behavioral reputation scoring logic for the requested source IP

#### Scenario: External reputation remains historical
- **WHEN** matching alerts contain stored external reputation fields
- **THEN** `reputation.external_snapshots` contains bounded recent stored alert reputation snapshots and `reputation.latest_external` identifies the newest available snapshot without implying it is a current live lookup

### Requirement: Bounded response collections
The endpoint SHALL cap recent collections to safe limits and SHALL expose the applied limits in the response.

#### Scenario: Recent collections are capped
- **WHEN** more records exist than the configured caps for alerts, incidents, queue rows, playbook executions, or external reputation snapshots
- **THEN** the endpoint returns only the most recent records up to each cap and includes those cap values in `limits`

#### Scenario: Optional limits are validated
- **WHEN** a request provides a supported limit parameter outside the allowed range
- **THEN** the endpoint either clamps the value to the maximum safe cap or returns HTTP 400 according to the implemented parameter policy

### Requirement: No source-IP context mutations
The source-IP context endpoint SHALL NOT mutate alerts, incidents, queue rows, playbook executions, approvals, blocklist rows, reputation fields, or SOAR state.

#### Scenario: Context read does not change state
- **WHEN** an authenticated analyst or super-admin requests source-IP context
- **THEN** the endpoint performs a read-only aggregation and does not enqueue actions, update lifecycle statuses, create incidents, execute playbooks, update blocklist rows, or write audit-side effects beyond any existing request logging policy

### Requirement: Frontend consumes backend context contract
Frontend source-IP context displays SHALL consume the normalized backend contract rather than recomputing cross-tab joins from unrelated service responses.

#### Scenario: Alert Details uses source-IP context
- **WHEN** a future Alert Details integration shows source-IP investigation context
- **THEN** it uses the source-IP context endpoint for incidents, queue activity, blocklist state, reputation context, and playbook execution context

#### Scenario: Map popup uses source-IP context
- **WHEN** a future Map popup integration shows source-IP investigation context
- **THEN** it uses the source-IP context endpoint for normalized context rather than relying only on the clicked alert object
