## ADDED Requirements

### Requirement: Participating workflows use authoritative threads
The system SHALL support conversation continuity for Quick Explain, Ask Anakin auto-routing, Deep Investigate, Decision Support, and Generate Artifact only when an authenticated request supplies an owned active SIEM thread envelope. Stateless callers SHALL remain compatible.

#### Scenario: Follow-up uses an owned thread
- **WHEN** an analyst submits a participating workflow with a valid thread, expected version, and client request ID
- **THEN** the system persists an ordered user turn and executes the workflow with server-selected conversation context

#### Scenario: Stateless request remains independent
- **WHEN** a participating workflow request omits conversation metadata
- **THEN** the system executes the existing stateless behavior without reading or writing a thread

### Requirement: Conversation context selection is deterministic and bounded
The system SHALL select active entities, valid compact state, fresh verified evidence, analyst statements, corrections, unresolved questions, and bounded recent completed turns according to deterministic priority and the selected workflow profile budget. The system SHALL NOT send the complete thread or silently truncate serialized context.

#### Scenario: Context exceeds its allocation
- **WHEN** eligible thread context exceeds the reserved conversation budget
- **THEN** the system omits whole lower-priority items, reports included and omitted counts and reasons, and keeps the final prompt within the workflow limit

#### Scenario: Minimum context cannot fit
- **WHEN** the minimum safe conversation packet cannot fit beside required workflow instructions
- **THEN** the system returns `conversation_context_too_large` without invoking the model

### Requirement: Stored memory remains untrusted and provenance-aware
The system SHALL label verified evidence, analyst statements, corrections, model inferences, and unresolved questions distinctly in prompt context. Stored messages and summaries SHALL be treated as untrusted data and SHALL NOT override system, workflow, tool, read-only, RBAC, or artifact safety instructions.

#### Scenario: Analyst supplies an instruction-like claim
- **WHEN** a stored analyst statement contains prompt-like control text or an unsupported factual claim
- **THEN** the system sanitizes and labels it as an analyst statement rather than a system instruction or verified fact

#### Scenario: Correction supersedes inference
- **WHEN** a valid correction targets a prior model inference
- **THEN** selected context prefers the correction and excludes the superseded inference from active conclusions without modifying verified evidence

### Requirement: Follow-up references resolve or clarify deterministically
The system SHALL classify continuation, explanation, comparison, prior-focus, correction, reset, and generic entity references using authoritative thread state. It SHALL resolve only a unique supported referent and SHALL ask for clarification rather than guess when multiple or no valid candidates exist.

#### Scenario: Why refers to the prior conclusion
- **WHEN** the analyst asks "why?" after one applicable assistant conclusion
- **THEN** the system binds the follow-up to that conclusion and includes its provenance in the context packet

#### Scenario: Ambiguous IP reference
- **WHEN** the analyst refers to "the IP" and multiple equally salient IP entities are active
- **THEN** the system returns a structured clarification listing safe candidate labels without invoking the model

#### Scenario: Compare and go back
- **WHEN** the analyst asks to compare two resolvable entities or return to a previous distinct focus
- **THEN** the system selects those validated entities deterministically and records the resulting focus transition

### Requirement: Conversation generation is serialized and idempotent
The system SHALL allow at most one generating turn per thread, allocate turn sequences transactionally, return the original turn/request for duplicate client request IDs including terminal retries, and prevent stale or out-of-order completions from mutating newer state.

#### Scenario: Two tabs submit concurrently
- **WHEN** two tabs submit different turns against the same thread version
- **THEN** one submission is accepted and the other receives a deterministic conflict without concurrent generation

#### Scenario: Completed request is retried
- **WHEN** the same owner, thread, and client request ID are submitted after the original request reached a terminal state
- **THEN** the system returns the original linked turn, request, and result without another model call

### Requirement: Async workflow lifecycle is linked to conversation turns
The system SHALL atomically link conversational Deep Investigate, Decision Support, and Generate Artifact requests to their queued user turns. Workers SHALL revalidate the current user and role, rebuild bounded context at execution, and persist terminal assistant output under owner, lease, and thread-version guards.

#### Scenario: Refresh during async generation
- **WHEN** the analyst refreshes while a linked request is queued or running
- **THEN** thread and request reads expose the same authoritative progress and completed turns without browser-owned history

#### Scenario: Worker generation fails
- **WHEN** model or tool generation fails
- **THEN** the linked user turn and request become terminal failed while prior thread state remains unchanged

#### Scenario: Role is lost after queueing
- **WHEN** the queued actor is disabled or no longer has analyst access before worker execution
- **THEN** the worker fails the request closed before reading tools or invoking the model

### Requirement: Artifact continuity remains preview-only
Generate Artifact SHALL consume selected thread state and may persist generated text as an assistant artifact-preview turn, but SHALL preserve `preview_only=true`, `persisted=false`, `applied=false`, and `approval_required=true` and SHALL NOT trigger apply or confirmation behavior.

#### Scenario: Artifact survives refresh
- **WHEN** a conversational artifact request completes and the thread is reloaded
- **THEN** its assistant turn contains the preview text and mandatory safety labels without an operational SIEM write

### Requirement: Workflow namespaces remain isolated
Repo Assistant and SOC Briefing SHALL NOT read, accept, persist, or inject SIEM conversation context. Conversation metadata supplied to those workflows SHALL be rejected deterministically.

#### Scenario: Repo Assistant receives SIEM thread metadata
- **WHEN** a Repo Assistant request includes a SIEM conversation envelope
- **THEN** the system rejects the envelope before repository retrieval or generation

#### Scenario: SOC Briefing executes
- **WHEN** a scheduled or manual SOC Briefing runs
- **THEN** it uses its existing job context only and does not query conversation threads

### Requirement: Derived state can be rebuilt safely
The system SHALL rebuild a bounded context packet from authoritative turns, entities, and evidence when compact state or summary is absent or invalid, and SHALL expose rebuild metadata without promoting unsupported content.

#### Scenario: Stored summary is corrupt
- **WHEN** the selector encounters malformed derived state or an unusable summary
- **THEN** it ignores that derived value, uses authoritative bounded records, and marks the context as rebuilt

### Requirement: Entity lifecycle changes fail without substitution
The system SHALL revalidate referenced entities and thread ownership at submission and execution. Deleted, inaccessible, expired, reset, or closed context SHALL not be replaced with a similarly named entity or another user's thread.

#### Scenario: Active entity was deleted
- **WHEN** a follow-up references an entity that is no longer accessible
- **THEN** the system returns a target-unavailable or expired-context response and preserves the existing focus without model invocation
