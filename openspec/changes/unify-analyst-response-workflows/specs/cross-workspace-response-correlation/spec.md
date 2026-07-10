## ADDED Requirements

### Requirement: Shared action behavior across analyst surfaces
Dashboard alerts, alert details, Threat Hunt, Attack Map, incidents, Source-IP Context, SOC Command Center, playbooks, queue, approvals, and Response Registry SHALL invoke shared response contracts and present equivalent outcomes for equivalent actions.

#### Scenario: Block IP is selected from any supported surface
- **WHEN** an authorized user selects `block_ip` from any supported analyst surface
- **THEN** the same validation, idempotency, tracking-only mutation, provenance, canonical outcome, and analyst confirmation contract SHALL apply

### Requirement: Mutation-driven resource synchronization
Successful mutations SHALL identify affected resources and the frontend SHALL refresh or invalidate every currently visible dependent read model.

#### Scenario: Dashboard block action succeeds
- **WHEN** a Dashboard alert action records Blocklist tracking
- **THEN** alert outcome, response log, Response Registry, Blocklist Tracking, Source-IP Context, relevant incident/playbook/queue/approval context, metrics, and command-center summaries SHALL become consistent without a full browser reload

### Requirement: Contextual deep links and preserved filters
Analyst summaries and identifiers SHALL link to their authoritative workspace with relevant record selection and filters preserved.

#### Scenario: Command Center reports pending approvals
- **WHEN** an analyst selects the pending-approval attention item
- **THEN** the application SHALL open the Approvals workspace filtered to pending records rather than only opening a generic operations page

#### Scenario: Incident lists a linked alert
- **WHEN** an analyst selects the linked alert identifier
- **THEN** the Dashboard SHALL open the canonical alert detail while retaining a route back to the incident

#### Scenario: Threat Hunt result is investigated
- **WHEN** an analyst selects a response or investigation handoff for an event IP
- **THEN** the next workspace SHALL receive the IP and event provenance rather than relying only on a free-text search

### Requirement: Truthful and accessible controls
Controls SHALL distinguish requested action from actual outcome, visually locked controls SHALL not execute, and success messages SHALL identify the created or changed resource.

#### Scenario: Unauthorized manual action is displayed
- **WHEN** the user lacks the required role
- **THEN** every rendering variant SHALL be disabled or omitted and SHALL NOT issue a backend request

#### Scenario: Tracking-only block succeeds
- **WHEN** the backend returns a tracking-only outcome and Blocklist ID
- **THEN** the UI SHALL confirm that the SIEM Blocklist entry was created or reused and that no firewall, host, provider, or external enforcement occurred

### Requirement: Lifecycle relationship guidance
The UI SHALL preserve independent alert and incident lifecycles while surfacing contradictions that require analyst review.

#### Scenario: Last open alert in incident is resolved
- **WHEN** resolving an alert leaves its linked incident open with no other open linked alerts
- **THEN** the UI SHALL explain that incident status is independent and offer a direct review action without silently resolving the incident
