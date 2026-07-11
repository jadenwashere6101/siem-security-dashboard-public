## ADDED Requirements

### Requirement: Canonical outcome evidence presentation
Affected alert and SOAR surfaces SHALL pair canonical outcome labels with available evidence and SHALL never infer real execution from ambiguous or missing data.

#### Scenario: Simulated outcome with evidence
- **WHEN** a canonical outcome is simulated
- **THEN** the UI SHALL retain the Simulated label and expose mode, no-real-external-effect state, summary/reason, and available linked queue/execution/delivery/approval identifiers

#### Scenario: Confirmed real outcome
- **WHEN** canonical mode and external-effect evidence confirm real execution
- **THEN** the UI SHALL label it real executed and expose the confirming evidence without relying on a legacy status string alone

#### Scenario: Missing or contradictory evidence
- **WHEN** evidence is absent or canonical and legacy fields conflict
- **THEN** the UI SHALL show Unknown/not-recorded or a data-quality warning and SHALL NOT claim real execution

### Requirement: Distinct operational states
Presentation SHALL keep simulation, tracking-only, read-only/observed, pending approval, blocked/rejected, failed, skipped, real executed, and unknown states distinct.

#### Scenario: Tracking-only Blocklist outcome
- **WHEN** an outcome records SIEM Blocklist tracking without external enforcement
- **THEN** the UI SHALL label it tracking-only and SHALL NOT present it as simulated or firewall-executed

#### Scenario: Pending approval
- **WHEN** an action awaits approval
- **THEN** the UI SHALL describe the requested effect as pending and SHALL NOT present it as executed

### Requirement: Manual queue simulation explanation
The Queue Visibility manual batch control SHALL explain its bounded internal processing and external-effect prohibition before and after invocation.

#### Scenario: Before simulation batch
- **WHEN** a super admin reviews the Run simulation batch control
- **THEN** the UI SHALL state that pending queue work is processed with the simulation executor, internal lifecycle records may change, and no notification/provider/firewall/host/external effect can occur

#### Scenario: Simulation result
- **WHEN** the simulation batch returns results
- **THEN** the UI SHALL report simulated/failed/skipped/requeued internal outcomes truthfully and SHALL NOT use real-execution language

### Requirement: Recent Alerts outcome clarity
Recent Alerts details SHALL show the canonical linked outcome and enough provenance to identify its source record when available.

#### Scenario: Alert linked to simulated playbook or queue work
- **WHEN** an alert's latest canonical outcome comes from simulated queue or playbook processing
- **THEN** Recent Alerts SHALL display Simulated plus linked evidence and SHALL NOT relabel it merely because the alert itself is real detection data

#### Scenario: Stale legacy response_status is non-authoritative
- **WHEN** `alerts.response_status` remains `pending` (or another legacy value) after the linked canonical ResponseOutcome is terminal
- **THEN** Alert Details and Recent Alerts SHALL present the canonical ResponseOutcome label/evidence as authoritative and SHALL NOT present the legacy field as the live response status

### Requirement: Distinct approval denied versus expired reasons
Approval timeout and active human denial SHALL use distinct canonical reason codes through producer, persistence, serializer, and presentation.

#### Scenario: Approval expires unanswered
- **WHEN** an approval request times out without a human decision
- **THEN** the system SHALL record `reason_code=approval_expired` on the blocked outcome, present an Expired label/explanation that is not an active denial, and SHALL keep all execution effect booleans false

#### Scenario: Approval denied by a human
- **WHEN** an approval request is denied by an authorized actor
- **THEN** the system SHALL record `reason_code=approval_denied` and present a Rejected/denied label distinct from Expired

#### Scenario: Legacy approval_denied evidence remains renderable
- **WHEN** historical outcome evidence already stores `reason_code=approval_denied` (including older expire-path records)
- **THEN** the UI SHALL continue to render that evidence safely as Rejected/denied without rewriting historical rows

