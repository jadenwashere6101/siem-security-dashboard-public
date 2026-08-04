## ADDED Requirements

### Requirement: Generated artifact previews use a depth-bounded storage representation
The system SHALL normalize trusted generated artifact previews at the assistant-turn persistence boundary before applying the existing session-memory validation contract.

#### Scenario: Nested artifact payload is persisted
- **WHEN** Artifact Generation returns nested objects or lists under an artifact payload field that would exceed the session-memory depth limit
- **THEN** the system SHALL flatten those nested values into a bounded representation and persist the preview successfully

#### Scenario: Meaning and provenance survive normalization
- **WHEN** an artifact preview is normalized
- **THEN** its meaningful draft fields, source provenance, preview-only labels, thread context, original and stored depth, flattened paths, and truncation state SHALL remain available for review and audit

### Requirement: Session-memory safety limits remain fail closed
The system MUST retain the existing global structured-value depth limit and MUST NOT apply artifact-specific normalization to arbitrary public or user-authored session data.

#### Scenario: Unsafe public nested input is rejected
- **WHEN** arbitrary session-memory input exceeds the existing depth limit
- **THEN** the system SHALL reject it with the existing validation error rather than flattening or accepting it

#### Scenario: Malformed generated artifact cannot be bounded safely
- **WHEN** a generated artifact has an invalid envelope or cannot be represented within the existing size and depth limits
- **THEN** persistence SHALL fail closed without applying an artifact or weakening session-memory validation

### Requirement: Artifact persistence remains preview only
The system SHALL preserve the existing preview-only Artifact Generation boundary after normalization.

#### Scenario: Fresh or long-lived thread generates an artifact
- **WHEN** Artifact Generation completes in a fresh thread or after repeated conversation turns
- **THEN** the assistant preview SHALL persist with approval required and with persisted/applied operational flags remaining false
