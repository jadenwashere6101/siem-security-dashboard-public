## ADDED Requirements

### Requirement: Guided-analysis prompts fit by construction
The system SHALL construct every provider-bound guided-analysis synthesis prompt so its complete serialized length does not exceed the selected AI profile's maximum prompt characters.

#### Scenario: Large evidence remains within profile limit
- **WHEN** a Deep Investigation contains more evidence and conversation history than the guided-analysis profile can accept
- **THEN** the system SHALL compact optional history and lower-priority evidence before mandatory content and SHALL invoke the provider only with a prompt at or below the configured limit

#### Scenario: Mandatory grounding context is preserved
- **WHEN** guided-analysis prompt compaction occurs
- **THEN** the bounded prompt SHALL retain the current question, task and entity context, essential validated evidence, source provenance, truncation metadata, grounding rules, and read-only safety policy

### Requirement: Oversized mandatory content degrades safely
The system SHALL return a deterministic grounded partial investigation result instead of failing when the mandatory guided-analysis prompt content cannot fit within the configured profile limit.

#### Scenario: Mandatory content exceeds the limit
- **WHEN** the compact mandatory prompt still exceeds the selected profile's limit
- **THEN** the system SHALL skip provider invocation and return a source-cited partial answer that discloses truncation and does not claim an operational action

### Requirement: Prompt budgeting is measurable
The system SHALL report sanitized prompt-budget measurements sufficient to distinguish the original candidate size, bounded size, omitted optional content, and deterministic fallback use.

#### Scenario: Investigation prompt is compacted
- **WHEN** the full guided-analysis candidate exceeds the profile limit
- **THEN** correlation metadata SHALL identify the limit, measured candidate and final sizes, compaction state, and included or omitted content without exposing secrets
