## ADDED Requirements

### Requirement: Super-admin configuration API
The backend SHALL provide authenticated super-admin endpoints to list effective pfSense ingest filters and update one known category atomically.

#### Scenario: Configuration is listed
- **WHEN** a super admin requests pfSense ingest configuration
- **THEN** the response SHALL include each category’s effective enabled state, parameters, default/override status, description, updater, and update timestamp

#### Scenario: Unknown category is updated
- **WHEN** a client submits an unknown category or parameter
- **THEN** the API SHALL return a safe 4xx response and SHALL NOT persist it

### Requirement: Restartless update visibility
Committed API updates SHALL affect the next ingest request without backend or listener restart.

#### Scenario: Routine allows are enabled
- **WHEN** a super admin enables `all_allow_events` and the PATCH commits
- **THEN** the next valid routine allow SHALL be retained

#### Scenario: Update fails
- **WHEN** validation or persistence fails
- **THEN** the prior effective configuration SHALL remain active and the UI SHALL show the failure

### Requirement: Administration panel
The frontend SHALL add a super-admin-only “pfSense Ingest Filters” panel under Administration using existing navigation, service, dark-theme, and feedback patterns.

#### Scenario: Super admin opens panel
- **WHEN** a super admin navigates to the panel
- **THEN** it SHALL show Block events, Inbound sensitive-port allows, All allow events, DNS port-53 traffic, ICMP traffic, and the sensitive-port editor with effective state and fallback status

#### Scenario: Restricted user navigates directly
- **WHEN** a non-super-admin attempts to open or call the panel controls
- **THEN** navigation and backend authorization SHALL prevent mutation

### Requirement: Safe toggle and port editing UX
The panel SHALL validate inputs, disclose overlapping-category effects, confirm saved effective state, and avoid ambiguous claims about DNS content or firewall enforcement.

#### Scenario: Sensitive ports are edited
- **WHEN** a super admin submits a valid list
- **THEN** the UI SHALL reload and show the canonical normalized list used by retention and suspicious-allow detection

#### Scenario: DNS control is displayed
- **WHEN** the DNS category is rendered
- **THEN** its label/help SHALL state TCP/UDP destination port 53 and SHALL NOT claim domain/query visibility

#### Scenario: Configuration fallback is active
- **WHEN** the API reports invalid or unavailable overrides
- **THEN** the panel SHALL visibly identify safe defaults as active and SHALL NOT imply the override is applied

### Requirement: UI verification quality
The Administration panel SHALL include focused service/component tests, role tests, validation/error tests, and production-build plus dark-theme/accessibility verification.

#### Scenario: UI implementation is ready for handoff
- **WHEN** Mac Phase 2 completes
- **THEN** targeted tests and production build SHALL pass and visual review SHALL confirm readable spacing, contrast, labels, disabled states, and responsive behavior
