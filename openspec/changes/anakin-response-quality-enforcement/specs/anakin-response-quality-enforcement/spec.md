# anakin-response-quality-enforcement

## ADDED Requirements

### Requirement: Deterministic Tone Classification

Anakin SHALL classify request tone deterministically per request as `casual`, `professional`, or `technical`.

#### Scenario: Tone is classified without model discretion
- **WHEN** an Anakin workflow prompt is built
- **THEN** tone SHALL be classified from user prompt plus workflow/surface context
- **AND** the model SHALL NOT be asked to invent the tone classification.

#### Scenario: Shareable outputs force professional tone
- **WHEN** Generate Artifact, SOC Briefing, notes, playbooks, detection suggestions, or response recommendations are generated
- **THEN** tone SHALL be professional
- **AND** slang or profanity SHALL be prohibited.

### Requirement: Decision Support Recommendation First

Decision Support SHALL enforce a recommendation-first response contract.

#### Scenario: Recommendation is first
- **WHEN** Decision Support runs
- **THEN** the prompt SHALL require the first rendered content to be the recommendation
- **AND** SHALL require `recommendation`, `why`, `evidence`, `risks`, `alternatives`, `what_would_change_my_mind`, and `confidence`.

#### Scenario: Unsupported certainty is challenged
- **WHEN** the user presents a conclusion not supported by evidence
- **THEN** Anakin SHALL explicitly and respectfully disagree
- **AND** SHALL explain what the evidence actually supports.

### Requirement: Filler And Disclaimer Patterns Are Rejected

Anakin SHALL reject exact and near-equivalent filler/disclaimer patterns.

#### Scenario: Equivalent filler fails acceptance
- **WHEN** a response uses boilerplate such as `based on the context`, `alert is indicating`, `further investigation may reveal`, or generic closing caveats
- **THEN** response-quality acceptance SHALL fail.

#### Scenario: Deep Investigate ends usefully
- **WHEN** Deep Investigate responds
- **THEN** it SHALL end with a prioritized next step or the most important unresolved question
- **AND** SHALL NOT end with a generic disclaimer.

### Requirement: Existing Workflow Safety Remains

Response-quality enforcement SHALL NOT weaken existing workflow boundaries.

#### Scenario: Decision Support remains read-only
- **WHEN** Decision Support runs
- **THEN** it SHALL NOT generate artifacts, preview actions, confirm actions, apply actions, or mutate state.

#### Scenario: Artifact and briefing schemas remain professional
- **WHEN** Generate Artifact or SOC Briefing runs
- **THEN** schema validation, repair behavior, formal tone, and no-profanity requirements SHALL remain intact.
