## ADDED Requirements

### Requirement: Repo questions are classified
Repo Architecture Assistant SHALL classify repository questions before prompting.

#### Scenario: Evaluative question classification
- **WHEN** the user asks “What is my most impressive feature?”
- **THEN** the assistant SHALL classify the question as evaluative/opinion/recommendation.

#### Scenario: Factual question classification
- **WHEN** the user asks where a component is implemented
- **THEN** the assistant SHALL classify the question as factual/repository-grounded.

#### Scenario: Architectural explanation classification
- **WHEN** the user asks how parts of the system fit together
- **THEN** the assistant SHALL classify the question as architectural explanation.

### Requirement: Backend owns citations
Repo Architecture Assistant SHALL attach citations from retrieved repository evidence rather than trusting model-generated paths.

#### Scenario: Missing citation syntax does not invalidate useful answer
- **WHEN** the model returns a useful answer without exact `[path:line_start-line_end]` syntax
- **THEN** the backend SHALL keep the answer
- **AND** attach citations selected from retrieved current evidence.

#### Scenario: Arbitrary model paths are ignored
- **WHEN** the model emits citation text for files or ranges not in retrieved evidence
- **THEN** those citations SHALL NOT be trusted
- **AND** response citations SHALL reference only retrieved evidence.

### Requirement: Evaluative answers are natural and grounded
Evaluative/opinion answers SHALL answer directly while grounding judgment in repository evidence.

#### Scenario: Most impressive feature question
- **WHEN** the user asks “What is my most impressive feature?”
- **THEN** the assistant SHALL provide a useful judgment with reasons
- **AND** distinguish fact from judgment
- **AND** attach backend-selected evidence citations.

### Requirement: Factual and architectural answers stay grounded
Factual and architecture answers SHALL use retrieved evidence and avoid unsupported claims.

#### Scenario: SOAR worker implementation question
- **WHEN** the user asks “Where is the SOAR worker implemented?”
- **THEN** the assistant SHALL answer with retrieved repository evidence
- **AND** attach valid citations from retrieved chunks.

#### Scenario: Unsupported detail
- **WHEN** retrieved evidence does not support a requested claim
- **THEN** the assistant SHALL omit the claim or label it as inference.

### Requirement: Safety boundaries remain unchanged
Repo Architecture Assistant SHALL preserve existing access and execution boundaries.

#### Scenario: Read-only bounded repository assistance
- **WHEN** Repo Architecture Assistant handles a request
- **THEN** it SHALL remain super-admin-only, read-only, bounded to repository retrieval, routed through `developer_assistant`, and unable to mutate source/runtime state.
