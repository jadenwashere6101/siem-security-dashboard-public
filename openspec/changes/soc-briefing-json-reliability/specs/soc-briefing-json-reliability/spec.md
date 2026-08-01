# Spec: SOC Briefing JSON Reliability

## ADDED Requirements

### Requirement: SOC Briefing validates structured provider output

SOC Briefing synthesis SHALL validate provider JSON before accepting it as generated briefing content.

#### Scenario: Valid structured output is accepted

- **GIVEN** the provider returns valid JSON with `summary` and all required SOC briefing sections
- **WHEN** SOC Briefing synthesis parses the response
- **THEN** the briefing SHALL be accepted as successful
- **AND** existing successful behavior SHALL remain unchanged.

#### Scenario: Missing sections are rejected

- **GIVEN** the provider returns JSON missing one or more required briefing sections
- **WHEN** validation runs
- **THEN** the response SHALL be treated as invalid
- **AND** the missing sections SHALL NOT be silently fabricated into a successful provider response.

#### Scenario: Non-array sections are rejected

- **GIVEN** the provider returns a required section with a non-array value
- **WHEN** validation runs
- **THEN** the response SHALL be treated as invalid.

### Requirement: SOC Briefing performs exactly one bounded repair attempt

SOC Briefing synthesis SHALL attempt one bounded repair for malformed or schema-invalid provider output.

#### Scenario: Malformed JSON repaired successfully

- **GIVEN** initial provider output is malformed JSON
- **AND** the repair response is valid structured briefing JSON
- **WHEN** synthesis handles the response
- **THEN** the repaired response SHALL be accepted
- **AND** exactly one repair call SHALL be made.

#### Scenario: Truncated output repaired successfully

- **GIVEN** initial provider output is truncated before a complete JSON object
- **AND** the repair response is valid structured briefing JSON
- **WHEN** synthesis handles the response
- **THEN** the repaired response SHALL be accepted
- **AND** exactly one repair call SHALL be made.

#### Scenario: Repair failure fails cleanly

- **GIVEN** initial provider output is malformed or schema-invalid
- **AND** the single repair response is unavailable, malformed, or still invalid
- **WHEN** synthesis completes
- **THEN** SOC Briefing SHALL persist deterministic partial briefing content
- **AND** SHALL use a clear malformed-output error code
- **AND** SHALL NOT perform more than one repair attempt.

### Requirement: SOC Briefing repair preserves safety and evidence integrity

The repair path SHALL remain read-only, local-only, bounded, and evidence-preserving.

#### Scenario: Repair does not fabricate evidence

- **WHEN** a repair attempt is made
- **THEN** the repair prompt SHALL instruct the provider not to invent evidence
- **AND** persisted evidence refs SHALL remain the bounded refs collected before synthesis.

#### Scenario: Repair metadata is auditable and non-mutating

- **WHEN** a repair call is made
- **THEN** gateway metadata SHALL include `action=soc_briefing_repair`, `repair_attempt=1`, and `read_only=true`
- **AND** SHALL NOT include preview, confirm, apply, persistence, SOAR, or mutation semantics.

### Requirement: SOC Briefing completion budget reduces truncation risk narrowly

SOC Briefing synthesis SHALL keep any default completion-token budget adjustment minimal and scoped only to structured briefing JSON reliability.

#### Scenario: Completion budget remains bounded

- **WHEN** SOC Briefing synthesis requests model output
- **THEN** the configured completion budget SHALL remain bounded
- **AND** SHALL be documented as a narrow reliability adjustment for six-section JSON output.
