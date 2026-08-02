# Spec: SOC Briefing Analyst Quality

## ADDED Requirements

### Requirement: SOC Briefing executive summary provides analyst judgment

SOC Briefing SHALL provide a concise executive summary that answers what happened, why it matters, what changed, and what deserves immediate attention.

SOC Briefing SHALL preserve a model-generated Executive Summary only when deterministic quality checks show that it communicates the activity, security judgment or why it matters, and analyst direction or next action.

#### Scenario: Placeholder summaries are not accepted

- **GIVEN** provider output contains placeholder summary text
- **WHEN** SOC Briefing post-processing runs
- **THEN** the persisted summary SHALL be replaced with deterministic analyst-readable language
- **AND** it SHALL NOT include placeholder wording such as "Analysis of provided evidence".

#### Scenario: Bare title summaries are not accepted

- **GIVEN** provider output contains an Executive Summary such as "Potential Scanning Activity", "pfSense Firewall Port Scans", or another short alert-family title
- **WHEN** SOC Briefing post-processing runs
- **THEN** the persisted summary SHALL be replaced with deterministic handoff language
- **AND** the replacement SHALL include activity, security judgment, and a next analyst action.

#### Scenario: Complete shift-handoff summaries are preserved

- **GIVEN** provider output contains a concise summary that describes the activity, states a security judgment or why it matters, and gives analyst direction
- **WHEN** SOC Briefing post-processing runs
- **THEN** the model-generated summary SHALL be preserved.

### Requirement: SOC Briefing sections are analyst-readable

SOC Briefing SHALL avoid raw JSON-style section dumps and SHALL explain empty sections.

SOC Briefing SHALL NOT expose internal pipeline terminology or raw backend/source metadata in analyst-facing summary or sections, including selected candidates, bounded evidence references, skipped candidates, source paths, tool names, record counts, or investigation-engine mechanics.

SOC Briefing SHALL NOT directly stringify dictionaries, lists, raw JSON, or Python literal representations into analyst-facing summary or section prose.

#### Scenario: Evidence reviewed is readable

- **GIVEN** evidence refs or tool evidence exist
- **WHEN** SOC Briefing is persisted
- **THEN** Evidence Reviewed SHALL describe what was learned from the evidence in analyst-readable language rather than raw JSON, route/source paths, tool names, or record counts.

#### Scenario: Production evidence dict shapes are normalized

- **GIVEN** the provider returns Evidence Reviewed items shaped as `fact`, `fact` + `inference` + `uncertainty`, `type` + `description`, or type-only dictionaries
- **WHEN** SOC Briefing post-processing runs
- **THEN** each item SHALL be converted into readable evidence prose
- **AND** the output SHALL NOT contain Python dict syntax, JSON syntax, key names, raw source paths, tool names, or internal IDs.

#### Scenario: Internal metadata is not analyst-facing

- **GIVEN** SOC Briefing uses candidate and evidence metadata internally
- **WHEN** summary and sections are persisted
- **THEN** analyst-facing prose SHALL NOT include selected-candidate counts, bounded evidence-reference counts, skipped-candidate counts, source paths, tool names, record counts, `dedup_key`, lifecycle/storage terminology, or investigation-engine mechanics.

#### Scenario: Unknown dictionaries are safe

- **GIVEN** the provider returns a section item with unknown dictionary keys, nested dictionaries, nested arrays, or internal metadata
- **WHEN** SOC Briefing post-processing runs
- **THEN** useful scalar analyst-facing values SHALL be extracted and sanitized
- **AND** internal metadata SHALL be omitted
- **AND** if no useful value remains, a deterministic section-specific explanation SHALL be used.

#### Scenario: Duplicate punctuation is normalized

- **GIVEN** provider section content includes duplicate punctuation such as "network.."
- **WHEN** SOC Briefing post-processing runs
- **THEN** analyst-facing prose SHALL normalize the duplicate punctuation.

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

#### Scenario: Production recommendation dict shapes are normalized

- **GIVEN** the provider returns Recommendation items shaped as `step` + `description`, `action` + `target`, or `recommended_action` + `reason`
- **WHEN** SOC Briefing post-processing runs
- **THEN** each item SHALL be converted into a clear analyst instruction
- **AND** the output SHALL remain evidence-specific
- **AND** the output SHALL NOT contain Python dict syntax, JSON syntax, raw source paths, tool names, record metadata, or internal identifiers.

### Requirement: SOC Briefing correlates related alerts when possible

SOC Briefing SHALL correlate alerts by shared source IP, destination, subnet, alert family, repeated behavior, or timeline relationship when such evidence is available.

#### Scenario: Multiple alerts share a source IP

- **GIVEN** multiple selected alerts share the same source IP
- **WHEN** SOC Briefing is persisted
- **THEN** the briefing SHALL describe the correlation rather than treating every alert as unrelated inventory.
