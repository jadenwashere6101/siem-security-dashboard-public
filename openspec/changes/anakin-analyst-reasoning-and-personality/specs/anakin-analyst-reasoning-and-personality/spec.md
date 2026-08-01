# Spec: Anakin Analyst Reasoning And Personality

## ADDED Requirements

### Requirement: Shared Detection Engineer Persona

Anakin prompts MUST reuse a shared persona/reasoning policy for SIEM analyst-facing workflows where freeform prose or generated content is produced.

#### Scenario: Shared policy is included

- **GIVEN** a Quick Explain, Deep Investigate, Decision Support, Generate Artifact, SOC Briefing, or Repo Assistant prompt is built
- **WHEN** the prompt is inspected
- **THEN** it contains the shared Detection Engineer persona or the workflow-specific policy derived from it
- **AND** it prohibits robotic visible-field repetition and generic filler.

### Requirement: Quick Explain Is Concise And Bounded

Quick Explain MUST answer with short, conversational reasoning from already-loaded context only.

#### Scenario: Quick Explain prompt

- **GIVEN** Quick Explain prompt construction
- **WHEN** the prompt is built
- **THEN** it asks for what happened, what matters, confidence, and one next check
- **AND** it forbids tool use and long essay-style output.

### Requirement: Deep Investigate Performs Skeptical Analysis

Deep Investigate MUST require support, contradiction or benign explanations, missing evidence, confidence, and prioritized read-only next steps.

#### Scenario: Deep Investigate prompt

- **GIVEN** Deep Investigate prompt construction
- **WHEN** the prompt is built
- **THEN** it requires supporting evidence, evidence against the leading theory, missing evidence, confidence, and next steps
- **AND** it forbids merely creating a longer visible-field summary.

### Requirement: Decision Support Remains Recommendation-Only

Decision Support MUST answer what the analyst should do without drafting, applying, or confirming artifacts.

#### Scenario: Decision Support prompt

- **GIVEN** Decision Support prompt construction
- **WHEN** the prompt is built
- **THEN** it requires one primary recommendation, alternatives, risks, confidence, and what would change the recommendation
- **AND** it explicitly forbids artifact generation or action execution.

### Requirement: Generate Artifact Stays Schema-Compliant

Generate Artifact MUST preserve strict structured-output schemas, validation, and bounded repair while improving specificity.

#### Scenario: Artifact prompt

- **GIVEN** a draft prompt is built
- **WHEN** the draft type has a strict schema
- **THEN** the prompt keeps JSON-only schema instructions
- **AND** it requires evidence-specific content rather than boilerplate.

### Requirement: Briefing And Repo Assistant Tone

SOC Briefing MUST sound like concise analyst handoff, and Repo Assistant MUST distinguish repository facts from architectural judgment.

#### Scenario: Dedicated prompts

- **GIVEN** briefing or repo assistant prompts
- **WHEN** they are built
- **THEN** briefing prompts prioritize attention and low-value noise handling
- **AND** repo prompts distinguish cited facts from judgment while preserving citations.

### Requirement: Golden Reasoning Acceptance

The offline acceptance suite MUST include realistic golden cases evaluated for reasoning properties rather than exact wording.

#### Scenario: Golden cases

- **GIVEN** the offline acceptance tests run
- **WHEN** golden cases are evaluated
- **THEN** likely password spray, commodity recon, weak high-severity evidence, incident contradiction, graph spike, decision support, SOC briefing, and repo assistant cases pass required reasoning-property checks.
