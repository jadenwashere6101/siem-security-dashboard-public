## ADDED Requirements

### Requirement: Shared dashboard loading indicators
The dashboard and Recent Alerts UI SHALL use one shared loading indicator implementation and one animation definition that is loaded by the React application entrypoint.

#### Scenario: Dashboard initial load animates
- **WHEN** the dashboard is waiting for initial alert or summary data
- **THEN** the rendered loading indicator uses the shared loading component or shared loading styles
- **AND** the animation keyframes are present in a globally imported stylesheet
- **AND** no local duplicate spinner implementation is required for that location

#### Scenario: Inline refresh uses the shared loading indicator
- **WHEN** a dashboard subsection, timeline, or Recent Alerts table enters a pending or refreshing state
- **THEN** the rendered loading state uses the same shared loading implementation
- **AND** it does not define independent spinner keyframes or duplicate inline animation logic

#### Scenario: Reduced motion remains accessible
- **WHEN** the browser requests reduced motion
- **THEN** the loading state remains visible and understandable
- **AND** spinner rotation is disabled or replaced with an equivalent static themed loading state

### Requirement: Source-IP dashboard widgets exclude synthetic sources before aggregation
Dashboard summary source-IP widgets SHALL exclude configured synthetic/demo source IPs before grouping, counting, ranking, limiting, or mapping source-IP aggregates.

#### Scenario: Top Source IPs limit is applied after exclusion
- **GIVEN** synthetic/demo source IPs have more alert rows than legitimate source IPs
- **WHEN** `/alerts/summary` builds the Top Source IPs response
- **THEN** synthetic/demo source IP rows are excluded before aggregation and `LIMIT`
- **AND** legitimate source IPs are able to occupy the returned ranked slots

#### Scenario: Source-IP widgets use the same exclusion policy
- **WHEN** `/alerts/summary` returns source-IP-derived dashboard data
- **THEN** Top Source IPs, Unique Source IPs, Attack Map markers, and source-IP map aggregation use the same synthetic/demo exclusion policy
- **AND** each affected widget remains internally consistent with the others

#### Scenario: Alert-volume widgets preserve historical alert counts
- **WHEN** `/alerts/summary` returns alert-volume data
- **THEN** Total Alerts, severity counts, and Alerts Over Time continue to represent the filtered alert population
- **AND** historical production alert rows are not deleted, rewritten, or hidden from Recent Alerts solely because source-IP widgets exclude synthetic/demo source IPs

#### Scenario: Synthetic filtering is deterministic and production-safe
- **WHEN** the backend evaluates whether a source IP is synthetic/demo data
- **THEN** it uses explicit configured exclusions and known documentation/demo networks
- **AND** it does not blanket-exclude private, reserved, or internal-address ranges that may represent legitimate production telemetry

### Requirement: Recent Alerts supports detection-rule filtering
Recent Alerts SHALL allow analysts to filter alerts by the detection rule that generated the alert while preserving existing filter behavior.

#### Scenario: Alerts API accepts a rule filter
- **WHEN** the client requests `/alerts` with `rule_id`
- **THEN** the backend maps `rule_id` to the alert detection rule field
- **AND** the filter composes with search, severity, source, status, operational scope, exact source IP, exact target IP, alert ID, sort, limit, and offset
- **AND** pagination totals reflect the combined filters

#### Scenario: Summary API accepts the same rule filter
- **WHEN** the client requests `/alerts/summary` with `rule_id`
- **THEN** dashboard metrics, charts, and summary widgets are calculated from the same filtered alert population used by Recent Alerts
- **AND** source-IP-derived widgets still apply the synthetic/demo source-IP exclusion policy before aggregation

#### Scenario: Rule filter appears in the analyst workflow
- **WHEN** an analyst opens Recent Alerts
- **THEN** the toolbar exposes a detection-rule filter using non-sensitive detection-rule labels or observed alert types
- **AND** selecting a rule refreshes the table and dashboard summary consistently
- **AND** clearing filters restores the current default Recent Alerts behavior

#### Scenario: Exports preserve the active rule filter
- **WHEN** an analyst exports alerts while `rule_id` or other Recent Alerts filters are active
- **THEN** CSV, PDF, and report exports apply the same eligible filters as the table
- **AND** exported rows match the alert set represented by the current filtered workflow

#### Scenario: Invalid rule filters fail clearly
- **WHEN** the client sends a malformed or unsupported `rule_id`
- **THEN** the backend returns a clear validation error
- **AND** it does not silently ignore the requested detection-rule filter

### Requirement: Implementation verification covers UI and API behavior
The implementation SHALL include focused automated and visual verification for loading states, source-IP filtering, and detection-rule filtering.

#### Scenario: Automated checks cover backend filtering
- **WHEN** implementation is complete
- **THEN** focused backend tests prove `/alerts`, `/alerts/summary`, and exports apply detection-rule filters consistently
- **AND** source-IP summary tests prove synthetic/demo source IPs are excluded before aggregation and limit

#### Scenario: Automated checks cover frontend behavior
- **WHEN** implementation is complete
- **THEN** focused frontend tests cover shared loading usage, detection-rule query construction, toolbar state, reset behavior, and export URL construction
- **AND** the React production build succeeds

#### Scenario: Visual verification confirms analyst-facing behavior
- **WHEN** implementation is complete locally
- **THEN** browser verification confirms the loading indicator animates or presents the approved static fallback
- **AND** browser verification confirms Top Source IPs no longer shows synthetic/demo IPs in the affected chart
- **AND** after deployment, runtime visual verification confirms the same behavior in the target environment
