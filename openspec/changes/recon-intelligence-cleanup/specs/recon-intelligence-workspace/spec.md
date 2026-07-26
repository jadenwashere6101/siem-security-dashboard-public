## ADDED Requirements

### Requirement: Recon history workspace
The system SHALL provide a bounded analyst workflow for browsing complete Distributed Internet Reconnaissance Activity history outside the SOC Command Center summary.

#### Scenario: Analyst opens complete recon history
- **WHEN** an analyst opens the recon history experience
- **THEN** the system returns a paginated list of recon activities
- **AND** the response includes `items`, `total`, `limit`, `offset`, and applied filter metadata
- **AND** the UI does not rely on infinite scrolling to access older recon activities

#### Scenario: Command Center stays summarized
- **WHEN** the SOC Command Center loads recon activity
- **THEN** it shows a bounded curated summary of recent or high-priority recon activity
- **AND** it provides a clear navigation path to the complete recon history experience
- **AND** it does not attempt to render the full recon history inline

### Requirement: Recon history filtering and search
The recon history workflow SHALL support filters that let analysts find relevant activity without scanning an unbounded list.

#### Scenario: Analyst filters recon history
- **WHEN** an analyst applies status, severity, confidence, classification, time range, or search filters
- **THEN** the backend applies those filters before pagination
- **AND** the returned `total` reflects the combined filtered result set
- **AND** clearing filters restores the default bounded history query

#### Scenario: Analyst searches recon evidence
- **WHEN** an analyst searches by source IP, target/protected range, service/port, activity ID, or related incident ID
- **THEN** matching recon activities are returned without changing ingest, alert, SOAR, or notification behavior

### Requirement: Recon detail remains bounded
Recon activity detail SHALL provide a compact evidence summary and paginate linked alerts separately from the activity summary payload.

#### Scenario: Analyst opens recon detail
- **WHEN** an analyst selects a recon activity
- **THEN** the detail response includes the activity summary, intelligence classification, confidence, evidence reasons, target/service summary, and investigation pivots
- **AND** it does not require all linked alerts to be embedded in the primary detail payload

#### Scenario: Analyst browses linked alerts
- **WHEN** an analyst requests linked alerts for a recon activity
- **THEN** the system returns linked alerts with `limit`, `offset`, `total`, and deterministic sorting
- **AND** the analyst can page through the complete linked alert history for that activity

### Requirement: Evidence-gated recon intelligence
The system SHALL classify recon activity using an evidence-based model that distinguishes weak recon clusters from campaign-grade reconnaissance.

#### Scenario: Weak activity is not called a campaign
- **WHEN** a recon activity has only one linked alert, one source, a short duration, and no related incident or progression evidence
- **THEN** the system classifies it as a low-confidence recon cluster
- **AND** the UI does not label it as campaign-linked recon

#### Scenario: Campaign-grade recon requires multiple evidence categories
- **WHEN** a recon activity has sufficient source diversity, linked alert count, duration, target/service consistency, alert-type diversity, incident correlation, or attack progression evidence
- **THEN** the system classifies it as possible campaign or campaign recon according to the configured evidence thresholds
- **AND** the response includes reasons explaining which evidence categories contributed to the confidence level

#### Scenario: Missing evidence is visible
- **WHEN** a recon activity does not meet campaign-grade thresholds
- **THEN** the response includes missing or weak evidence signals that explain why confidence remains low
- **AND** the recommended action remains monitor or review rather than investigate as a campaign

### Requirement: Existing operational behavior is preserved
Recon intelligence cleanup SHALL NOT change existing ingest, detection, alerting, SOAR, notification, incident, or AI execution behavior.

#### Scenario: Recon enrollment remains compatible
- **WHEN** pfSense recon alerts are ingested
- **THEN** existing recon activity enrollment still links eligible alerts to recon activities
- **AND** existing alerts and events are not deleted, rewritten, or reclassified outside the recon intelligence projection

#### Scenario: Existing integrations remain read-compatible
- **WHEN** notifications, AI prompts, source-IP context, or alert detail views consume recon activity data
- **THEN** existing fields remain backward-compatible
- **AND** new confidence/classification fields are additive unless a separate approved change modifies those consumers

### Requirement: Recon implementation verification
The implementation SHALL include focused automated and browser verification for recon history browsing and intelligence quality.

#### Scenario: Backend verification
- **WHEN** implementation is complete
- **THEN** backend tests prove recon history pagination, filtering, search, linked-alert pagination, and evidence-gated classification behavior
- **AND** tests prove weak one-alert clusters are not labeled as campaign recon

#### Scenario: Frontend verification
- **WHEN** implementation is complete
- **THEN** frontend tests cover the Command Center summary, Recon workspace filters, pagination controls, detail loading, linked-alert pagination, and investigation pivots
- **AND** a production build succeeds

#### Scenario: Runtime verification handoff
- **WHEN** implementation is ready for deployment
- **THEN** the handoff identifies that VM sync and runtime browser verification are required for the deployed frontend/backend behavior
