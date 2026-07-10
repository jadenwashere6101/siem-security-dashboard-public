# response-registry-workspace Specification

## Purpose
TBD - created by archiving change unify-analyst-response-workflows. Update Purpose after archive.
## Requirements
### Requirement: Response Registry navigation and views
The sidebar SHALL provide a Response Registry workspace with All, Monitoring, Blocklist Tracking, Escalated, Pending, Failed/Rejected, and History views.

#### Scenario: Analyst opens the registry
- **WHEN** an authorized user selects Response Registry
- **THEN** the workspace SHALL show paginated/filterable indicator dispositions with requested action, actual outcome, enforcement mode, risk, related counts, origin, actor, reason, expiry, and last activity

#### Scenario: Legacy Blocklist navigation is used
- **WHEN** a user follows the existing Blocklist navigation or deep link after migration
- **THEN** the application SHALL open or redirect to Response Registry’s Blocklist Tracking view without losing Blocklist functionality

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

