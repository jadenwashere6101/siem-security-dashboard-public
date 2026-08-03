## ADDED Requirements

### Requirement: Eligible turns are planned before capability selection
The system SHALL reinterpret every eligible SIEM conversation turn after server-owned entity/context resolution and before selecting a capability. A prior workflow SHALL be context only and MUST NOT control a new turn.

#### Scenario: New lookup follows an explanation
- **WHEN** an analyst asks for the newest HIGH alert after an alert explanation
- **THEN** the system plans a current-alert lookup instead of repeating the prior explanation strategy

#### Scenario: Explicit shortcut is a hint
- **WHEN** an explicit shortcut and current question imply different tasks
- **THEN** the planner evaluates the current question and treats the shortcut as a non-authoritative preferred-strategy hint

### Requirement: Planner input is compact, authoritative, and untrusted
The system SHALL construct a measured planner packet from the current message, resolved entities, compact relevant thread state, assertion provenance, fresh verified evidence summaries, capability/tool boundaries, and latency class. It MUST NOT include complete history, raw tool results, frontend workspace state, or stored text as system instructions.

#### Scenario: Production-sized thread state
- **WHEN** a thread contains multiple entities, corrections, stale and fresh evidence, unresolved questions, and recent turns
- **THEN** the planner packet compacts deterministically, preserves the current message and primary entity, identifies omissions, and fits its assigned budget

### Requirement: Plans use a strict structured contract
The system SHALL require the model proposal to declare only current intent, evidence sufficiency, required evidence, strategy, tool categories, bounded semantic evidence requirements, clarification, reasoning summary, stopping condition, and confidence. The server SHALL populate resolved entities, prior-turn relationship, capability, read-only safety, and execution metadata from authoritative state or validated strategy mappings. Plans SHALL contain no executable code or backend query syntax.

#### Scenario: Valid bounded plan
- **WHEN** the planner returns every required reasoning field with allowed and internally consistent values
- **THEN** deterministic validation accepts the reasoning proposal and the server compiles a complete plan for dispatch

#### Scenario: Model supplies server-owned metadata
- **WHEN** model output includes entities, prior-turn relationship, capability, safety, or execution metadata
- **THEN** strict validation rejects those unknown fields rather than ignoring them or allowing them to override server authority

#### Scenario: Malformed plan
- **WHEN** the planner returns malformed JSON, missing fields, invalid values, or an oversized plan
- **THEN** the system permits at most one bounded repair and otherwise fails safely without sticky routing

### Requirement: Plan validation is authoritative
The system SHALL validate the exact reasoning-field schema, strategy/tool/evidence relationships, approved read-only tool category, authoritative entity availability and consistency, namespace boundary, evidence provenance/freshness, stopping condition, plan size, and artifact safety before execution. Capability and safety SHALL be deterministically attached only after the model proposal passes validation.

#### Scenario: Forbidden plan
- **WHEN** a plan requests mutation, Repo Assistant, SOC Briefing continuation, an unapproved tool, or an entity absent from authoritative resolution
- **THEN** the system rejects it without executing the proposed capability or tool

#### Scenario: User claim remains a statement
- **WHEN** an analyst says an IP is an approved scanner
- **THEN** planning may revise an inference using the correction but MUST NOT promote the statement to verified evidence

### Requirement: Strategies dispatch through bounded existing capabilities
The system SHALL support direct answer, one quick evidence lookup, bounded investigation, decision support, artifact draft, two-entity comparison, clarification, and unsupported/boundary strategies. It SHALL dispatch accepted plans only through existing approved read-only capability paths and SHALL permit no more than one planner-selected evidence action.

#### Scenario: Evidence is sufficient
- **WHEN** current fresh verified context answers the question
- **THEN** the planner selects direct answer without a tool category

#### Scenario: Evidence is insufficient
- **WHEN** one bounded approved lookup can answer the question
- **THEN** the planner selects quick evidence lookup with exactly one relevant read-tool category, non-empty bounded evidence requirements, and a stopping condition

### Requirement: Evidence intent is preserved through tool execution
The system SHALL accept only allowlisted scalar evidence requirements for severity, alert type, source IP, destination IP, hostname, username, time window, sort order, and bounded result limit. It SHALL validate category compatibility and values before deterministically translating requirements into an existing approved read-tool request. It MUST reject unknown, invalid, unrepresentable, mutation-capable, or query-language input and MUST NOT silently discard accepted requirements.

#### Scenario: Most recent HIGH alert
- **WHEN** a validated alert lookup requests HIGH severity, newest order, and one result
- **THEN** the executed alert search contains severity `high`, sort `newest`, and limit `1`, and the response is grounded only in matching returned evidence

#### Scenario: Alert-family lookup from one source
- **WHEN** a validated lookup requests a specific alert type from a valid source IP within a bounded time window
- **THEN** all four constraints reach the existing alert search and non-matching evidence is excluded

#### Scenario: Unsupported filter cannot be represented
- **WHEN** a plan supplies an unknown filter, invalid value, excessive bound, or a requirement unsupported by the selected tool category
- **THEN** validation fails before tool execution and the system does not replace it with a generic unfiltered lookup

#### Scenario: Artifact request
- **WHEN** an analyst requests an artifact
- **THEN** the planner dispatches Generate Artifact with preview-only, persisted-false, applied-false, and approval-required guarantees

### Requirement: Ambiguity and planner failure fail safely
The system SHALL ask for clarification without model/tool workflow invocation when authoritative resolution is ambiguous. Planner timeout, provider failure, or repair failure SHALL preserve prior thread state and MUST NOT revert to the previous workflow.

#### Scenario: Ambiguous referent
- **WHEN** a turn refers to an IP and multiple salient IPs are plausible
- **THEN** the system stores a concise clarification turn and creates no capability execution request

#### Scenario: Planner unavailable
- **WHEN** an auto-routed turn cannot obtain a valid plan
- **THEN** the system returns a truthful planner-unavailable response and leaves prior conclusions and evidence unchanged

### Requirement: Response shape matches the current task
The system SHALL pass task intent and validated strategy to downstream capability prompts without imposing one universal prose template.

#### Scenario: Direct alert lookup
- **WHEN** an analyst asks for the newest HIGH alert and the required evidence is retrieved
- **THEN** the response directly identifies the alert and relevant evidence rather than emitting a generic Fact/Inference/Uncertainty template

#### Scenario: Comparison
- **WHEN** exactly two accessible entities are resolved for comparison
- **THEN** the response compares those entities and does not repeat the prior single-entity summary

### Requirement: Planner boundaries remain isolated
The SIEM planner SHALL be limited to canonical conversational Quick Explain, Deep Investigate, Decision Support, Generate Artifact, and approved SOC reads. Repo Assistant, SOC Briefing, action confirmation/apply, response execution, and mutation-capable routes MUST remain outside the planner.

#### Scenario: Boundary request
- **WHEN** an eligible SIEM thread asks to continue a SOC Briefing, inspect repository code, or apply an action
- **THEN** the planner returns an unsupported/boundary result without crossing namespaces or invoking mutation

### Requirement: Planner behavior is measured across paraphrases and failures
The system SHALL test at least three natural phrasings for each required behavioral intent and SHALL measure packet/prompt sizes, repair use, strategy consistency, and repeated-run model contract performance with production-shaped state.

#### Scenario: Paraphrase matrix
- **WHEN** current lookup, prioritization, explanation, evidence, topic switch, comparison, correction, no-tool, ambiguity, and boundary intents are expressed in three natural ways
- **THEN** each phrasing produces a contract-consistent strategy without exact-sentence or growing keyword-list routing

#### Scenario: End-to-end persisted planning
- **WHEN** a production-shaped conversational request is planned through a controlled local-provider test double
- **THEN** plan construction, validation, dispatch, response envelope, and PostgreSQL turn state complete under owner and workflow boundaries

### Requirement: Planner capability is registered with the configured local provider
The system SHALL register `agentic_analyst_planning` through the normal provider capability contract. The configured Ollama provider SHALL accept that capability and reach generation, while providers and capabilities that are not explicitly registered MUST continue to fail closed. The planning profile SHALL remain local-only with paid fallback disabled.

#### Scenario: Planner reaches local generation
- **WHEN** the gateway receives an `agentic_analyst_planning` request using the configured local planning profile
- **THEN** Ollama capability validation accepts it and invokes local generation without attempting paid fallback

#### Scenario: Unknown capability remains blocked
- **WHEN** the gateway receives an unregistered capability
- **THEN** it returns provider-incapable without invoking generation

### Requirement: Planner uses a dedicated local planning profile
The system SHALL route initial and repair planner requests through the approved `agentic_planning` profile using the local `llama3.1:8b` model. The profile SHALL have planner-specific prompt, output, timeout, and temperature limits, SHALL remain local-only, and SHALL disable paid fallback. Existing Quick Explain and other workflow profile assignments MUST remain unchanged.

#### Scenario: Planner profile is observable
- **WHEN** the planner submits a proposal or its one bounded repair
- **THEN** the gateway and provider metadata identify profile `agentic_planning` and model `llama3.1:8b`

#### Scenario: Quick Explain profile is unchanged
- **WHEN** Quick Explain executes outside the planner generation stage
- **THEN** it continues using `fast_triage` and its existing `llama3.2:3b` assignment

#### Scenario: Contradictory 8B plan
- **WHEN** the model combines `direct_answer` with a tool category, omits required evidence for a lookup, leaves reasoning or stopping conditions empty, or otherwise violates strategy relationships
- **THEN** deterministic validation rejects the plan, permits at most one bounded model repair, and fails closed if the repaired plan remains invalid

### Requirement: Original workflow boundaries are validated before planning
The system SHALL validate the originally requested workflow and SIEM conversation namespace before planner generation, repair, classification, or fallback. Repo Assistant, SOC Briefing, and unsupported workflow names MUST NOT be transformed into a SIEM capability. A post-planning classification SHALL NOT erase the original request boundary.

#### Scenario: Explicit isolated workflow
- **WHEN** a SIEM conversation request explicitly names Repo Assistant or SOC Briefing
- **THEN** the request is rejected before planner or workflow generation regardless of planner availability or output

#### Scenario: Unsupported workflow
- **WHEN** a SIEM conversation request names an unknown workflow
- **THEN** it fails with an unsupported-workflow error and MUST NOT silently execute Quick Explain

#### Scenario: Valid degraded shortcut
- **WHEN** the current request explicitly selects an allowed SIEM shortcut and the planner is unavailable
- **THEN** only the documented safe shortcut fallback may run; an unhinted `auto` request remains planner-unavailable
