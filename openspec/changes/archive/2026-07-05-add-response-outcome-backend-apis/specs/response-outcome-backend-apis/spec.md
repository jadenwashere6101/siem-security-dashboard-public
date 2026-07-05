## ADDED Requirements

### Requirement: Child Change Scope
This change SHALL implement the remaining backend API response outcome contract work from parent roadmap `openspec/changes/clarify-soar-response-outcomes` Phase 6 after alert APIs.

#### Scenario: Parent roadmap remains master
- **WHEN** this child change is implemented
- **THEN** the parent roadmap SHALL remain the master roadmap/spec and this child change SHALL be treated as the active implementation spec for the remaining Phase 6 backend API work

#### Scenario: Alert API work is already complete
- **WHEN** this child change is implemented
- **THEN** the implementation SHALL NOT reimplement alert list/detail `response_outcome` work that was already completed in Phase 6 Slice 1

#### Scenario: No frontend or schema work
- **WHEN** this child change is implemented
- **THEN** it SHALL NOT modify frontend screens and SHALL NOT add migrations unless an unexpected existing-schema blocker is documented and separately approved

### Requirement: Additive Response Outcome API Contract
Updated backend entity APIs SHALL expose canonical response outcome data additively while preserving all existing legacy fields.

#### Scenario: Legacy fields are preserved
- **WHEN** an updated route returns an existing payload
- **THEN** all legacy fields that existed before this child change SHALL remain present with the same meaning

#### Scenario: Canonical outcome key is present
- **WHEN** an updated route returns an entity that can be associated with response work
- **THEN** the entity payload SHALL include a `response_outcome` key

#### Scenario: No canonical outcome exists
- **WHEN** an updated route returns an entity without a canonical decision or latest outcome
- **THEN** the entity payload SHALL include `response_outcome: null`

#### Scenario: Canonical outcome exists
- **WHEN** an updated route returns an entity with a canonical latest outcome
- **THEN** `response_outcome` SHALL include the shared serializer shape with SOAR correlation id, decision id, latest outcome event id, selected action, decision source, execution actor, execution mode/state, execution booleans, summary, reason code, related ids, and timestamps

#### Scenario: Existing helpers are reused
- **WHEN** backend code serializes canonical response outcome data
- **THEN** it SHALL reuse helpers from `core/soar_response_outcomes.py` rather than duplicating canonical semantics in route modules

#### Scenario: List endpoints avoid N+1 queries
- **WHEN** an updated list endpoint returns multiple rows
- **THEN** it SHALL batch or bulk-load canonical outcome data instead of issuing one canonical outcome query per returned row

### Requirement: Response Log API Outcomes
The response log API SHALL include canonical outcome linkage and latest outcome where an existing response log route or embedded response log payload is present.

#### Scenario: Response log route exists
- **WHEN** an existing route returns `response_actions_log` records
- **THEN** each response log record SHALL include `response_outcome` resolved from canonical outcome linkage where available

#### Scenario: Response log route does not exist
- **WHEN** implementation confirms there is no public response log API route
- **THEN** this child change SHALL document the route as skipped or deferred and SHALL NOT create a new response log endpoint

### Requirement: SOAR Queue API Outcomes
SOAR queue API responses SHALL include canonical latest outcome data additively.

#### Scenario: Queue recent/list response
- **WHEN** `GET /admin/soar/queue/recent` returns queue rows
- **THEN** each queue row SHALL include `response_outcome`, using batched lookup behavior

#### Scenario: Queue detail response
- **WHEN** `GET /admin/soar/queue/<queue_id>` returns one queue row
- **THEN** the queue payload SHALL include `response_outcome`

#### Scenario: Queue status response
- **WHEN** `GET /admin/soar/queue/status` returns aggregate queue state
- **THEN** the response SHOULD include additive canonical outcome summary fields where useful and SHALL preserve existing queue status fields

### Requirement: Playbook Execution API Outcomes
Playbook execution APIs SHALL expose execution-level and detail canonical outcome payloads without creating child decisions.

#### Scenario: Playbook execution list
- **WHEN** `GET /playbook-executions` returns execution rows
- **THEN** each execution payload SHALL include execution-level `response_outcome` using batched lookup behavior

#### Scenario: Playbook execution detail
- **WHEN** `GET /playbook-executions/<execution_id>` returns one execution
- **THEN** the payload SHALL include execution-level `response_outcome` and SHOULD include ordered canonical outcome timeline or step-level canonical outcome payloads where available

#### Scenario: No child decisions
- **WHEN** step-level canonical outcome payloads are returned
- **THEN** they SHALL attach to the existing execution-level decision and SHALL NOT require per-step child decisions

### Requirement: Approval API Outcomes
Approval APIs SHALL expose canonical approval response outcomes additively.

#### Scenario: Approval list
- **WHEN** `GET /approvals` returns approval requests
- **THEN** each approval payload SHALL include `response_outcome` using batched lookup behavior

#### Scenario: Approval detail
- **WHEN** `GET /approvals/<approval_id>` returns one approval request
- **THEN** the approval payload SHALL include `response_outcome`

#### Scenario: Approval decision response
- **WHEN** `POST /approvals/<approval_id>/decision` returns a decision result
- **THEN** the response SHALL preserve existing fields and SHOULD include canonical approval outcome fields when they are available after the decision

### Requirement: Notification Delivery API Outcomes
Notification delivery APIs SHALL expose canonical outcome data additively while preserving delivery-specific mode and status fields.

#### Scenario: Notification delivery list
- **WHEN** `GET /notification-deliveries` returns delivery attempts
- **THEN** each attempt SHALL include `response_outcome` using batched lookup behavior

#### Scenario: Notification delivery detail
- **WHEN** `GET /notification-deliveries/<attempt_id>` returns one delivery attempt
- **THEN** the payload SHALL include `response_outcome`

#### Scenario: Delivery fields are preserved
- **WHEN** canonical outcome fields are added to delivery payloads
- **THEN** existing provider, adapter, action, delivery `mode`, delivery `status`, failure, circuit breaker, metadata, and linkage fields SHALL remain unchanged

### Requirement: Incident API and Timeline Outcomes
Incident APIs SHALL include canonical response outcome data without mutating incident state.

#### Scenario: Incident list
- **WHEN** `GET /incidents` returns incidents
- **THEN** each incident payload SHALL include `response_outcome` using batched lookup behavior

#### Scenario: Incident detail
- **WHEN** `GET /incidents/<incident_id>` returns one incident
- **THEN** the incident payload SHALL include `response_outcome`

#### Scenario: Incident timeline
- **WHEN** `GET /incidents/<incident_id>/timeline` returns timeline entries
- **THEN** it SHALL preserve existing timeline entries and SHOULD include canonical outcome events as clearly typed timeline entries

#### Scenario: Read-only timeline
- **WHEN** incident timeline outcome data is serialized
- **THEN** the route SHALL NOT mutate incident, playbook, approval, notification, queue, or outcome state

### Requirement: Source-IP Context Outcomes
The Source-IP Context API SHALL include recent canonical outcomes and aggregate outcome counts for the requested source IP.

#### Scenario: Source-IP context response
- **WHEN** `GET /source-ip-context` returns context for a source IP
- **THEN** the response SHALL preserve existing context fields and SHALL include recent canonical outcomes for that source IP

#### Scenario: Source-IP outcome counts
- **WHEN** source-IP context includes canonical outcome aggregates
- **THEN** counts SHALL be grouped by execution mode, execution state, `external_executed`, `tracking_recorded`, and `simulated`

#### Scenario: Bounded read behavior
- **WHEN** source-IP context loads canonical outcomes
- **THEN** it SHALL use bounded recent queries and SHALL NOT perform per-related-record N+1 outcome lookups

### Requirement: Attack Map Backend Route Handling
Attack Map/source-IP popup backend response outcome work SHALL only update an existing backend route if one exists.

#### Scenario: Dedicated backend route exists
- **WHEN** implementation identifies a dedicated Attack Map or source-IP popup backend route that displays response status
- **THEN** that route SHALL add canonical response outcome data additively and preserve existing fields

#### Scenario: Dedicated backend route does not exist
- **WHEN** implementation confirms no dedicated backend route exists
- **THEN** this child change SHALL document the item as skipped or deferred and SHALL NOT create a new Attack Map endpoint

### Requirement: Blocklist API Outcomes
Blocklist APIs SHALL expose tracking-only provenance or canonical outcome data without implying firewall enforcement.

#### Scenario: Blocklist list response
- **WHEN** `GET /blocked-ips` returns blocklist records
- **THEN** each record SHALL include additive `response_outcome` or tracking-only provenance fields where canonical linkage can be resolved

#### Scenario: No canonical linkage
- **WHEN** a blocklist record cannot be safely linked to canonical outcome data
- **THEN** the payload SHALL include `response_outcome: null` or conservative provenance without claiming real enforcement

#### Scenario: Firewall enforcement language
- **WHEN** blocklist API payloads include canonical or provenance fields
- **THEN** they SHALL NOT imply firewall, provider, external, or local enforcement unless future approved schema and runtime work proves it

### Requirement: Metrics and SOC Command Center Outcome Aggregation
Existing metrics endpoints used by SOC Command Center SHALL include additive canonical outcome aggregate fields.

#### Scenario: No dedicated SOC backend route
- **WHEN** SOC Command Center needs canonical outcome aggregation
- **THEN** implementation SHALL use existing metrics endpoints and SHALL NOT create a new SOC Command Center backend route

#### Scenario: Playbook metrics
- **WHEN** `GET /metrics/playbooks` returns metrics
- **THEN** it SHALL preserve existing fields and include additive canonical outcome counts

#### Scenario: Notification metrics
- **WHEN** `GET /metrics/notifications` returns metrics
- **THEN** it SHALL preserve existing fields and include additive canonical outcome counts

#### Scenario: Incident metrics
- **WHEN** `GET /metrics/incidents` returns metrics
- **THEN** it SHALL preserve existing fields and include additive canonical outcome counts

#### Scenario: Approval metrics
- **WHEN** `GET /metrics/approvals` returns metrics
- **THEN** it SHALL preserve existing fields and include additive canonical outcome counts

#### Scenario: Required count groups
- **WHEN** metrics endpoints include canonical outcome counts
- **THEN** counts SHALL be grouped by `execution_mode`, `execution_state`, `external_executed`, `tracking_recorded`, and `simulated`

### Requirement: Backend API Contract Tests
Every updated backend route SHALL have focused API contract tests for canonical outcome additions.

#### Scenario: Route tests cover null outcomes
- **WHEN** an updated route returns records without canonical outcomes
- **THEN** tests SHALL assert the `response_outcome` key is present and null where applicable

#### Scenario: Route tests cover canonical payload
- **WHEN** an updated route returns records with canonical outcomes
- **THEN** tests SHALL assert the canonical payload shape and values

#### Scenario: Route tests cover legacy compatibility
- **WHEN** an updated route returns existing legacy fields
- **THEN** tests SHALL assert those fields remain present

#### Scenario: Read routes do not execute work
- **WHEN** updated read routes are exercised in tests
- **THEN** tests SHOULD assert they do not call worker execution, adapter execution, provider probes, or mutation helpers where applicable
