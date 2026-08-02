# Spec: SOC Briefing Analyst Polish

## ADDED Requirements

### Requirement: Critical Findings and Escalations have distinct analyst purposes

SOC Briefing SHALL render Critical Findings and Escalations with meaningfully different analyst-facing content.

#### Scenario: Critical finding explains what happened and why it matters

- **GIVEN** critical evidence exists
- **WHEN** SOC Briefing sections are normalized
- **THEN** Critical Findings SHALL explain what happened and why it matters
- **AND** SHALL include evidence-bounded confidence when confidence appears.

#### Scenario: Escalation explains immediate attention and next action

- **GIVEN** an escalation-worthy item exists
- **WHEN** SOC Briefing sections are normalized
- **THEN** Escalations SHALL identify what needs immediate analyst attention
- **AND** SHALL state what should happen next
- **AND** SHALL explain why the item cannot wait.

### Requirement: Recommendations read naturally

SOC Briefing SHALL render recommendations as natural SOC analyst instructions, not mechanical field concatenation.

#### Scenario: Source IP recommendation is natural

- **GIVEN** recommendation data includes a source IP target
- **WHEN** SOC Briefing recommendations are normalized
- **THEN** the recommendation SHALL name the source IP in a natural investigation sentence
- **AND** SHALL NOT include awkward phrases such as "for Source IP".

### Requirement: Confidence and judgment are evidence-bounded

SOC Briefing SHALL avoid overconfident maliciousness claims unless evidence supports them.

#### Scenario: Confidence includes evidence-based rationale

- **GIVEN** a finding includes a confidence value
- **WHEN** the finding is rendered
- **THEN** confidence SHALL include a brief explanation tied to available evidence.

#### Scenario: Cautious judgment is preserved

- **GIVEN** evidence shows scanning without confirmed exploitation
- **WHEN** SOC Briefing prose is rendered
- **THEN** the prose SHALL state uncertainty or limited evidence rather than asserting confirmed malicious activity.
