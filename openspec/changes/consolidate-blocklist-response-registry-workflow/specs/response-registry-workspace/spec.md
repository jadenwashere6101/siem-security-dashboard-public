## MODIFIED Requirements

### Requirement: Response Registry navigation and views
The sidebar SHALL provide one visible Response Registry workspace with All, Monitoring, Blocklist Tracking, Escalated, Pending, Failed/Rejected, and History views; it SHALL NOT show a separate Blocklist workspace.

#### Scenario: User opens Blocklist Tracking
- **WHEN** an authorized user selects Blocklist Tracking in Response Registry
- **THEN** the application SHALL show the canonical Blocklist tracking records and actions in that workspace

#### Scenario: Legacy Blocklist navigation is used
- **WHEN** a stored landing preference or internal legacy request targets `blocklist`
- **THEN** the application SHALL normalize it to Response Registry's Blocklist Tracking view without losing functionality or creating a second state source

### Requirement: Discoverable Blocklist tracking removal
Response Registry SHALL expose a clear supported removal action for eligible active Blocklist tracking records and SHALL explain its actual effect.

#### Scenario: Eligible active record
- **WHEN** an authorized analyst views an active non-protected Blocklist tracking record
- **THEN** the UI SHALL offer “Remove Tracking” and explain that tracking becomes inactive, history remains, and no firewall/provider/host enforcement is changed

#### Scenario: Ineligible record
- **WHEN** a record is terminal, expired, protected, unauthorized, or otherwise ineligible
- **THEN** the UI SHALL keep its history readable and SHALL hide or disable mutation with a truthful reason

