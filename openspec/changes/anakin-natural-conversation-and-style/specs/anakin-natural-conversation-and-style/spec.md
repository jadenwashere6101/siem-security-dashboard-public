# anakin-natural-conversation-and-style

## ADDED Requirements

### Requirement: Interactive Natural Conversation Contract

Interactive Anakin workflows SHALL use natural, direct, concise analyst-to-analyst style without weakening evidence-bounded reasoning.

#### Scenario: Casual interactive prompt
- **WHEN** a casual Quick Explain, Ask Anakin, Decision Support, Deep Investigate, or Repo Assistant prompt is classified as casual
- **THEN** the prompt SHALL instruct Anakin to answer immediately, use short natural sentences, and avoid formal preambles
- **AND** SHALL NOT force slang, theatrics, or a character performance.

#### Scenario: Formal shareable output
- **WHEN** Generate Artifact, SOC Briefing, notes, playbooks, detection changes, or response recommendations are generated
- **THEN** the prompt SHALL remain professional
- **AND** SHALL prohibit slang and profanity.

### Requirement: Few-Shot Style Examples

Interactive prompts SHALL include a small bounded set of examples that demonstrate natural responses versus robotic responses.

#### Scenario: Examples stay bounded
- **WHEN** an interactive workflow prompt is built
- **THEN** it SHALL include concise style examples
- **AND** prompt size SHALL remain within the selected model profile limit.

### Requirement: Positive Anti-Filler Enforcement

Anakin response-quality checks SHALL evaluate response properties, not only exact banned phrases.

#### Scenario: Robotic filler paraphrase
- **WHEN** a response uses robotic preambles or close filler paraphrases such as alert-indicates wording
- **THEN** acceptance checks SHALL flag the response.

#### Scenario: Low-value paragraph
- **WHEN** a paragraph only restates visible fields without new reasoning, evidence, uncertainty, or next step
- **THEN** acceptance checks SHALL flag it as low value.

### Requirement: Decision Support Markdown Recommendation Detection

Decision Support recommendation-first enforcement SHALL recognize markdown-formatted recommendation labels.

#### Scenario: Markdown recommendation first
- **WHEN** the first rendered line is `**Recommendation:**`, `## Recommendation`, or a bulleted/numbered recommendation label
- **THEN** the helper SHALL treat the recommendation as already first
- **AND** metadata SHALL truthfully report that no reordering was needed.

#### Scenario: Recommendation appears later
- **WHEN** the model places a markdown-formatted recommendation section after other content
- **THEN** the helper SHALL move that section to the first rendered line
- **AND** metadata SHALL truthfully report that recommendation-first enforcement occurred.

#### Scenario: Unrelated label
- **WHEN** a line contains recommendation as an unrelated phrase rather than the section label
- **THEN** it SHALL NOT be mistaken for the recommendation section.
