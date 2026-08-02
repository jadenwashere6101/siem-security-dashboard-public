# Spec: SOC Briefing Analyst Quality

## ADDED Requirements

### Requirement: SOC Briefing executive summary provides analyst judgment

SOC Briefing SHALL provide a concise executive summary that answers what happened, why it matters, what changed, and what deserves immediate attention.

#### Scenario: Placeholder summaries are not accepted

- **GIVEN** provider output contains placeholder summary text
- **WHEN** SOC Briefing post-processing runs
- **THEN** the persisted summary SHALL be replaced with deterministic analyst-readable language
- **AND** it SHALL NOT include placeholder wording such as "Analysis of provided evidence".

### Requirement: SOC Briefing sections are analyst-readable

SOC Briefing SHALL avoid raw JSON-style section dumps and SHALL explain empty sections.

SOC Briefing SHALL NOT expose internal pipeline terminology or raw backend/source metadata in analyst-facing summary or sections, including selected candidates, bounded evidence references, skipped candidates, source paths, tool names, record counts, or investigation-engine mechanics.

#### Scenario: Evidence reviewed is readable

- **GIVEN** evidence refs or tool evidence exist
- **WHEN** SOC Briefing is persisted
- **THEN** Evidence Reviewed SHALL describe what was learned from the evidence in analyst-readable language rather than raw JSON, route/source paths, tool names, or record counts.

#### Scenario: Internal metadata is not analyst-facing

- **GIVEN** SOC Briefing uses candidate and evidence metadata internally
- **WHEN** summary and sections are persisted
- **THEN** analyst-facing prose SHALL NOT include selected-candidate counts, bounded evidence-reference counts, skipped-candidate counts, source paths, tool names, record counts, or investigation-engine mechanics.

#### Scenario: Empty sections explain why

- **GIVEN** a briefing section has no entries
- **WHEN** SOC Briefing is persisted
- **THEN** the section SHALL include a concise explanation of why no item appears.

### Requirement: SOC Briefing findings and recommendations contain reasoning

Critical findings and recommendations SHALL connect evidence, analyst judgment, confidence, and next action without fabricating evidence.

#### Scenario: Critical finding includes required analyst fields

- **GIVEN** critical evidence exists
- **WHEN** SOC Briefing is generated or falls back deterministically
- **THEN** each critical finding SHALL include what happened, supporting evidence, why it matters, confidence, and recommended action.

#### Scenario: Recommendations reference evidence

- **GIVEN** source IPs or evidence refs exist
- **WHEN** recommendations are persisted
- **THEN** recommendations SHALL reference specific analyst-meaningful evidence such as source IP, alert behavior, or observed outcome gaps without exposing raw source paths or tool metadata.

### Requirement: SOC Briefing correlates related alerts when possible

SOC Briefing SHALL correlate alerts by shared source IP, destination, subnet, alert family, repeated behavior, or timeline relationship when such evidence is available.

#### Scenario: Multiple alerts share a source IP

- **GIVEN** multiple selected alerts share the same source IP
- **WHEN** SOC Briefing is persisted
- **THEN** the briefing SHALL describe the correlation rather than treating every alert as unrelated inventory.
