# response-registry-workspace Specification

## Purpose
Sole analyst workspace for canonical indicator dispositions and Blocklist Tracking, including discoverable tracking-only removal and legacy Blocklist navigation compatibility.

## Requirements

### Requirement: Response Registry navigation and views
The sidebar SHALL provide one visible Response Registry workspace with All, Monitoring, Blocklist Tracking, Escalated, Pending, Failed/Rejected, and History views; it SHALL NOT show a separate Blocklist workspace.

#### Scenario: Analyst opens the registry
- **WHEN** an authorized user selects Response Registry
- **THEN** the workspace SHALL show paginated/filterable indicator dispositions with requested action, actual outcome, enforcement mode, risk, related counts, origin, actor, reason, expiry, and last activity

#### Scenario: User opens Blocklist Tracking
- **WHEN** an authorized user selects Blocklist Tracking in Response Registry
- **THEN** the application SHALL show the canonical Blocklist tracking records and actions in that workspace

#### Scenario: Legacy Blocklist navigation is used
- **WHEN** a stored landing preference or internal legacy request targets `blocklist`
- **THEN** the application SHALL normalize it to Response Registry's Blocklist Tracking view without losing functionality or creating a second state source

### Requirement: Registry detail and history
An indicator detail view SHALL expose current disposition, explicit enforcement status, complete response history, and links to authoritative related records.

#### Scenario: Tracking-only blocked IP is viewed
- **WHEN** an analyst opens an IP with active Blocklist tracking
- **THEN** the view SHALL state “tracking only” and “no firewall enforcement,” show every originating request, and link related alerts, incidents, playbooks, approvals, queue items, and outcomes

### Requirement: Guarded contextual registry actions
The workspace SHALL offer only role-authorized actions and SHALL return the resulting canonical outcome rather than generic success.

#### Scenario: Analyst starts monitoring
- **WHEN** an authorized analyst selects Monitor from registry detail
- **THEN** the workspace SHALL display the created watch disposition and refresh history without requiring a page reload

#### Scenario: Viewer sees a restricted action
- **WHEN** a viewer lacks mutation permission
- **THEN** the control SHALL be disabled or absent, SHALL expose an accessible restriction explanation, and SHALL NOT send a mutation request

### Requirement: Blocklist management compatibility
Existing add, expiry, list, and unblock behavior SHALL remain available through the Response Registry while adopting canonical outcomes and provenance.

#### Scenario: Tracked IP is unblocked
- **WHEN** an authorized analyst removes active tracking
- **THEN** the Blocklist record SHALL become inactive, a removal event SHALL be appended, and history SHALL remain visible without implying a firewall change

### Requirement: Discoverable Blocklist tracking removal
Response Registry SHALL expose a clear supported removal action for eligible active Blocklist tracking records and SHALL explain its actual effect.

#### Scenario: Eligible active record
- **WHEN** an authorized analyst views an active non-protected Blocklist tracking record
- **THEN** the UI SHALL offer “Remove Tracking” and explain that tracking becomes inactive, history remains, and no firewall/provider/host enforcement is changed

#### Scenario: Ineligible record
- **WHEN** a record is terminal, expired, protected, unauthorized, or otherwise ineligible
- **THEN** the UI SHALL keep its history readable and SHALL hide or disable mutation with a truthful reason
